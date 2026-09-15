"""
Infiny Box — the first-run wizard.

Phase 1 ships no model; the user brings their own. The wizard's job is to carry
a person from "I started the container" to "the agent answers" without reading
any documentation. It is the first thing they see, hence:

  * stdlib and core/ only — no rich, no prompt_toolkit. The wizard has to work
    in the poorest environment there is, including one where dependencies
    failed to install;
  * no HTTP to our own bridge — we call core/model_source.py directly. A wizard
    that needs a running service in order to configure things is useless
    exactly when it is needed;
  * every refusal is explained. "Nothing found", with no reason, is a dead end
    the user leaves by closing the window.

All text goes through infiny_cli/i18n.py — English is the base language,
Russian is switched on with `/lang ru`. Until 2026-09-03 this wizard was the
one large module that did not import i18n at all: the CLI spoke English to the
user and the wizard before it spoke Russian.

The Phase 1 client is the CLI. There is no graphical interface here and there
will not be: it is platform-dependent (on WSL it opens through Windows interop,
in Docker on macOS it does not open at all), and the Box has to start the same
way everywhere.
"""
from __future__ import annotations

import asyncio
import sys

from core import model_source, runtime_env

from .i18n import t as _


def _say(msg: str = "") -> None:
    print(msg, flush=True)


def _ask(prompt: str, default: str = "") -> str:
    """Input with a default. EOF/Ctrl+D means "keep the default", not a crash."""
    suffix = f" [{default}]" if default else ""
    try:
        answer = input(f"{prompt}{suffix}: ").strip()
    except (EOFError, KeyboardInterrupt):
        _say()
        return default
    return answer or default


def _yes(prompt_key: str) -> bool:
    """A yes/no question defaulting to no. The answer is checked in both
    languages."""
    return _ask(_(prompt_key), "n").strip().lower()[:1] in ("y", "д")


def _choose(options: list[str], prompt: str) -> int | None:
    """Pick from a list. Returns an index, or None if the user declined."""
    if not options:
        return None
    if len(options) == 1:
        return 0
    for i, opt in enumerate(options, 1):
        _say(f"  {i}. {opt}")
    raw = _ask(prompt, "1")
    if not raw.isdigit() or not (1 <= int(raw) <= len(options)):
        return None
    return int(raw) - 1


def _num(n: int) -> str:
    """Thousands separated by a space — reads the same in both languages."""
    return f"{n:,}".replace(",", " ")


def _print_status(cur: dict) -> None:
    if cur.get("configured"):
        _say(_("setup_connected", model=cur["model"], url=cur["base_url"]))
    else:
        _say(_("setup_not_connected", reason=cur.get("reason", "—")))


async def _pick_endpoint() -> tuple[str, str, str] | None:
    """
    Find an endpoint and a model. Returns (base_url, model, api_key) or None.

    Autodiscovery first, then — always — the option to type an address by hand:
    cloud endpoints and non-standard ports are not discoverable by design, and
    without manual entry the Box would be tied to local servers.

    The key is returned as the THIRD element rather than lost here. The function
    used to return only a pair; the key was asked for and stayed in a local
    variable — and the cloud path was broken end to end. probe() got the key (the
    model list arrived, everything looked fine), while the tool check and the
    config write ran with the default "no-key". The user saw "CHECK FAILED
    (http_401): Invalid API Key" immediately after the wizard had successfully
    listed 48 models using that same key, and drew the only reasonable
    conclusion: that their key was bad. Caught by the very first live run
    through Mistral on 2026-09-02; it never surfaced on local Ollama, which
    needs no key.
    """
    _say(_("setup_searching"))
    found = await model_source.discover()

    if found:
        labels = [f"{f['label']:18} {f['base_url']}  "
                  f"{_('setup_n_models', n=len(f['models']))}" for f in found]
        labels.append(_("setup_manual_entry"))
        idx = _choose(labels, _("setup_what"))
        if idx is None:
            return None
        if idx < len(found):
            # Autodiscovered endpoints are local and need no key.
            ep = found[idx]
            if not ep["models"]:
                _say(_("setup_no_models"))
                model = _ask(_("setup_model_name"))
                return (ep["base_url"], model, "no-key") if model else None
            _say()
            m = _choose(ep["models"], _("setup_model"))
            return (ep["base_url"], ep["models"][m], "no-key") if m is not None else None
    else:
        _say()
        _say(model_source.explain_not_found())
        _say()

    base_url = _ask(_("setup_address"))
    if not base_url:
        return None
    api_key = _ask(_("setup_apikey"), "no-key")

    _say(_("setup_checking"))
    res = await model_source.probe(base_url, api_key)
    if not res["ok"]:
        # Do not give up immediately. The model list and whether the endpoint
        # works are different questions: Together's list weighs 133 KB and
        # breaks halfway on a slow or lossy link (measured 2026-09-02: curl cut
        # off at 128 KB of ~133), while a chat response is a few hundred bytes
        # and goes through fine. This used to be `return None`, so someone on a
        # bad connection could not attach a perfectly working cloud at all.
        _say(_("setup_list_failed", err=res["error"]))
        _say(_("setup_list_failed_hint1"))
        _say(_("setup_list_failed_hint2"))
        if not _yes("setup_type_model_q"):
            return None
        model = _ask(_("setup_model_name"))
        return (base_url, model, api_key) if model else None

    if res["models"]:
        _say()
        m = _choose(res["models"], _("setup_model"))
        model = res["models"][m] if m is not None else ""
    else:
        model = _ask(_("setup_model_name"))
    return (base_url, model, api_key) if model else None


