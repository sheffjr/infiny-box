"""Plain fallback — stdlib only, zero third-party deps.

This is the lifeline. If rich/prompt_toolkit aren't installed (fresh recovery
shell, broken venv, SSH into a half-booted box), Infiny is still reachable here
using nothing but Python's standard library. Same gateway, same brain — just a
minimal skin. Triggered by `--plain`, or automatically if the rich UI can't load.
"""
import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path

from . import config_ref
from .i18n import t as _, get_lang, set_lang, LANGS

HERMES_URL = "http://127.0.0.1:8642/v1/chat/completions"
HERMES_MODELS = "http://127.0.0.1:8642/v1/models"

# Not a constant: the user picks the model, see config_ref. That module is
# stdlib-only, so the emergency mode stays an emergency mode.
HERMES_MODEL = config_ref.configured_model()


def _load_api_key() -> str:
    if key := os.environ.get("API_SERVER_KEY"):
        return key
    env_path = Path.home() / ".hermes" / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("API_SERVER_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


HERMES_KEY = _load_api_key()


def _auth(extra: dict | None = None) -> dict:
    h = {"Authorization": f"Bearer {HERMES_KEY}"} if HERMES_KEY else {}
    if extra:
        h.update(extra)
    return h


class C:
    A = "\033[38;5;180m"; DIM = "\033[2m"; B = "\033[1m"; R = "\033[0m"
    G = "\033[38;5;114m"; E = "\033[38;5;210m"; U = "\033[38;5;110m"


def col(s: str, c: str) -> str:
    return f"{c}{s}{C.R}" if sys.stdout.isatty() else s


def _get(url: str, timeout: int = 3):
    try:
        req = urllib.request.Request(url, headers=_auth())
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None


def is_up() -> bool:
    return _get(HERMES_MODELS) is not None


def print_status() -> None:
    up = is_up()
    print(col(_("plain_status_title"), C.A + C.B))
    mark = col("●", C.G) if up else col("○", C.E)
    print(_("plain_gateway_row", mark=mark) +
          (col(_("online"), C.G) if up else col(_("not_responding"), C.E)))
    if not up:
        print(col(_("plain_not_responding_hint"), C.E))
        print(col("    hermes gateway run", C.DIM))
    else:
        print(col(_("plain_ok"), C.G))
    print()


def _err_down() -> str:
    return col(_("plain_err_down"), C.E)


def print_help() -> None:
    print(col(_("plain_help_title"), C.A + C.B))
    for key in ("plain_help_help", "plain_help_status", "plain_help_lang",
                "plain_help_clear", "plain_help_exit"):
        print(col(_(key), C.DIM))
    print()


def ask(messages: list, stream: bool = True) -> str:
    """Send full history; stream tokens. Returns the assistant text."""
    payload = {"model": HERMES_MODEL, "messages": messages, "stream": stream}
    req = urllib.request.Request(
        HERMES_URL, data=json.dumps(payload).encode(),
        headers=_auth({"Content-Type": "application/json", "Accept": "text/event-stream"}),
    )
    full = ""
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            if stream:
                for raw in resp:
                    line = raw.decode(errors="replace").strip()
                    if not line.startswith("data:"):
                        continue
                    chunk = line[5:].strip()
                    if chunk == "[DONE]":
                        break
                    try:
                        obj = json.loads(chunk)
                    except json.JSONDecodeError:
                        continue
                    tok = obj.get("choices", [{}])[0].get("delta", {}).get("content", "")
                    if tok:
                        full += tok
                        sys.stdout.write(tok); sys.stdout.flush()
            else:
                obj = json.loads(resp.read().decode())
                full = obj.get("choices", [{}])[0].get("message", {}).get("content", "")
    except urllib.error.URLError:
        return _err_down()
    except Exception as e:
        return col(_("plain_error", e=e), C.E)
    return full


def repl() -> None:
    print(col("\n  ✦ Infiny CLI", C.A + C.B) + col(_("plain_subtitle"), C.DIM))
    if not is_up():
        print(_err_down())
    print(col(_("plain_hint"), C.DIM))
    history: list = []
    while True:
        try:
            msg = input(col("you › ", C.U)).strip()
        except (EOFError, KeyboardInterrupt):
            print(col(_("plain_bye"), C.DIM)); break
        if not msg:
            continue
        if msg in ("/exit", "/quit", "/q"):
            print(col(_("plain_bye"), C.DIM)); break
        if msg == "/help":
            print_help(); continue
        if msg == "/status":
            print_status(); continue
        if msg == "/clear":
            sys.stdout.write("\033[2J\033[H"); continue
        if msg.startswith("/lang"):
            parts = msg.split()
            if len(parts) > 1 and parts[1].lower() in LANGS:
                set_lang(parts[1].lower())
                print(col(_("plain_lang_set", code=parts[1].lower()), C.G))
            else:
                print(col(f"  {'/'.join(LANGS)}  (current: {get_lang()})", C.DIM))
            continue
        history.append({"role": "user", "content": msg})
        print(col("\ninfiny › ", C.A), end="")
        reply = ask(history, stream=True)
        history.append({"role": "assistant", "content": reply})
        print("\n")


def one_shot(text: str, stream: bool = True) -> None:
    out = ask([{"role": "user", "content": text}], stream=stream)
    if not stream:
        print(out)
    else:
        print()
