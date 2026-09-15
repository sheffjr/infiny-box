"""HermesClient — the CLI's link to the Infiny brain.

Speaks Hermes gateway's `/v1/runs` API on :8642 (Bearer auth) — NOT
`/v1/chat/completions`. This matters: only `/v1/runs` wires a real approval
notify callback (`register_gateway_notify`, api_server.py ~line 5100) into
the agent's dangerous-command gate (tools/approval.py). `/v1/chat/completions`
never registers that callback, so a flagged command there just fails closed
with an unresolvable "pending_approval" — there is no way to say yes. `/v1/runs`
gives us a real `approval.request` SSE event we can answer via
`POST /v1/runs/{run_id}/approval`. This is also the only path that emits
`reasoning.available` events, if reasoning is ever turned back on.

We send the FULL conversation history each turn (`conversation_history` +
`input`), plus a stable session id, so Hermes keeps memory continuity.

Event stream (yielded by `stream_run()`):
    ("thinking",  None)        first — request accepted, nothing back yet
    ("token",     str)         a chunk of assistant text
    ("tool",      dict)        tool lifecycle: {toolCallId, tool, label, emoji, status}
                                status is "running" or "completed"
    ("reasoning", str)         a chunk of model reasoning/thinking, if the
                                server-side config ever enables it (currently off)
    ("usage",     dict)        token accounting: {prompt_tokens, completion_tokens, total_tokens}
    ("error",     str)         something went wrong (human-readable)
    ("done",      str)         final — full assistant text

Approval: when the agent hits a flagged command, the server emits an
`approval.request` event. We call `approval_handler(event_dict)` — supplied
by the caller — synchronously; it must return one of "once"/"session"/
"always"/"deny". We POST that choice back before continuing to read events.

Cancellation: raise KeyboardInterrupt inside the consuming loop; we best-effort
POST /v1/runs/{run_id}/stop so the agent actually stops running server-side
(closing our SSE connection alone does NOT stop it — the run continues in
the background since /v1/runs is an async job, unlike the old synchronous
chat-completions stream).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable, Iterator

import httpx

from . import config_ref
from .i18n import t as _t

HERMES_BASE = "http://127.0.0.1:8642"
HERMES_RUNS = f"{HERMES_BASE}/v1/runs"
HERMES_MODELS = f"{HERMES_BASE}/v1/models"

# Read from ~/.hermes/config.yaml rather than hardcoded: in Phase 1 the user
# picks the model in the first-run wizard, and any name baked in here simply
# does not exist on their machine. This module is imported AFTER the wizard has
# run (see cli.py), so the value comes from a fresh config.
HERMES_MODEL = config_ref.configured_model()

# Native context window, keyed by Ollama model tag. Not exposed by /v1/models,
# so we track the ones we run — see project memory for how this was verified.
MODEL_CONTEXT: dict[str, int] = {
    "qwen3-vl:4b": 262_144,
}


SOUL_PATH = Path.home() / ".hermes" / "SOUL.md"


def load_soul() -> str:
    """Infiny's persona. The gateway API path does NOT auto-inject SOUL.md (that
    is a CLI-only Hermes feature), so we must pass it as the run's `instructions`
    (→ system prompt) or the model answers as the raw base model. Read fresh per
    request so edits to SOUL.md take effect without restarting the CLI."""
    try:
        return SOUL_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def load_api_key() -> str:
    """Bearer token from env or ~/.hermes/.env (API_SERVER_KEY)."""
    if key := os.environ.get("API_SERVER_KEY"):
        return key
    env_path = Path.home() / ".hermes" / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("API_SERVER_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


class HermesClient:
    def __init__(self, model: str = HERMES_MODEL) -> None:
        self.model = model
        self.key = load_api_key()

    def _headers(self, extra: dict | None = None) -> dict:
        h = {"Authorization": f"Bearer {self.key}"} if self.key else {}
        if extra:
            h.update(extra)
        return h

    # ── status ──────────────────────────────────────────────────────────────
    def is_up(self, timeout: float = 2.0) -> bool:
        try:
            r = httpx.get(HERMES_MODELS, headers=self._headers(), timeout=timeout)
            return r.status_code == 200
        except Exception:
            return False

    def models(self, timeout: float = 3.0) -> list[str]:
        try:
            r = httpx.get(HERMES_MODELS, headers=self._headers(), timeout=timeout)
            data = r.json()
            return [m.get("id", "") for m in data.get("data", [])]
        except Exception:
            return []

    def context_window(self) -> int | None:
        """Known native context length for the active model, if we track it."""
        return MODEL_CONTEXT.get(self.model)

    # ── streaming runs (with real approval support) ────────────────────────
    def stream_run(
        self,
        messages: list[dict],
        session_id: str,
        approval_handler: Callable[[dict], str],
    ) -> Iterator[tuple[str, object]]:
        """Create a run for the latest user turn and stream its events.

        *messages* is the full history including the new user message last —
        everything before it becomes `conversation_history`, matching how the
        rest of the app already builds `session.messages`.
        """
        if not messages:
            return
        history, user_msg = messages[:-1], messages[-1].get("content", "")
        payload = {"model": self.model, "input": user_msg,
                   "conversation_history": history, "session_id": session_id}
        if soul := load_soul():
            payload["instructions"] = soul
        headers = self._headers({"Content-Type": "application/json"})
        full = ""
        run_id = None
        # The stream carries no call id. Measured on the wire 2026-09-14:
        # tool.started is {run_id, timestamp, tool, preview} and tool.completed
        # is {run_id, timestamp, tool, duration, error} — the tool NAME is the
        # only identifier offered, and three consecutive `echo`s arrive as three
        # events all saying "terminal".
        #
        # Keyed by name, every terminal call in a turn lands on the same row and
        # overwrites the last: a thirty-command Docker install showed the user
        # one line that kept changing, and the record of what had been run to
        # their machine was gone. (The gateway does emit an authoritative
        # tool.start carrying a stable tool_id, but on a different surface — the
        # desktop socket — not on /v1/runs/{id}/events.)
        #
        # So synthesize an id from the timestamp and match completions FIFO,
        # which is what Hermes' own ACP adapter does with the same events.
        open_calls: dict[str, list[str]] = {}
        # Which step we are on goes into the error text. It sounds like a
        # detail, but on 2026-08-03 a user got a bare
        # "⚠ UnicodeDecodeError: ... byte 0xd1 in position 2", and that line did
        # not even reveal whose failure it was — ours, the gateway's or a
        # tool's. An evening went into it and produced nothing.
        stage = _t("stage_request")
        yield ("thinking", None)
        try:
            with httpx.Client(timeout=httpx.Timeout(600.0, connect=5.0)) as client:
                r = client.post(HERMES_RUNS, json=payload, headers=headers)
                if r.status_code not in (200, 202):
                    yield ("error", f"Hermes {r.status_code}: {r.text[:300]}")
                    yield ("done", full)
                    return
                run_id = r.json().get("run_id")
                events_url = f"{HERMES_RUNS}/{run_id}/events"
                stage = _t("stage_stream")
                with client.stream("GET", events_url,
                                    headers=self._headers({"Accept": "text/event-stream"})) as resp:
                    for line in resp.iter_lines():
                        if not line.startswith("data:"):
                            continue
                        chunk = line[5:].strip()
                        if not chunk:
                            continue
                        try:
                            obj = json.loads(chunk)
                        except json.JSONDecodeError:
                            continue
                        etype = obj.get("event")
                        if etype == "message.delta":
                            tok = obj.get("delta", "")
                            full += tok
                            yield ("token", tok)
                        elif etype == "tool.started":
                            name = obj.get("tool") or "tool"
                            cid = f"{name}@{obj.get('timestamp') or len(open_calls)}"
                            open_calls.setdefault(name, []).append(cid)
                            yield ("tool", {"toolCallId": cid, "tool": name,
                                            "label": obj.get("preview") or name,
                                            "emoji": "", "status": "running"})
                        elif etype == "tool.completed":
                            name = obj.get("tool") or "tool"
                            queue = open_calls.get(name)
                            # FIFO: tools finish in the order they started. If a
                            # completion arrives with nothing open — a tool that
                            # began before we attached — fall back to its own
                            # timestamp rather than colliding with a live row.
                            cid = queue.pop(0) if queue else f"{name}@{obj.get('timestamp')}"
                            yield ("tool", {"toolCallId": cid, "tool": name,
                                            "label": name, "emoji": "", "status": "completed"})
                        elif etype == "reasoning.available":
                            yield ("reasoning", obj.get("text", ""))
                        elif etype == "approval.request":
                            stage = _t("stage_approval")
                            choice = approval_handler(obj)
                            stage = _t("stage_stream")
                            try:
                                client.post(f"{HERMES_RUNS}/{run_id}/approval",
                                            json={"choice": choice}, headers=headers)
                            except Exception:
                                pass
                        elif etype == "run.completed":
                            full = obj.get("output", full) or full
                            if raw_usage := obj.get("usage"):
                                # /v1/runs names these input_tokens/output_tokens,
                                # unlike the OpenAI-shape prompt_tokens/completion_tokens
                                # the rest of the app expects — normalize here.
                                yield ("usage", {
                                    "prompt_tokens": raw_usage.get("input_tokens", 0),
                                    "completion_tokens": raw_usage.get("output_tokens", 0),
                                    "total_tokens": raw_usage.get("total_tokens", 0),
                                })
                            yield ("done", full)
                            return
                        elif etype == "run.failed":
                            yield ("error", str(obj.get("error", "run failed")))
                            yield ("done", full)
                            return
                        elif etype == "run.cancelled":
                            yield ("done", full)
                            return
        except httpx.ConnectError:
            yield ("error", "connect")
            yield ("done", full)
        except KeyboardInterrupt:
            if run_id:
                try:
                    httpx.post(f"{HERMES_RUNS}/{run_id}/stop", headers=headers, timeout=3.0)
                except Exception:
                    pass
            yield ("done", full)
            raise
        except Exception as e:
            yield ("error", _t("stage_error", kind=type(e).__name__,
                               stage=stage, err=e))
            yield ("done", full)
