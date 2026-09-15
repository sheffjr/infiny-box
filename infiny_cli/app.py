"""Infiny CLI — the rich terminal application.

The control surface for the whole machine: panels, structure, a little life.
Streaming markdown, animated tool calls, live stats (cpu/ram/tokens) in the
status bar, `!command` straight to the shell, `@file` attachments, multi-line
input, fuzzy search across sessions — the same brain as the GUI (Hermes gateway
:8642), just a richer surface.
"""
from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path

import psutil
from rich.console import Console, Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text
from rich.live import Live
from rich.markup import escape
from rich import box

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style

from .client import HermesClient, HERMES_MODEL
from .session import Session
# Aliased to `_` (gettext convention) — `t` collides with the many local
# Table/Text/tool-dict variables named `t` throughout this file.
from .i18n import t as _, get_lang, set_lang, LANGS

# ── palette — taken from ui/index.html (#080807 / #c4aa82 / Inter) ────────────
ACCENT = "#c4aa82"
ACCENT2 = "#e8d9bd"      # light end of the header gradient
USER = "#7fa8d0"
OK = "#8fbf8f"
ERR = "#e0968c"
DIM = "grey50"

# How many reply lines to show in the live area while streaming.
# Deliberately below the height of any sensible window: once the Live content
# outgrows the screen, rich stops redrawing in place and reprints every frame.
# The full text is printed after streaming anyway.
_LIVE_TAIL_LINES = 12

INFINY_DIR = Path.home() / ".infiny"

# Command tokens stay Latin (like git/docker) regardless of interface
# language — switching keyboard layout for slash commands would be annoying.
# Descriptions come from i18n.t() so they follow the current language.
COMMAND_TOKENS = ["/help", "/status", "/mode", "/new", "/sessions", "/resume", "/history",
                   "/model", "/reasoning", "/soul", "/lang", "/retry", "/copy", "/clear",
                   "/heal", "/exit"]


def commands() -> dict[str, str]:
    return {
        "/help": _("cmd_help"), "/status": _("cmd_status"), "/mode": _("cmd_mode"),
        "/new": _("cmd_new"), "/sessions": _("cmd_sessions"), "/resume": _("cmd_resume"),
        "/history": _("cmd_history"), "/model": _("cmd_model"),
        "/reasoning": _("cmd_reasoning"), "/soul": _("cmd_soul"),
        "/lang": _("cmd_lang"), "/retry": _("cmd_retry"), "/copy": _("cmd_copy"),
        "/clear": _("cmd_clear"), "/heal": _("cmd_heal"), "/exit": _("cmd_exit"),
    }


# ── input: slash commands and @file mentions in one completer ─────────────────
class InfinyCompleter(Completer):
    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if text.startswith("/") and " " not in text:
            for cmd, desc in commands().items():
                if cmd.startswith(text):
                    yield Completion(cmd, start_position=-len(text), display=cmd, display_meta=desc)
            return
        at = text.rfind("@")
        if at == -1 or (at > 0 and not text[at - 1].isspace()):
            return
        frag = text[at + 1:]
        if " " in frag or "\n" in frag:
            return
        dirname = os.path.dirname(frag) or "."
        prefix = os.path.basename(frag)
        try:
            entries = sorted(os.listdir(dirname))
        except OSError:
            return
        for e in entries:
            if not e.startswith(prefix):
                continue
            full_path = os.path.join(dirname, e) if frag and os.path.dirname(frag) else e
            is_dir = os.path.isdir(os.path.join(dirname, e))
            yield Completion(full_path, start_position=-len(frag),
                              display=e + ("/" if is_dir else ""))


