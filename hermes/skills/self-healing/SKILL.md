---
name: self-healing
description: Fix broken things: gateway down, no search, model unreachable, disk full
triggers: broken, not working, fix, repair, error, failed, crash, frozen, slow, diagnose, heal, сломалось, не работает, почини, ошибка, завис, тормозит, диагностика
---

# Self-Healing (Infiny Box)

You can diagnose and repair this container. Work through the checks, report
findings, then fix (with confirmation for anything destructive).

## Non-negotiable acceptance criteria
- Diagnose with real commands before proposing a fix. Never guess the cause.
- For each fix, show the exact command and its result. Don't claim "fixed" blindly.
- Restarting a service here is safe; removing packages or editing configs needs
  confirmation.

## Know what actually runs here
This is a container. There are exactly three moving parts:

| what | where | managed by |
|---|---|---|
| Hermes gateway (your own brain's API) | `127.0.0.1:8642` | `infiny-gateway.service` |
| SearXNG (web search) | `127.0.0.1:8888` | `infiny-search.service` |
| the model | on the **host**, outside the Box | the user |

Both services run under systemd with `Restart=always`. That has a consequence
worth knowing: **you cannot kill them for long.** Stop one and it comes back in
about three seconds. If you need it down to test something, use
`systemctl stop <unit>`, and remember to start it again.

There is no display, no compositor, no GPU driver and no local model process in
here. If a diagnosis leads you toward one of those, the diagnosis is wrong.

## Diagnostic sweep
- Gateway: `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8642/v1/models`
  (401 also means alive — it answered, it just wants the key)
- Search: `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8888/`
- Model endpoint (read the address from the config first):
  `grep base_url ~/.hermes/config.yaml`, then `curl -s -o /dev/null -w '%{http_code}' <base_url>/models`
- Services: `systemctl status infiny-gateway infiny-search --no-pager -l`
- Recent service logs: `journalctl -u infiny-gateway -n 30 --no-pager`
- Disk: `df -h /`
- Memory: `free -h`
- Network out of the Box: `curl -s -o /dev/null -w '%{http_code}' https://example.com`
- Gateway log, when it is the gateway that is unwell: `tail -40 /tmp/hermes-gateway.log`

## Common fixes
- **Gateway not answering** → `systemctl restart infiny-gateway`, then check
  `systemctl status infiny-gateway`. If it restarts in a loop, the cause is in
  the log (`journalctl -u infiny-gateway -n 50 --no-pager`) — usually a broken
  `~/.hermes/config.yaml`, not the service itself.
- **Search not answering** → `systemctl restart infiny-search`, then
  `journalctl -u infiny-search -n 30 --no-pager` if it does not come up.
- **Model endpoint unreachable** → this is almost always on the host, not here.
  The usual cause is a server bound to `127.0.0.1`, which is invisible from this
  sandbox by design. Tell the user to make it listen on `0.0.0.0` (for Ollama:
  `OLLAMA_HOST=0.0.0.0`, then restart it). Do not try to fix it from inside —
  you cannot reach the host. `infiny --setup` re-runs the connection wizard.
- **Disk full** → `apt-get clean` and, if systemd journals are large,
  `journalctl --vacuum-size=100M`.

### Killing a process: never `pkill -f` on a bare name
`pkill -f searx.webapp` matches **any** process whose command line contains that
text — including the shell running your own command, and the agent process
holding the user's message (their words are in its argv). You kill yourself, the
task dies with SIGTERM, and nothing explains why. Seen for real 2026-08-24.

Find the PID first, then kill it:
```
pgrep -f 'searx[.]webapp'      # brackets stop the pattern matching itself
kill <pid>
```

## When write_file refuses a system path
Writing to `/etc/`, `/boot/` or `/usr/lib/systemd/` with `write_file` comes back
with "Refusing to write to sensitive system path" and advice to use `sudo`.
Ignore the advice — there is no `sudo` here, you are already root. The refusal
is a guard on that one tool, not on the file. Use the terminal instead:

```
cat > /etc/some.conf <<'EOF'
...
EOF
```

That is not a workaround for a security rule, it is the supported path: system
files are edited through the shell, and this is a disposable container. Do not
report the task as blocked over this.

The one file that really is off limits is `~/.hermes/config.yaml` — it holds the
approval policy, and you do not get to edit your own permissions. If a fix
genuinely needs a change there, say what to change and let the user make it.

## When a fix needs root and sudo asks for a password
You are root inside the Box, so this should not happen. If it does:
- Stop trying variants. Do not retry with `su`, do not suggest another terminal.
- Never ask the user for a password and never ask them to type one anywhere.
- Report it plainly: name the exact command, say administrator rights are not
  available to you here, and stop.
- Still report everything you DID manage to diagnose — that is the useful part.

## Output
Report: what was broken, what you did, and whether it's fixed now. One issue per
line. If a check came back clean, say so in one word rather than pasting output.
