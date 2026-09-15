#!/usr/bin/env python3
"""Infiny CLI — full control of Infiny from the terminal.

The control block for the whole machine. Rich, modern, animated by default
(infiny_cli/app.py) — the same brain as the GUI (Hermes gateway :8642, same
memory/skills/tools). Falls back automatically to a stdlib-only plain mode
if rich/prompt_toolkit aren't installed, or explicitly via --plain — this is
the lifeline: works over SSH, on a bare tty, in recovery, with no deps.

Russian is available as a switchable interface feature (`/lang ru` inside
the REPL); English is the default.

Usage:
  infiny                    rich interactive REPL
  infiny "how's it going?"  one question, one answer, exit
  infiny --setup            connect a model (endpoint wizard)
  infiny --status           check that services are alive
  infiny --heal             self-diagnose + repair
  infiny --resume [ID]      return to a saved conversation (latest if no ID)
  infiny --plain            stdlib-only REPL (recovery / no dependencies)

Phase 1 ("Infiny Box") ships no model: the user brings their own OpenAI-compatible
endpoint. So before anything can talk to the brain, a model source must be
configured — hence the wizard, and hence the auto-trigger below. Landing a first-
time user in a REPL that silently fails on every message is the worst outcome
available; we have made that mistake before.
"""
import argparse
import sys
from pathlib import Path

# Runs as /opt/infiny/cli.py in the image, where `core` sits alongside. Without
# this, `from core import ...` inside infiny_cli/setup.py breaks depending on
# which directory the user happened to launch from.
sys.path.insert(0, str(Path(__file__).resolve().parent))


def _hide_message_from_cmdline() -> None:
    """Remove the message text from the process command line.

    `infiny "stop searx"` puts the user's words into argv, and therefore into
    /proc/PID/cmdline. The agent then dutifully runs `pkill -f searx` — and
    kills ITSELF, because the pattern matched its own command line. From
    outside this looks like a mysterious SIGTERM with no explanation; we lost an
    evening to it on 2026-08-24, mistaking our own trap for the agent failing.

    setproctitle rewrites argv in memory and the process becomes plain `infiny`.
    Without the library we carry on as before — this is a convenience, not a
    requirement.
    """
    try:
        import setproctitle
        setproctitle.setproctitle("infiny")
    except Exception:
        pass


def main() -> None:
    _hide_message_from_cmdline()
    p = argparse.ArgumentParser(prog="infiny", description="Infiny CLI — Infiny in your terminal")
    p.add_argument("message", nargs="*", help="message to the agent (empty = interactive REPL)")
    p.add_argument("--setup", action="store_true", help="connect a model (endpoint wizard)")
    p.add_argument("--status", action="store_true", help="check services")
    p.add_argument("--heal", action="store_true", help="self-diagnose + repair")
    p.add_argument("--resume", nargs="?", const="", default=None, metavar="ID",
                   help="return to a saved conversation (latest if no ID)")
    p.add_argument("--plain", action="store_true", help="stdlib-only mode (no third-party deps)")
    p.add_argument("--no-stream", action="store_true", help="plain mode: don't stream tokens")
    args = p.parse_args()

    from infiny_cli import setup

    if args.setup:
        sys.exit(0 if setup.run_setup(force=True) else 1)

    # First run: no model source configured. The wizard comes before everything
    # else, including --status, because "the services are alive but there is no
    # brain" is not the answer anyone came for.
    if setup.needs_setup() and not setup.run_setup():
        sys.exit(1)

    use_plain = args.plain
    if not use_plain:
        try:
            import rich  # noqa: F401
            import prompt_toolkit  # noqa: F401
        except ImportError:
            print("(rich/prompt_toolkit not installed — falling back to plain mode; "
                  "pip install -r requirements.txt for the full experience)", file=sys.stderr)
            use_plain = True

    if use_plain:
        from infiny_cli import plain
        if args.status:
            plain.print_status()
            return
        if args.heal:
            from infiny_cli.i18n import t as _t
            plain.ask([{"role": "user", "content": _t("heal_prompt")}])
            print()
            return
        if args.message:
            plain.one_shot(" ".join(args.message), stream=not args.no_stream)
            return
        plain.repl()
        return

    from infiny_cli.app import InfinyApp
    from infiny_cli.client import HERMES_MODEL

    app = InfinyApp(model=HERMES_MODEL)
    if args.status:
        app._status()
        return
    if args.heal:
        from infiny_cli.i18n import t as _t
        app.session.add_user(_t("heal_prompt"))
        full = app._stream()
        app.session.add_assistant(full)
        app.session.save()
        return
    if args.message:
        app.session.add_user(" ".join(args.message))
        full = app._stream()
        app.session.add_assistant(full)
        app.session.save()
        return

    app.run(resume=args.resume)


if __name__ == "__main__":
    main()
