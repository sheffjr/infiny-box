"""
Infiny — where the model comes from.

Phase 1 is "my harness, your model": no model ships in the distribution. Infiny
attaches to any OpenAI-compatible endpoint the user already has running, local
(Ollama, LM Studio, llama.cpp server, vLLM) or in the cloud.

How we reach the user's host lives in core/runtime_env.py, because every
platform sandboxes differently (WSL2, Docker, bare Linux). What matters here is
the consequence they share: **a server listening only on 127.0.0.1 is
unreachable from inside the sandbox, by design.** That is the one real barrier,
and it is fixed by a single setting on the server side. So detection has to
tell "no server" apart from "server is there but only on loopback", and say so
out loud — see explain_not_found().

Decision about .wslconfig (2026-07-29): we run on NAT, the default mode, and do
NOT touch .wslconfig. It is global and affects every distribution the user has;
a Phase 1 installer has no business rewriting someone's networking for its own
convenience. Mirrored mode is offered as a suggestion in the hint text instead.

The Hermes config schema was verified empirically on 2026-07-27 against the
real resolver (hermes_cli.runtime_provider.resolve_runtime_provider) rather
than guessed at:
  - providers: {<key>: ...} + model.default: "<key>/<model>"  → DOES NOT WORK.
    Hermes does not parse the "name/" prefix, falls through to provider "auto"
    and fails with AuthError. This is exactly what a previous version of this
    file claimed to do.
  - providers: {<key>: ...} + model.provider: "<key>"          → works.
  - flat model: {default, provider: custom, base_url, api_key} → works, and
    resolves identically.
The flat form won: it is what 267 benchmark runs in round 2 exercised, and it
is what sits in hermes/config.yaml — so switching the source writes the same
shape the distribution started with, with no schema drift.
"""
import asyncio
import secrets
import socket
import subprocess
import time
from pathlib import Path

import httpx
import yaml

from core import runtime_env
from core.i18n import t as _

HERMES_HOME = Path.home() / ".hermes"
HERMES_CONFIG = HERMES_HOME / "config.yaml"

# Ports local OpenAI-compatible servers usually listen on. The label is only
# for display: what decides is whether /v1/models answered, never the port
# number.
KNOWN_PORTS: list[tuple[int, str]] = [
    (11434, "Ollama"),
    (1234, "LM Studio"),
    (8080, "llama.cpp server"),
    (8000, "vLLM"),
]

PROBE_TIMEOUT = 2.0

# Port of the Hermes OpenAI-compatible API server.
GATEWAY_PORT = 8642
GATEWAY_MODELS_URL = f"http://127.0.0.1:{GATEWAY_PORT}/v1/models"

# Timeout for the tool-calling check. Deliberately large: measured 2026-07-29
# on a live machine, a cold load of gemma4:12b in Ollama took 105s and
# qwen3.5:4b took 56s. A 30s timeout would condemn a working endpoint as dead.
CAPABILITY_TIMEOUT = 180.0

# A toy tool for the capability check. The schema is deliberately trivial: a
# model that cannot call this has no chance with the real Hermes toolset.
_PROBE_TOOL = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get current weather for a city",
        "parameters": {
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
    },
}


async def probe(base_url: str, api_key: str = "no-key") -> dict:
    """
    Check one endpoint the OpenAI way: GET {base_url}/models.

    /v1/models specifically, not Ollama's /api/tags — otherwise "any
    OpenAI-compatible endpoint" quietly means "Ollama only".

    An empty model list is not an error: some servers answer 200 with empty
    data and work perfectly well.
    """
    url = base_url.rstrip("/")
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        async with httpx.AsyncClient(timeout=PROBE_TIMEOUT) as c:
            r = await c.get(f"{url}/models", headers=headers)
    except Exception as e:
        return {"ok": False, "base_url": url, "models": [], "error": str(e)}

    if r.status_code != 200:
        return {"ok": False, "base_url": url, "models": [],
                "error": f"HTTP {r.status_code}"}
    try:
        data = r.json().get("data", [])
        models = [m["id"] for m in data if isinstance(m, dict) and m.get("id")]
    except Exception as e:
        return {"ok": False, "base_url": url, "models": [],
                "error": _("err_not_openai", err=e)}
    return {"ok": True, "base_url": url, "models": models, "error": None}


