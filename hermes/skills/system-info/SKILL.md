---
name: system-info
description: RAM, disk, CPU, GPU, OS version, uptime, date and time
triggers: system, ram, memory, cpu, disk, space, time, date, hostname, os, version, kernel, gpu, hardware, uptime, оперативк, память, память, процессор, диск, место, время, дата, система, версия, ядро, видеокарта, железо
---

# System Info

This is the single most important reliability rule for Infiny: **you have no
built-in knowledge of this machine's actual hardware, OS version, or the current
time.** Any of those, guessed, will be wrong. This skill exists so you never guess.

## Non-negotiable acceptance criteria
- For ANY question touching hardware, OS, resources, or time/date — run the exact
  command below. Do not answer before running it. Do not paraphrase a remembered
  value from an earlier turn if more than a few minutes have passed (RAM/disk
  change, and the date always does).
- Never say "I don't have access to real-time information" — you do, via these
  commands. Run them.
- Report the actual numbers returned. Don't round or approximate unless the user
  asked for an approximation.
- **Partial output is still good output.** If one field comes back empty or with
  "command not found" (GPU is the usual one — a sandbox often has no PCI bus),
  report every other field you DID get. Never replace real values you already
  have with placeholders like `[CPU model]` or a "something went wrong" apology —
  that throws away correct data over one missing line.

## Exact commands (single terminal call each — combine with `&&` for one question)

**Current date and time** (the model has NO internal clock — always check):
```
date "+%Y-%m-%d %H:%M:%S %Z"
```

**RAM (total / used / free, plus used-percent)**:
```
free -h | grep Mem && free | awk '/Mem:/{printf "Used: %.0f%% of total\n", $3/$2*100}'
```
The second line prints the used percentage already computed (used/total). For
"сколько занято RAM в процентах" / "how much RAM is used", read that number
straight off — do NOT compute it yourself (used/total, never used/free).

**CPU model and core count**:
```
lscpu | grep -E "Model name|CPU\(s\):|Thread"
```

**Disk space**:
```
df -h / --output=size,used,avail,pcent
```

**OS name and version**:
```
cat /etc/os-release | grep -E "PRETTY_NAME|VERSION="
```

**Kernel version**:
```
uname -r
```

**GPU**:
```
lspci | grep -iE "vga|3d|display"
```

**Hostname**:
```
hostname
```

**Uptime**:
```
uptime -p
```

**Everything at once** (for "tell me about this system" / "какая у меня система").
Join the steps with `;`, NOT `&&`: with `&&` a single failing field (a missing
tool, an empty GPU list) aborts the whole chain and you lose every value after
it. With `;` each field stands alone and the report always completes.
```
echo "=== Time ===" ; date "+%Y-%m-%d %H:%M:%S %Z" ; \
echo "=== OS ===" ; grep PRETTY_NAME /etc/os-release ; \
echo "=== Kernel ===" ; uname -r ; \
echo "=== CPU ===" ; lscpu | grep "Model name" ; \
echo "=== RAM ===" ; free -h | grep Mem ; free | awk '/Mem:/{printf "Used: %.0f%% of total\n", $3/$2*100}' ; \
echo "=== Disk ===" ; df -h / --output=size,used,avail,pcent | tail -1 ; \
echo "=== GPU ===" ; lspci 2>/dev/null | grep -iE "vga|3d" || echo "no PCI GPU visible (normal in a sandbox)" ; \
echo "=== Hostname ===" ; hostname
```
The GPU line is the one that legitimately comes back empty or absent — a
container/WSL usually exposes no real GPU over PCI. That is not a failure to
apologise for; say the host GPU is not visible from inside the sandbox and move
on.

## Workflow
1. User asks anything in the trigger list → run the relevant command(s) above
   (or the combined one for a general "tell me about my system").
2. Read the actual output.
3. Answer in one or two sentences with the real numbers. No preamble like
   "Let me check that for you" — just check it and answer.

## Output
Direct answer with real values. Example: "16 GB RAM, 6.2 GB used. It's 14:32 on
July 7, 2026." Not: "I'll need to check your system specifications."
