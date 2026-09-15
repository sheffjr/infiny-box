"""Conversation sessions — persisted so history survives across CLI runs.

Each session is a JSON file under ~/.infiny/sessions/<id>.json holding the
message list (OpenAI role/content dicts) plus metadata. The full message list
is what gives the agent real conversational memory: every turn we resend the
whole thread, so Hermes sees the context it replied to earlier.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

SESS_DIR = Path.home() / ".infiny" / "sessions"


def _now() -> float:
    return time.time()


@dataclass
class Session:
    id: str
    title: str = "new session"
    created: float = field(default_factory=_now)
    updated: float = field(default_factory=_now)
    messages: list[dict] = field(default_factory=list)
    last_usage: dict = field(default_factory=dict)   # tokens for the most recent turn
    total_tokens: int = 0                             # cumulative for this session

    # ── lifecycle ───────────────────────────────────────────────────────────
    @classmethod
    def new(cls) -> "Session":
        return cls(id=time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4])

    @property
    def path(self) -> Path:
        return SESS_DIR / f"{self.id}.json"

    def add_user(self, text: str) -> None:
        self.messages.append({"role": "user", "content": text})
        if self.title == "new session":
            self.title = (text[:48] + "…") if len(text) > 48 else text

    def add_assistant(self, text: str) -> None:
        self.messages.append({"role": "assistant", "content": text})

    def add_usage(self, usage: dict) -> None:
        self.last_usage = usage
        self.total_tokens = usage.get("total_tokens", self.total_tokens)

    def turns(self) -> int:
        return sum(1 for m in self.messages if m["role"] == "user")

    # ── persistence ─────────────────────────────────────────────────────────
    def save(self) -> None:
        """
        Write the session atomically: temporary file first, then rename.

        `write_text` truncates the file to zero and only then writes. A power
        cut, Ctrl+C or `kill -9` inside that window left truncated JSON on disk —
        and `--resume` then failed with a bare traceback on EVERY launch, because
        load() did not guard its parse. The only way out was deleting the right
        file by hand.

        `os.replace` is atomic within one filesystem: either the old version or
        the new one, with no state in between.
        """
        SESS_DIR.mkdir(parents=True, exist_ok=True)
        self.updated = _now()
        payload = json.dumps({
            "id": self.id, "title": self.title,
            "created": self.created, "updated": self.updated,
            "messages": self.messages,
            "last_usage": self.last_usage, "total_tokens": self.total_tokens,
        }, ensure_ascii=False, indent=2)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, self.path)

    @classmethod
    def load(cls, sid: str) -> "Session | None":
        """
        Read a session. A corrupted file is None, not an exception.

        list() already guarded its parse and load() did not, and the mismatch
        hurt: a damaged session showed up in the list quite happily, and opening
        it took the CLI down with a traceback. For `--resume`, which picks the
        latest one itself, that meant a broken launch until the file was deleted
        by hand.

        Returning None is more correct than raising: the caller already knows how
        to handle it — the same way it handles a session that does not exist.
        """
        p = SESS_DIR / f"{sid}.json"
        if not p.exists():
            return None
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeDecodeError):
            return None
        if not isinstance(d, dict) or "id" not in d:
            return None
        return cls(id=d["id"], title=d.get("title", "session"),
                   created=d.get("created", _now()), updated=d.get("updated", _now()),
                   messages=d.get("messages", []),
                   last_usage=d.get("last_usage", {}), total_tokens=d.get("total_tokens", 0))

    @classmethod
    def load_latest(cls) -> "Session | None":
        items = cls.list()
        return cls.load(items[0]["id"]) if items else None

    @staticmethod
    def list() -> list[dict]:
        """Session metadata, newest first."""
        if not SESS_DIR.exists():
            return []
        out = []
        for p in SESS_DIR.glob("*.json"):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
                out.append({"id": d["id"], "title": d.get("title", "session"),
                            "updated": d.get("updated", 0),
                            "turns": sum(1 for m in d.get("messages", []) if m["role"] == "user")})
            except Exception:
                continue
        return sorted(out, key=lambda x: x["updated"], reverse=True)