async def discover() -> list[dict]:
    """
    Find running local endpoints: every host address × every known port.

    The probes run in parallel. Sequentially this is 2s × addresses × ports —
    up to 20 seconds of staring at the first-run screen, which is far too long.
    The address count is platform-dependent, so the sequential version also
    grows.
    """
    targets = [
        (f"http://{host}:{port}/v1", label)
        for host in runtime_env.host_candidates()
        for port, label in KNOWN_PORTS
    ]
    # _label rather than _: in this module `_` is the translation function, and
    # a loop variable of the same name shadows it. Harmless today (a generator
    # has its own scope), but the first _("key") call inside such a loop would
    # fail with "str is not callable", and that takes a while to find.
    results = await asyncio.gather(*(probe(url) for url, _label in targets))
    return [
        {"base_url": url, "label": label, "models": res["models"]}
        for (url, label), res in zip(targets, results)
        if res["ok"]
    ]


async def check_tool_calling(base_url: str, model: str,
                             api_key: str = "no-key") -> dict:
    """
    Actually verify that this endpoint and model can call tools.

    Why this is separate from probe(): a reply to GET /v1/models only proves
    there is a live HTTP server. It says NOTHING about whether the agent will
    run. Tool calling is a matter of launch flags rather than OpenAI
    compatibility:
      - llama.cpp server without `--jinja` cannot call tools at all;
      - vLLM needs `--enable-auto-tool-choice --tool-call-parser <...>`;
      - LM Studio depends on its version and the model's template.
    Promising "any OpenAI-compatible endpoint" and letting the user discover
    the truth three steps into a conversation is the worst outcome. Asking the
    server directly is cheaper.

    NOTE: max_tokens is deliberately not set. With `max_tokens: 200`,
    qwen3.5:4b returned content="" and NOT ONE tool_call, at HTTP 200 with no
    error — a reasoning model spent the budget thinking and was cut off before
    the tool call. The failure looked like "the model is stupid". Same class of
    trap as Ollama's default 4096 context.

    Returns {"ok", "tool_calls", "reason", "detail"}.
    """
    url = base_url.rstrip("/")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": model,
        "messages": [{"role": "user",
                      "content": "What is the weather in Moscow? Use the tool."}],
        "tools": [_PROBE_TOOL],
    }
    try:
        async with httpx.AsyncClient(timeout=CAPABILITY_TIMEOUT) as c:
            r = await c.post(f"{url}/chat/completions", json=payload, headers=headers)
    except httpx.TimeoutException:
        return {"ok": False, "tool_calls": False, "reason": "timeout",
                "detail": _("err_timeout", sec=CAPABILITY_TIMEOUT)}
    except Exception as e:
        return {"ok": False, "tool_calls": False, "reason": "unreachable",
                "detail": str(e)}

    if r.status_code != 200:
        # A server without tool support usually answers 400/422 with a clear
        # message. Show theirs — it is more useful than our paraphrase.
        return {"ok": False, "tool_calls": False, "reason": f"http_{r.status_code}",
                "detail": r.text[:300]}
    try:
        msg = r.json()["choices"][0]["message"]
    except Exception as e:
        return {"ok": False, "tool_calls": False, "reason": "bad_response",
                "detail": _("err_not_openai", err=e)}

    if msg.get("tool_calls"):
        return {"ok": True, "tool_calls": True, "reason": "ok",
                "detail": msg["tool_calls"][0].get("function", {}).get("name", "")}

    # 200, but no tool was called. Common on servers without tool support: the
    # call arrives as text in content, which the agent cannot parse.
    content = (msg.get("content") or "").strip()
    return {"ok": False, "tool_calls": False, "reason": "no_tool_calls",
            "detail": content[:300] or _("err_empty_reply")}