async def _verify_tools(base_url: str, model: str, api_key: str = "no-key") -> bool:
    """
    Actually verify tool calling. Returns False only when the user, after an
    explicit warning, chose not to continue.

    A separate step, because a reply to GET /v1/models only proves there is a
    live HTTP server and says NOTHING about whether the agent will run.
    llama.cpp without --jinja and vLLM without --enable-auto-tool-choice cannot
    call tools at all — and learning that three steps into a conversation is far
    worse than learning it now.

    The waiting threshold is not arbitrary: measured 2026-07-29, a cold load of
    gemma4:12b took 105s. Without a warning, a pause that long reads as a hang.
    """
    _say()
    _say(f"  {_('setup_slow_check')}")
    try:
        res = await model_source.check_tool_calling(base_url, model, api_key)
    except KeyboardInterrupt:
        _say(_("setup_check_skipped"))
        return True

    if res["ok"]:
        _say(_("setup_tools_ok"))
        return True

    _say()
    _say(_("setup_check_failed", reason=res["reason"], detail=res["detail"]))
    if res["reason"] in ("http_401", "http_403"):
        # A separate branch, because the --jinja advice is useless here and only
        # confuses: the server never even reached the model.
        _say(_("setup_key_rejected"))
        _say(_("setup_key_r1"))
        _say(_("setup_key_r2"))
        _say(_("setup_key_r3"))
    if res["reason"] == "no_tool_calls":
        _say(_("setup_no_tools1"))
        _say(_("setup_no_tools2"))
        _say(_("setup_no_tools_r1"))
        _say(_("setup_no_tools_r2"))
        _say(_("setup_no_tools_r3"))
    return _yes("setup_connect_anyway")


async def _apply(base_url: str, model: str, api_key: str = "no-key") -> bool:
    _say()
    _say(_("setup_connecting", model=model, url=base_url))
    res = model_source.switch_to(base_url, model, api_key)
    if not res.get("ok"):
        _say(_("setup_error", err=res.get("error")))
        return False

    # The context window. Measured for real (`/api/ps`) rather than taken from
    # GGUF metadata, which holds the model's architectural maximum — 262,144 on
    # a typical modern one. Hermes believes that number and behaves as if space
    # were unlimited, while its own small-window guard stays silent forever,
    # because it compares against the same inflated figure.
    #
    # Cloud endpoints have no /api/ps, so ctx will be None — and that is correct:
    # there Hermes works the window out itself from /v1/models metadata, and
    # does it better than we can (verified on Mistral: max_context_length
    # 256000).
    ctx = res.get("context_length")
    if ctx:
        _say(_("setup_ctx", n=_num(ctx)))
    if res.get("context_too_small"):
        _say()
        _say(_("setup_ctx_small", min=_num(model_source.HERMES_MINIMUM_CONTEXT)))
        _say(_("setup_ctx_small1"))
        _say(_("setup_ctx_small2"))
        _say(_("setup_ctx_small3"))
        _say()
        _say(_("setup_ctx_fix"))
        _say("    OLLAMA_CONTEXT_LENGTH=65536 ollama serve")
        _say(_("setup_ctx_rerun"))
        _say()

    _say(_("setup_written"))
    # A deliberate separate check: "the config is written" and "everything
    # works" are different claims, and we have been burned passing the first off
    # as the second.
    ready = await model_source.wait_for_gateway(model_source.GATEWAY_MODELS_URL)
    if ready:
        _say(_("setup_ready"))
        return True
    _say(_("setup_gw_down"))
    _say(_("setup_gw_hint1"))
    _say(_("setup_gw_hint2"))
    return False


async def _run(force: bool) -> bool:
    _say()
    _say(_("setup_title"))
    _say(_("setup_env", env=runtime_env.detect_runtime()))
    cur = model_source.current_source()
    _print_status(cur)
    _say()

    if cur.get("configured") and not force:
        if not _yes("setup_reconfigure"):
            return True

    picked = await _pick_endpoint()
    if not picked:
        _say()
        _say(_("setup_cancelled_rerun"))
        return False

    base_url, model, api_key = picked
    if not await _verify_tools(base_url, model, api_key):
        _say(_("setup_cancelled"))
        return False
    return await _apply(base_url, model, api_key)


def run_setup(force: bool = False) -> bool:
    try:
        return asyncio.run(_run(force))
    except KeyboardInterrupt:
        _say()
        _say(_("setup_interrupted"))
        return False


def needs_setup() -> bool:
    """Whether a model source is configured. Cheap — reads config.yaml only."""
    return not model_source.current_source().get("configured")


if __name__ == "__main__":
    sys.exit(0 if run_setup(force="--force" in sys.argv) else 1)
