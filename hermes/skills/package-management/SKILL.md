---
name: package-management
description: Install, remove, update packages with apt
triggers: install, remove, uninstall, update, upgrade, package, app, software, apt, установи, удали, обнови, приложение, программа, пакет
---

# Package Management (Infiny Box — Debian 13, apt)

Installing things is normal here, not an event: the Box is a disposable
container and **you ARE root inside it** — no `sudo` needed, and a permission
error is never the reason to give up. Install what a task needs.

## Non-negotiable acceptance criteria
- Confirm with the user before installing or removing packages, unless
  autonomous mode is on. State exactly what will be installed or removed.
- Never claim a package installed without checking the command's exit status.
- After install, verify the binary exists (`command -v <name>`) before reporting
  success.

## apt
- Search: `apt-cache search <term> | head -20`
- Install: `DEBIAN_FRONTEND=noninteractive apt-get install -y <pkg>`
- Remove: `apt-get remove -y <pkg>`
- Update lists: `apt-get update` — **needed before the first install**, the
  image ships with the package lists stripped to save space, so the first
  `install` in a fresh Box fails with "Unable to locate package" until you do.
- Show what a package provides: `dpkg -L <pkg>`

## There is no display here
This container has no screen, no X, no Wayland. A GUI program can be installed,
but it cannot be launched — there is nowhere to draw it. If the user asks for a
desktop application, say that plainly and offer the terminal equivalent
(`ncdu` instead of a disk-usage GUI, `yazi` instead of a file manager, and so
on). Never offer to "launch" a window.

Python packages go into a venv or use `--break-system-packages`: Debian 13
refuses `pip install` into the system interpreter, and that refusal is correct,
not an error to route around blindly.

## "Permission denied" is never the end of the road here
You are root in this container. A permission error means the command was wrong,
not that you lack rights — most often a missing `apt-get update` first, or pip
refusing the system interpreter (see above). Fix the command and retry.

What NOT to do, because it has actually happened and it wasted the user's time:
do not announce "I have no sudo rights / the system blocks me" and stop. That
sentence is false inside the Box, and the task dies on a false premise. Read the
real error text and act on it.

Do NOT invent a cause either — in particular, do not blame an "apt lock" unless
you actually ran `fuser /var/lib/dpkg/lock-frontend` and saw a process holding
it. And never ask the user to type a password anywhere.

## Workflow
1. Search first to find the exact package name.
2. Show the user what you found and ask to confirm.
3. Install, then verify the binary exists.

## Output
One line: what was installed or removed, and whether it succeeded.