def explain_not_found() -> str:
    """
    The first-run text for when discover() found nothing.

    The point is not "nothing found" but "here is what to check". The common
    case: the server is running and opens fine from the host, but listens only
    on 127.0.0.1 — a socket unreachable from the sandbox by design. The user is
    certain everything works, and is technically right.
    """
    hosts = ", ".join(runtime_env.host_candidates())
    ports = ", ".join(f"{p} ({n})" for p, n in KNOWN_PORTS)
    return (
        f"{_('nf_title')}\n\n"
        f"{runtime_env.sandbox_hint()}\n\n"
        f"{_('nf_hosts', hosts=hosts)}\n"
        f"{_('nf_ports', ports=ports)}\n\n"
        f"{_('nf_localhost')}\n"
        f"{_('nf_ollama')}\n"
        f"{_('nf_lmstudio')}\n"
        f"{_('nf_llamacpp')}\n"
        f"{_('nf_vllm')}\n\n"
        f"{_('nf_manual')}"
    )


def _write_config(cfg: dict) -> None:
    """
    Write config.yaml and close it to everyone else.

    The chmod is not a formality: switch_to() puts a cloud provider's api_key in
    this file. The header of hermes/config.yaml itself says "Secrets go in
    ~/.hermes/.env, never here" — but Hermes reads the key from here, so it has
    nowhere else to go. Right next door ensure_gateway_env() dutifully sets
    .env to 0600, while the config kept the default umask and was readable by
    anyone.

    This matters most in the Docker target: README suggests
    `-v infiny-home:/root`, and that volume carries the key between machines
    along with the image.

    Permissions go on BEFORE the content is written — otherwise there is a
    window, however short, between creating the file and the chmod where the
    key sits in the open.
    """
    HERMES_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    HERMES_CONFIG.touch(mode=0o600, exist_ok=True)
    try:
        HERMES_CONFIG.chmod(0o600)
    except OSError:
        # Not Unix, or an unusual filesystem — write it anyway.
        pass
    HERMES_CONFIG.write_text(yaml.dump(cfg, allow_unicode=True, sort_keys=False))


def current_source() -> dict:
    """What is currently configured as the brain. Hermes' flat schema."""
    if not HERMES_CONFIG.exists():
        return {"configured": False, "reason": _("src_no_config")}
    try:
        cfg = yaml.safe_load(HERMES_CONFIG.read_text()) or {}
    except (OSError, yaml.YAMLError) as e:
        return {"configured": False, "reason": _("src_bad_config", err=e)}

    model_cfg = cfg.get("model") or {}
    base_url = str(model_cfg.get("base_url") or "").strip()
    model = str(model_cfg.get("default") or "").strip()
    if not base_url or not model:
        return {"configured": False, "reason": _("src_not_set")}
    return {
        "configured": True,
        "base_url": base_url,
        "model": model,
        "provider": str(model_cfg.get("provider") or "").strip(),
        # api_key is returned so that changing the model does not wipe it:
        # switch_to() writes whatever key it was given, and with the default
        # "no-key" switching models on a cloud endpoint would silently break
        # authentication.
        "api_key": str(model_cfg.get("api_key") or "").strip(),
    }


# The minimum Hermes considers workable for tool use
# (agent/model_metadata.py: MINIMUM_CONTEXT_LENGTH). Below it Hermes either
# refuses outright or works unreliably: tool schemas plus the system prompt
# consume a large fixed prefix before the conversation even starts.
HERMES_MINIMUM_CONTEXT = 64_000


def probe_context_length(base_url: str, model: str, api_key: str = "no-key") -> int | None:
    """
    How many tokens the server ACTUALLY allocated for the loaded model.

    Why we need this when Hermes can detect the window itself: it asks
    `/api/show`, which returns the **architectural maximum from the GGUF** —
    262,144 on all of our models, regardless of what the server was started
    with. Two consequences follow, both confirmed by measurement:
      * its own guard (window below the minimum) NEVER fires, because
        262144 >= 64000, so a user running a 32k window gets no warning at all;
      * Hermes grows the history against an imaginary limit while the server
        silently truncates.

    `/api/ps` reports fact rather than aspiration: what was allocated for the
    model that is already loaded. Hence the requirement on the caller to warm
    the model first (check_tool_calling does that for us) — otherwise the list
    is empty.

    Returns None when the server is not Ollama-compatible or did not answer.
    That is not an error but "could not measure", and the caller should simply
    write nothing to the config.
    """
    root = base_url.rstrip("/")
    if root.endswith("/v1"):
        root = root[:-3]
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        with httpx.Client(timeout=PROBE_TIMEOUT) as c:
            r = c.get(f"{root}/api/ps", headers=headers)
        if r.status_code != 200:
            return None
        loaded = r.json().get("models") or []
    except Exception:
        return None

    bare = model.strip()
    for m in loaded:
        name = str(m.get("name") or m.get("model") or "")
        # Ollama returns names as "gemma4:12b" or "…:latest" — compare both
        # sides so an implicit tag does not cause a miss.
        if name == bare or name.split(":")[0] == bare.split(":")[0]:
            ctx = m.get("context_length")
            if isinstance(ctx, int) and ctx > 0:
                return ctx
    return None