def _hex(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def _gradient(s: str, c1: str, c2: str, bold: bool = True) -> Text:
    r1, g1, b1 = _hex(c1)
    r2, g2, b2 = _hex(c2)
    n = max(len(s) - 1, 1)
    t = Text()
    for i, ch in enumerate(s):
        f = i / n
        r, g, b = (int(r1 + (r2 - r1) * f), int(g1 + (g2 - g1) * f), int(b1 + (b2 - b1) * f))
        t.append(ch, style=f"{'bold ' if bold else ''}#{r:02x}{g:02x}{b:02x}")
    return t


def _fmt_tok(n: int) -> str:
    return f"{n / 1000:.1f}k" if n >= 1000 else str(n)


class InfinyApp:
    def __init__(self, model: str = HERMES_MODEL) -> None:
        self.console = Console()
        self.client = HermesClient(model=model)
        self.session = Session.new()
        self.approval_mode = "manual"  # manual | auto | yolo — see _handle_approval()
        INFINY_DIR.mkdir(parents=True, exist_ok=True)
        psutil.cpu_percent(interval=None)  # prime the non-blocking counter
        self.ptk = PromptSession(
            history=FileHistory(str(INFINY_DIR / "history")),
            completer=InfinyCompleter(),
            complete_while_typing=True,
            style=Style.from_dict({"prompt": f"{USER} bold", "bottom-toolbar": f"{ACCENT} bg:#1b1b1b"}),
        )

    # ── entry point ─────────────────────────────────────────────────────────
    def run(self, resume: str | None = None) -> None:
        if resume is not None:
            loaded = Session.load(resume) if resume else Session.load_latest()
            if loaded:
                self.session = loaded
        self._banner()
        if self.session.messages:
            self.console.print(Text(_("continuing", title=self.session.title,
                                       turns=self.session.turns()), style=DIM))
        while True:
            try:
                text = self._read_input()
            except KeyboardInterrupt:
                continue
            except EOFError:
                break
            if not text:
                continue
            if text.startswith("!"):
                self._run_shell(text[1:].strip())
                continue
            if text.startswith("/"):
                if self._command(text) == "exit":
                    break
                continue
            self._send(text)
        self.console.print(Text(_("goodbye"), style=DIM))

    def _read_input(self) -> str:
        """One logical input; a trailing `\\` continues on the next line."""
        line = self.ptk.prompt([("class:prompt", "you › ")],
                                bottom_toolbar=self._toolbar, refresh_interval=1.0)
        parts = []
        while line.rstrip().endswith("\\"):
            parts.append(line.rstrip()[:-1])
            line = self.ptk.prompt([("class:prompt", "    … ")],
                                    bottom_toolbar=self._toolbar, refresh_interval=1.0)
        parts.append(line)
        return "\n".join(parts).strip()

    # ── UI: loading, banner, status bar ──────────────────────────────────────
    def _banner(self) -> None:
        with self.console.status(Text(f" {_('waking')}", style=DIM), spinner="dots", spinner_style=ACCENT):
            up = self.client.is_up()
        dot = "[#8fbf8f]●[/]" if up else "[#e0968c]○[/]"
        status = f"{dot}  {_('gateway_up') if up else _('gateway_down')}   ·   [{ACCENT}]{self.client.model}[/]"
        body = Group(
            _gradient("✦ INFINY", ACCENT, ACCENT2),
            Text(_("tagline"), style=DIM),
            Text(""),
            Text.from_markup(status),
            Text(""),
            Text.from_markup(_("hint")),
        )
        self.console.print()
        self.console.print(Panel(body, border_style=DIM, box=box.ROUNDED, padding=(1, 3)))
        if not up:
            self.console.print(Text(_("gateway_down_hint"), style=ERR))
        self.console.print()

    def _toolbar(self) -> FormattedText:
        cpu = psutil.cpu_percent(interval=None)
        ram = psutil.virtual_memory().percent
        clock = time.strftime("%H:%M:%S")
        ctx = self.client.context_window()
        tok_word = _("tokens")
        tok = f"  ·  {_fmt_tok(self.session.total_tokens)}/{_fmt_tok(ctx)} {tok_word}" if ctx else \
              (f"  ·  {_fmt_tok(self.session.total_tokens)} {tok_word}" if self.session.total_tokens else "")
        return FormattedText([("class:bottom-toolbar",
            f" ✦ infiny · {self.client.model} · {self.session.title} · {self.session.turns()} {_('turns')}"
            f"{tok}   ·   cpu {cpu:>4.1f}%  ram {ram:>4.1f}%  {clock}     {_('toolbar_hints')} ")])

    # ── sending a message and streaming the reply ────────────────────────────
    def _send(self, text: str) -> None:
        self.session.add_user(self._expand_mentions(text))
        full = self._stream()
        self.session.add_assistant(full)
        self.session.save()

    @staticmethod
    def _expand_mentions(text: str) -> str:
        """Inline the contents of @mentioned files so Hermes can see them."""
        extra = ""
        for m in re.finditer(r"(?<!\S)@(\S+)", text):
            fp = Path(m.group(1)).expanduser()
            if fp.is_file():
                try:
                    body = fp.read_text(encoding="utf-8", errors="replace")[:4000]
                    extra += f"\n\n--- @{m.group(1)} ---\n{body}"
                except Exception:
                    pass
        return text + extra if extra else text

    def _stream(self) -> str:
        full = ""
        tools: dict[str, dict] = {}  # toolCallId -> {label, emoji, done}
        usage: dict = {}
        reasoning = ""
        started_at = time.time()

        def view():
            parts: list = [_gradient("◆ infiny", ACCENT, ACCENT2, bold=True)]
            for tl in tools.values():
                prefix = f"{tl['emoji']} " if tl["emoji"] else ""
                if tl["done"]:
                    parts.append(Text(f"  ✓ {prefix}{tl['label']}", style=DIM))
                else:
                    parts.append(Spinner("dots", text=Text(f" {prefix}{tl['label']}", style=ACCENT), style=ACCENT))
            if reasoning and not full:
                parts.append(Text(f"  💭 {reasoning}", style=f"{DIM} italic"))
            if full:
                # THE TAIL ONLY, and this matters.
                #
                # rich.Live repaints its area by moving the cursor and assumes a
                # block of FIXED height. Put growing text inside it and the
                # moment that text outgrows the window, Live can no longer
                # repaint in place and starts printing afresh — twelve times a
                # second. The user sees dozens of copies of the same reply and
                # concludes the agent is stuck in a loop. Observed live on
                # 2026-08-02 in a Windows console: ~70 repeats for a 91-token
                # reply.
                #
                # So only the tail goes into Live, and the whole reply is printed
                # once after leaving it (Live is transient — it erases itself).
                tail = full.splitlines()[-_LIVE_TAIL_LINES:]
                parts.append(Markdown("\n".join(tail), code_theme="monokai"))
            elif not tools or all(tl["done"] for tl in tools.values()):
                parts.append(Spinner("dots", text=Text(f" {_('thinking')}", style=DIM), style=ACCENT))
            elapsed = time.time() - started_at
            parts.append(Text(
                f"  {elapsed:.0f}s   ·   cpu {psutil.cpu_percent(interval=None):>4.1f}%  "
                f"ram {psutil.virtual_memory().percent:>4.1f}%   ·   {_('mode_label')} {self.approval_mode}"
                f"   ·   {_('cancel_hint')}",
                style=DIM))
            return Group(*parts)

        self.console.print()
        interrupted = False
        # transient=True: the area is erased on exit and the full reply is
        # printed below exactly once. With transient=False the last Live frame
        # stayed on screen and printing the full text would duplicate it.
        with Live(view(), console=self.console, refresh_per_second=12,
                  transient=True, vertical_overflow="crop") as live:
            def approval_handler(event: dict) -> str:
                return self._handle_approval(live, event)

            try:
                for ev, val in self.client.stream_run(self.session.messages, self.session.id, approval_handler):
                    if ev == "token":
                        full += val
                    elif ev == "reasoning":
                        reasoning += val
                    elif ev == "tool":
                        tid = val.get("toolCallId") or val.get("tool") or str(len(tools))
                        if val.get("status") == "running":
                            tools[tid] = {"label": val.get("label") or val.get("tool") or "tool",
                                         "emoji": val.get("emoji", ""), "done": False}
                        else:  # completed
                            if tid in tools:
                                tools[tid]["done"] = True
                            else:
                                tools[tid] = {"label": val.get("tool") or "tool", "emoji": "", "done": True}
                    elif ev == "usage":
                        usage = val
                    elif ev == "error":
                        for t in tools.values():
                            t["done"] = True
                        if val == "connect":
                            full += _("connect_error")
                        else:
                            full += f"\n\n⚠ {val}"
                    elif ev == "done":
                        for t in tools.values():
                            t["done"] = True
                        full = val or full
                    live.update(view())
            except KeyboardInterrupt:
                interrupted = True

        # The final render happens outside Live, as ordinary printing. Any
        # length is safe here: the console simply scrolls, exactly as it does for
        # the output of any other command.
        for tl in tools.values():
            prefix = f"{tl['emoji']} " if tl["emoji"] else ""
            self.console.print(Text(f"  ✓ {prefix}{tl['label']}", style=DIM))
        if full:
            self.console.print(Markdown(full, code_theme="monokai"))

        if interrupted:
            self.console.print(Text(_("cancelled"), style=DIM))
        if usage:
            self.session.add_usage(usage)
            p, c = usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
            self.console.print(Text(_("usage_line", elapsed=time.time() - started_at,
                                       p=_fmt_tok(p), c=_fmt_tok(c),
                                       total=_fmt_tok(usage.get("total_tokens", p + c))), style=DIM))
        else:
            self.console.print(Text(f"  {time.time() - started_at:.1f}s", style=DIM))
        self.console.print(Rule(style=DIM))
        return full or _("no_reply")

    # ── accept/deny ──────────────────────────────────────────────────────────
    def _handle_approval(self, live: Live, event: dict) -> str:
        """Called synchronously when Hermes flags a command and needs a decision.

        Returns one of "once" / "session" / "always" / "deny" — POSTed back by
        the client to /v1/runs/{id}/approval. Behaviour depends on self.approval_mode:
          - "yolo":   never blocks, answers "once" instantly (overnight runs).
          - "auto":   answers "session" instantly — Hermes then won't ask again
                      for this *pattern* this session (dedup happens server-side),
                      so this is a "ask once per kind of risky thing" mode.
          - "manual": always stops and asks you, default.
        """
        desc = event.get("description") or event.get("command", "")
        command = event.get("command", "")

        if self.approval_mode == "yolo":
            self.console.print(Text(_("yolo_note", desc=desc), style=DIM))
            return "once"
        if self.approval_mode == "auto":
            choices = event.get("choices", [])
            scope = "session" if "session" in choices else "once"
            self.console.print(Text(_("auto_note", scope=scope, desc=desc), style=DIM))
            return scope

        # manual — stop the Live render, prompt for real, then resume it.
        live.stop()
        try:
            choices = event.get("choices") or ["once", "deny"]
            keymap = {"once": "o", "session": "s", "always": "a", "deny": "d"}
            body = Text()
            body.append(f"{desc}\n\n", style="")
            if command:
                body.append("$ ", style=ACCENT)
                body.append(command, style="bold")
            self.console.print()
            self.console.print(Panel(body, title=f"[bold]{_('approval_title')}[/bold]",
                                     border_style=ERR, title_align="left", box=box.ROUNDED))
            # escape(), because console.input() parses rich markup and the key
            # hints are bracketed single letters — which are exactly rich's
            # style abbreviations. "[o] once  [s] session  [a] always  [d] deny"
            # rendered as: overline from "once", strikethrough from "session",
            # dim from "deny", none of the tags ever closed — and the letters
            # themselves swallowed as markup, so the prompt showed no keys at
            # all. On the one screen where the user approves a dangerous
            # command.
            hint = "  ".join(f"[{keymap.get(c, '?')}] {c}" for c in choices)
            hint = escape(hint)
            reverse = {v: k for k, v in keymap.items()}
            while True:
                try:
                    ans = self.console.input(_("approval_prompt", hint=hint)).strip().lower()
                except (EOFError, KeyboardInterrupt):
                    ans = "deny"
                if ans == "":
                    choice = "deny"
                elif ans in reverse and reverse[ans] in choices:
                    choice = reverse[ans]
                elif ans in choices:
                    choice = ans
                else:
                    self.console.print(Text(_("approval_bad_choice"), style=ERR))
                    continue
                break
            self.console.print(Text(f"  → {choice}\n", style=OK if choice != "deny" else ERR))
            return choice
        finally:
            live.start()

    # ── !shell, straight through ───────────────────────────────────────────
    def _run_shell(self, cmd: str) -> None:
        if not cmd:
            return
        self.console.print(Text.assemble(("  $ ", ACCENT), (cmd, "bold")))
        try:
            proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True, bufsize=1)
            for line in proc.stdout:
                self.console.print("  " + line.rstrip())
            rc = proc.wait()
            self.console.print(Text(f"  exit {rc}", style=OK if rc == 0 else ERR))
        except Exception as e:
            self.console.print(Text(f"  ⚠ {e}", style=ERR))
        self.console.print(Rule(style=DIM))

    # ── slash commands ───────────────────────────────────────────────────────
    def _command(self, text: str) -> str | None:
        parts = text.split()
        cmd, args = parts[0].lower(), parts[1:]
        if cmd in ("/exit", "/quit", "/q"):
            return "exit"
        if cmd == "/help":
            self._help()
        elif cmd == "/status":
            self._status()
        elif cmd == "/mode":
            self._mode(args)
        elif cmd == "/lang":
            self._lang(args)
        elif cmd == "/new":
            self.session = Session.new()
            self.console.print(Text(_("new_dialog"), style=ACCENT))
        elif cmd == "/sessions":
            self._sessions(args)
        elif cmd == "/resume":
            s = Session.load(args[0]) if args else Session.load_latest()
            if s:
                self.session = s
                self.console.print(Text(_("returned_to", title=s.title, turns=s.turns()), style=OK))
            else:
                self.console.print(Text(_("nothing_to_return"), style=ERR))
        elif cmd == "/history":
            self._history()
        elif cmd == "/model":
            self._model(args)
        elif cmd in ("/reasoning", "/think"):
            self._reasoning(args)
        elif cmd == "/soul":
            self._soul()
        elif cmd == "/retry":
            self._retry()
        elif cmd == "/copy":
            self._copy()
        elif cmd == "/clear":
            self.console.clear()
            self._banner()
        elif cmd in ("/heal", "/fix"):
            self.session.add_user(_("heal_prompt"))
            full = self._stream()
            self.session.add_assistant(full)
            self.session.save()
        else:
            self.console.print(Text(_("unknown_command", cmd=cmd), style=ERR))
        return None

    def _help(self) -> None:
        tbl = Table(box=box.SIMPLE, show_header=False, padding=(0, 2, 0, 1))
        tbl.add_column(style=ACCENT, no_wrap=True)
        tbl.add_column(style=DIM)
        for cmd, desc in commands().items():
            tbl.add_row(cmd, desc)
        tbl.add_row("!cmd", _("cmd_shell_row"))
        tbl.add_row("@file", _("cmd_file_row"))
        self.console.print(Panel(tbl, title=f"[bold]{_('help_title')}[/bold]", border_style=DIM,
                                 title_align="left", box=box.ROUNDED))
        self.console.print(Text(_("help_footer"), style=DIM))

    def _status(self) -> None:
        up = self.client.is_up()
        models = self.client.models() if up else []
        ctx = self.client.context_window()
        tbl = Table(box=box.SIMPLE, show_header=False, padding=(0, 2, 0, 1))
        tbl.add_column(no_wrap=True)
        tbl.add_column()
        dot = "[#8fbf8f]●[/]" if up else "[#e0968c]○[/]"
        tbl.add_row(dot + " Hermes gateway (:8642)", f"[#8fbf8f]{_('online')}[/]" if up else f"[#e0968c]{_('not_responding')}[/]")
        tbl.add_row(f"  {_('model_label')}", f"[{ACCENT}]{self.client.model}[/]")
        tbl.add_row(f"  {_('context_label')}", f"{ctx:,}".replace(",", " ") + f" {_('tokens')}" if ctx else _("unknown"))
        tbl.add_row(f"  {_('session_tokens_label')}", f"{self.session.total_tokens:,}".replace(",", " ") if self.session.total_tokens else "—")
        tbl.add_row("  cpu", f"{psutil.cpu_percent(interval=None):.1f}%")
        tbl.add_row("  ram", f"{psutil.virtual_memory().percent:.1f}%")
        if models:
            tbl.add_row(f"  {_('available_label')}", ", ".join(models[:6]))
        self.console.print(Panel(tbl, title=f"[bold]{_('status_title')}[/bold]", border_style=DIM,
                                 title_align="left", box=box.ROUNDED))
        if not up:
            self.console.print(Text(_("run_hint"), style=ERR))
        else:
            self.console.print()

    def _sessions(self, args: list[str]) -> None:
        items = Session.list()
        if not items:
            self.console.print(Text(_("none_saved"), style=DIM))
            return
        if args:
            query = " ".join(args)
            if query.isdigit():
                idx = int(query) - 1
                if 0 <= idx < len(items):
                    self._switch(items[idx]["id"])
                    return
                self.console.print(Text(_("no_such_session"), style=ERR))
                return
            matches = [it for it in items if query.lower() in it["title"].lower()]
            if len(matches) == 1:
                self._switch(matches[0]["id"])
                return
            items = matches or items
            if not matches:
                self.console.print(Text(_("no_matches", query=query), style=DIM))
        tbl = Table(box=box.SIMPLE, padding=(0, 2, 0, 1))
        tbl.add_column("#", style=ACCENT, no_wrap=True)
        tbl.add_column(_("col_title"))
        tbl.add_column(_("col_turns"), justify="right", style=DIM)
        tbl.add_column(_("col_updated"), style=DIM)
        for i, it in enumerate(items[:15], 1):
            mark = " ←" if it["id"] == self.session.id else ""
            when = time.strftime("%m-%d %H:%M", time.localtime(it["updated"]))
            tbl.add_row(str(i), it["title"] + mark, str(it["turns"]), when)
        self.console.print(Panel(tbl, title=f"[bold]{_('sessions_title')}[/bold]", border_style=DIM,
                                 title_align="left", box=box.ROUNDED))
        self.console.print(Text(_("sessions_hint"), style=DIM))

    @staticmethod
    def _modes() -> dict[str, str]:
        return {"manual": _("mode_manual"), "auto": _("mode_auto"), "yolo": _("mode_yolo")}

    def _mode(self, args: list[str]) -> None:
        modes = self._modes()
        if not args:
            tbl = Table(box=box.SIMPLE, show_header=False, padding=(0, 2, 0, 1))
            tbl.add_column(style=ACCENT, no_wrap=True)
            tbl.add_column(style=DIM)
            for m, desc in modes.items():
                mark = " ←" if m == self.approval_mode else ""
                tbl.add_row(m + mark, desc)
            self.console.print(Panel(tbl, title=f"[bold]{_('mode_title')}[/bold]", border_style=DIM,
                                     title_align="left", box=box.ROUNDED))
            self.console.print(Text(_("mode_switch_hint"), style=DIM))
            return
        m = args[0].lower()
        if m not in modes:
            self.console.print(Text(_("mode_unknown", m=m), style=ERR))
            return
        self.approval_mode = m
        style = ERR if m == "yolo" else OK
        self.console.print(Text(_("mode_set", m=m, desc=modes[m]), style=style))

    def _lang(self, args: list[str]) -> None:
        if not args:
            tbl = Table(box=box.SIMPLE, show_header=False, padding=(0, 2, 0, 1))
            tbl.add_column(style=ACCENT, no_wrap=True)
            for code in LANGS:
                mark = " ←" if code == get_lang() else ""
                tbl.add_row(code + mark)
            self.console.print(Panel(tbl, title=f"[bold]{_('lang_title')}[/bold]", border_style=DIM,
                                     title_align="left", box=box.ROUNDED))
            self.console.print(Text(_("lang_switch_hint"), style=DIM))
            return
        code = args[0].lower()
        if code not in LANGS:
            self.console.print(Text(_("lang_unknown", code=code), style=ERR))
            return
        set_lang(code)
        self.console.print(Text(_("lang_set", code=code), style=OK))

    def _switch(self, sid: str) -> None:
        s = Session.load(sid)
        if s:
            self.session = s
            self.console.print(Text(_("switched_to", title=s.title), style=OK))

    def _history(self) -> None:
        if not self.session.messages:
            self.console.print(Text(_("history_empty"), style=DIM))
            return
        for m in self.session.messages:
            if m["role"] == "user":
                self.console.print(Text.assemble(("you › ", f"{USER} bold"), (m["content"], "")))
            else:
                self.console.print(_gradient("◆ infiny", ACCENT, ACCENT2, bold=True))
                self.console.print(Markdown(m["content"], code_theme="monokai"))
            self.console.print()

    def _model(self, args: list[str]) -> None:
        """Show or ACTUALLY CHANGE the model.

        A previous version assigned the name to `self.client.model` and reported
        "model → X". That was fiction: the gateway's model is set in
        ~/.hermes/config.yaml, and it ignores the `model` field in the request.
        The list of "available" models came from the gateway's own /v1/models,
        which returns a single entry, `hermes-agent` — its own name, not a list
        of models. Any model comparison made through this command was invalid:
        the same model from the config ran throughout. Found on a live Box
        2026-08-03.

        Now it takes the same path as the first-run wizard: the list comes from
        the endpoint itself, a change is written to the config and the gateway is
        restarted, and we say "done" only after a 200 with the key.
        """
        import asyncio

        from core import model_source as ms

        cur = ms.current_source()
        if not cur.get("configured"):
            self.console.print(Text(_("model_no_source"), style=ERR))
            return

        base_url, api_key = cur["base_url"], cur.get("api_key") or "no-key"

        if not args:
            self.console.print(Text(_("model_current", model=cur["model"]), style=ACCENT))
            self.console.print(Text(_("model_source_line", url=base_url), style=DIM))
            res = asyncio.run(ms.probe(base_url, api_key))
            if res["ok"] and res["models"]:
                self.console.print(Text(_("model_available", list=", ".join(res["models"])), style=DIM))
            elif not res["ok"]:
                self.console.print(Text(_("model_probe_fail", error=res["error"]), style=ERR))
            self.console.print(Text(_("model_switch_hint"), style=DIM))
            self.console.print()
            return

        name = args[0]
        res = asyncio.run(ms.probe(base_url, api_key))
        # An empty model list is no reason to refuse: some servers do not
        # publish one at all, and there the name can only be typed by hand.
        if res["ok"] and res["models"] and name not in res["models"]:
            self.console.print(Text(_("model_unknown_name", name=name, url=base_url), style=ERR))
            self.console.print(Text(_("model_available", list=", ".join(res["models"])), style=DIM))
            return

        with self.console.status(Text(f" {_('model_switching', name=name)}", style=DIM),
                                 spinner="dots", spinner_style=ACCENT):
            out = ms.switch_to(base_url, name, api_key)
            ready = out.get("ok") and asyncio.run(
                ms.wait_for_gateway(ms.GATEWAY_MODELS_URL))
        if not out.get("ok"):
            self.console.print(Text(_("model_switch_fail", error=out.get("error", "")), style=ERR))
            return
        # Update the client's name regardless — otherwise the status bar keeps
        # claiming the old model while the config already says otherwise.
        self.client.model = name
        if ready:
            self.console.print(Text(_("model_changed", name=name), style=OK))
        else:
            self.console.print(Text(_("model_gateway_silent"), style=ERR))

    def _reasoning(self, args: list[str]) -> None:
        """The model's thinking level — a user setting, not our constant.

        This was hardcoded to `none`, which silently killed the agent's ability
        to act: with it the model writes out a plan and ends its turn instead of
        doing anything (qwen3.5:9b), or emits the tool call in a format Ollama's
        parser cannot read (gemma4:12b). Verified across four agentic tasks on
        2026-08-22. There is no single right value for every model, so the choice
        belongs to the user.
        """
        from core import model_source as ms

        if not args:
            cur = ms.get_reasoning() or "—"
            tbl = Table(box=box.SIMPLE, show_header=False, padding=(0, 2, 0, 1))
            tbl.add_column(style=ACCENT, no_wrap=True)
            tbl.add_column(style=DIM)
            for lvl in ms.REASONING_LEVELS:
                mark = " ←" if lvl == cur else ""
                tbl.add_row(lvl + mark, _(f"reasoning_{lvl}") if lvl in ("none", "low", "high") else "")
            self.console.print(Panel(tbl, title=f"[bold]{_('reasoning_title')}[/bold]",
                                     border_style=DIM, title_align="left", box=box.ROUNDED))
            self.console.print(Text(_("reasoning_hint"), style=DIM))
            self.console.print()
            return

        level = args[0].lower()
        if level not in ms.REASONING_LEVELS:
            self.console.print(Text(_("reasoning_unknown", level=level,
                                       list=", ".join(ms.REASONING_LEVELS)), style=ERR))
            return

        import asyncio

        with self.console.status(Text(f" {_('reasoning_switching', level=level)}", style=DIM),
                                 spinner="dots", spinner_style=ACCENT):
            out = ms.set_reasoning(level)
            ready = out.get("ok") and asyncio.run(
                ms.wait_for_gateway(ms.GATEWAY_MODELS_URL))
        if not out.get("ok"):
            self.console.print(Text(_("reasoning_fail", error=out.get("error", "")), style=ERR))
            return
        self.console.print(Text(_("reasoning_set", level=level), style=OK)
                           if ready else Text(_("model_gateway_silent"), style=ERR))

    def _soul(self) -> None:
        p = Path.home() / ".hermes" / "SOUL.md"
        if p.exists():
            self.console.print(Panel(Markdown(p.read_text(encoding="utf-8")),
                                     title=f"[bold]{_('soul_title')}[/bold]",
                                     border_style=DIM, title_align="left", box=box.ROUNDED))
        else:
            self.console.print(Text(_("soul_missing", path=p), style=ERR))

    def _retry(self) -> None:
        msgs = self.session.messages
        if msgs and msgs[-1]["role"] == "assistant":
            msgs.pop()
        if not any(m["role"] == "user" for m in msgs):
            self.console.print(Text(_("nothing_to_retry"), style=ERR))
            return
        full = self._stream()
        self.session.add_assistant(full)
        self.session.save()

    def _copy(self) -> None:
        last = next((m["content"] for m in reversed(self.session.messages)
                     if m["role"] == "assistant"), None)
        if not last:
            self.console.print(Text(_("nothing_to_copy"), style=ERR))
            return
        for tool in (["clip.exe"], ["wl-copy"], ["xclip", "-selection", "clipboard"]):
            try:
                subprocess.run(tool, input=last.encode(), check=True,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self.console.print(Text(_("copied"), style=OK))
                return
            except Exception:
                continue
        self.console.print(Text(_("no_clipboard_tool"), style=ERR))


def run(resume: str | None = None, model: str = HERMES_MODEL) -> None:
    InfinyApp(model=model).run(resume=resume)