def switch_to(base_url: str, model: str, api_key: str = "no-key") -> dict:
    """
    Point Infiny at the given OpenAI-compatible endpoint.

    Always provider "custom": by Hermes' own documentation the ollama/vllm/
    llamacpp aliases map onto custom anyway, and we set base_url explicitly, so
    there is nothing to gain by distinguishing them in the config.
    """
    base_url = base_url.rstrip("/")
    try:
        cfg = yaml.safe_load(HERMES_CONFIG.read_text()) if HERMES_CONFIG.exists() else {}
        cfg = cfg or {}
    except (OSError, yaml.YAMLError) as e:
        return {"ok": False, "error": _("err_config_read", err=e)}

    model_cfg = cfg.setdefault("model", {})
    model_cfg["default"] = model
    model_cfg["provider"] = "custom"
    model_cfg["base_url"] = base_url
    model_cfg["api_key"] = api_key

    # Tell Hermes the TRUTH about the context window. Without this it takes the
    # architectural maximum from the GGUF (262,144 on our models) and behaves as
    # if space were unlimited: history compression kicks in at the wrong time,
    # and its own minimum check never fires at all.
    #
    # Measured across 6 tasks (gemma4:12b/low): pass rate is unaffected, but the
    # worst case improves fourfold — 817s down to 197s, and 31,826 response
    # tokens down to 7,074. The model either solves it quickly or gives up
    # quickly, instead of grinding at the edge of an overflow.
    #
    # When we could not measure (not Ollama, or the server stayed quiet) we
    # DELETE the key rather than leave it as it was. The difference is
    # fundamental, and the first version of this got it wrong.
    #
    # "Leave it alone" sounds careful, but when switching sources it preserves a
    # number belonging to the PREVIOUS model. Caught live on 2026-09-02: the Box
    # was running qwen3.5:9b (65,536), we switched to mistral-small-latest, and
    # 65,536 stayed in the config even though Mistral's window is 256,000.
    # Hermes would have believed our number and used a quarter of what was
    # available; going the other way (large model to small) it would have
    # overflowed the window instead.
    #
    # An absent key costs nothing here: for cloud providers Hermes works the
    # window out itself, and better than we can — it looks for it in /v1/models
    # under twelve possible field names (context_length, max_model_len,
    # n_ctx_train and so on). Verified against Mistral: it returns
    # max_context_length: 256000 and Hermes picks it up. Our measurement exists
    # precisely for Ollama, which LIES through /api/show, returning the GGUF
    # architectural maximum instead of the allocated window.
    ctx = probe_context_length(base_url, model, api_key)
    if ctx:
        model_cfg["context_length"] = ctx
    else:
        model_cfg.pop("context_length", None)

    # A previous version also wrote providers: {...}. That is a valid Hermes
    # schema, but keeping both at once reliably produces a config with two
    # sources where which one won is anyone's guess. Keep one.
    cfg.pop("providers", None)

    try:
        _write_config(cfg)
    except OSError as e:
        return {"ok": False, "error": _("err_config_write", err=e)}

    return {"ok": True, "base_url": base_url, "model": model,
            "context_length": ctx,
            "context_too_small": bool(ctx and ctx < HERMES_MINIMUM_CONTEXT),
            "gateway": restart_gateway()}


# Thinking levels Hermes understands (hermes_cli/config.py). An empty string
# means the provider default; we do not offer it in the CLI, because explaining
# the difference between "default" and "none" buys the user nothing.
REASONING_LEVELS = ("none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra")


def get_reasoning() -> str:
    """Current thinking level from config.yaml. Empty when unset."""
    try:
        cfg = yaml.safe_load(HERMES_CONFIG.read_text()) or {}
    except (OSError, yaml.YAMLError):
        return ""
    return str((cfg.get("agent") or {}).get("reasoning_effort") or "").strip()


def set_reasoning(level: str) -> dict:
    """
    Change the thinking level and restart the gateway.

    Why this is a setting rather than a constant: with `none` the agent breaks
    on both models we tested, and differently — qwen3.5:9b writes out a plan and
    ends its turn, gemma4:12b emits the tool call in a format Ollama's parser
    cannot read. `low` fixes both. But above low, latency grows on a small model
    and the idle-loop risk returns — the very thing thinking was once turned off
    for. There is no single right value, so the user decides rather than us.
    """
    if level not in REASONING_LEVELS:
        return {"ok": False, "error": _("err_bad_level", level=level)}
    try:
        cfg = yaml.safe_load(HERMES_CONFIG.read_text()) if HERMES_CONFIG.exists() else {}
        cfg = cfg or {}
    except (OSError, yaml.YAMLError) as e:
        return {"ok": False, "error": _("err_config_read", err=e)}

    cfg.setdefault("agent", {})["reasoning_effort"] = level
    try:
        _write_config(cfg)
    except OSError as e:
        return {"ok": False, "error": _("err_config_write", err=e)}

    return {"ok": True, "level": level, "gateway": restart_gateway()}


def ensure_gateway_env() -> None:
    """
    Append to ~/.hermes/.env whatever the CLI needs to reach Hermes at all.

    BOTH variables are required, which is not obvious:
      API_SERVER_ENABLED=true — turns on the OpenAI-compatible server on :8642.
                                Without it there is no endpoint whatsoever.
      API_SERVER_KEY          — the Bearer token; per Hermes' documentation the
                                server refuses to start without one.

    A freshly built Box had neither. On the development machine .env had been
    created long ago by the Hermes setup wizard, and in the image there was
    nothing to create it. The symptom misled: the gateway answers 401, the CLI
    stays silent, and it reads as "the agent is broken". I first added only the
    key and got "Invalid API key" — because the server was not enabled at all.

    The key is generated per installation. Baking a shared one into the image is
    not an option: it would be identical for everyone who downloads the Box.

    The third variable, SEARXNG_URL, is about search and is just as mandatory.
    Without a provider, Hermes' built-in web_search does not merely fail — it
    disappears from the tool list, silently cut by the check_fn gate. In that
    state the agent honestly says "I have no search" and then makes things up.
    Verified 2026-08-13: this single line gives web_search and web_extract back
    to the model. The address is fixed: SearXNG lives inside the Box and is
    started by wsl/infiny-start.sh on 127.0.0.1:8888.
    """
    env_file = HERMES_HOME / ".env"
    try:
        HERMES_HOME.mkdir(parents=True, exist_ok=True)
        text = env_file.read_text() if env_file.exists() else ""
        add = []
        if "API_SERVER_ENABLED=" not in text:
            add.append("API_SERVER_ENABLED=true")
        if "API_SERVER_KEY=" not in text:
            add.append(f"API_SERVER_KEY={secrets.token_hex(32)}")
        if "SEARXNG_URL=" not in text:
            add.append("SEARXNG_URL=http://127.0.0.1:8888")
        if not add:
            return
        with env_file.open("a") as f:
            if text and not text.endswith("\n"):
                f.write("\n")
            f.write("\n".join(add) + "\n")
        env_file.chmod(0o600)
    except OSError:
        # Do not raise: we will try to start the gateway anyway, and the failure
        # will surface in wait_for_gateway. Dying quietly here is worse than
        # failing loudly there.
        pass


def gateway_key() -> str:
    """The gateway Bearer token from ~/.hermes/.env. Empty string if absent."""
    try:
        for line in (HERMES_HOME / ".env").read_text().splitlines():
            if line.startswith("API_SERVER_KEY="):
                return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return ""


def _port_is_free(port: int = GATEWAY_PORT, timeout_s: float = 15.0) -> bool:
    """
    Wait until the port is genuinely free after killing the old gateway.

    Without this wait, restarting breaks in exactly the scenario it exists for —
    changing the model. `pkill` returns immediately, the process is still dying,
    the socket is still held, the new gateway starts and dies with
    `Could not bind 127.0.0.1:8642: address already in use`, then exits. From
    outside this looks like "the wizard said done but the agent does not
    answer", and it takes a long time to find, because the port IS listening.
    """
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return True
        time.sleep(0.3)
    return False


def restart_gateway() -> dict:
    """
    Restart the Hermes gateway so a new config takes effect.

    Learned the hard way, and easy to break again:
      1. The command is `hermes gateway run` on :8642, NOT `hermes server` on
         :8787. The latter belongs to an architecture that no longer exists.
      2. There must never be two gateways at once. The second does not "fight"
         for the port — it fails cleanly with address already in use and exits.
         But from outside that is indistinguishable from a working system,
         because the first one is holding the port.
      3. Between killing the old one and starting the new one you MUST wait for
         the port to be released; see _port_is_free().
    The launch happens from HERMES_HOME: the gateway reads .env relative to its
    working directory, and without that the Bearer key comes out empty.
    """
    ensure_gateway_env()

    # Under a supervisor, systemd owns restarts and reaching around it by hand
    # is NOT allowed. The previous version always did pkill + nohup — and on a
    # Box with units that produced precisely the race we were escaping: the
    # wizard killed the service, systemd started its own three seconds later,
    # our nohup started a second one, both fought over :8642, and the agent's
    # request landed in the dying one. From outside: "Remote end closed
    # connection without response" immediately after a successful model setup.
    # Caught by the acceptance suite 2026-08-25.
    if Path("/run/systemd/system").is_dir():
        r = subprocess.run(["systemctl", "restart", "infiny-gateway"],
                           check=False, timeout=30, capture_output=True, text=True)
        if r.returncode == 0:
            return {"restarted": True, "via": "systemd",
                    "log": "journalctl -u infiny-gateway"}
        # No unit (a Box built without one) — fall through to the manual path.

    subprocess.run(["pkill", "-f", "hermes gateway run"], check=False, timeout=10)
    freed = _port_is_free()
    # --replace is mandatory. Hermes keeps its OWN instance lock, and it
    # survives pkill: the process is dead, the lock remains, and the new gateway
    # refuses to start, saying "Use 'hermes gateway run --replace' to
    # auto-replace". From outside this reads as "the gateway did not come up"
    # with no explanation, and I spent more time fighting that lock by hand than
    # it would have taken to read its own hint.
    subprocess.run(
        "setsid nohup hermes gateway run --replace "
        ">/tmp/hermes-gateway.log 2>&1 </dev/null &",
        shell=True, cwd=str(HERMES_HOME), check=False, timeout=10,
    )
    return {"restarted": True, "via": "nohup", "port_freed": freed,
            "log": "/tmp/hermes-gateway.log"}


async def wait_for_gateway(url: str, timeout_s: float = 60.0) -> bool:
    """
    Wait until the gateway actually starts serving requests.

    The request carries the Bearer key, and ONLY 200 counts as success.

    A previous version also accepted 401 — "the server is up, it just wants a
    key". That produced a false "Infiny is online" twice in one evening:
      * when the API server never came up at all because aiohttp was missing,
        and the 401 came from the gateway stub;
      * when the new gateway died on an occupied port and the 401 came from the
        old one, still dying.
    A check you can pass without working is not a check. When there is no key we
    honestly return False: without it the CLI gets nothing anyway.
    """
    key = gateway_key()
    if not key:
        return False
    headers = {"Authorization": f"Bearer {key}"}
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s
    async with httpx.AsyncClient(timeout=2.0) as c:
        while loop.time() < deadline:
            try:
                if (await c.get(url, headers=headers)).status_code == 200:
                    return True
            except Exception:
                pass
            await asyncio.sleep(0.5)
    return False
