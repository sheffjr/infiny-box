# Infiny Box — installing on Windows

This folder is what you download. Four files:

```
install-infiny.bat     <- double-click this one
install-infiny.ps1     <- does the actual work, called automatically
uninstall-infiny.bat   <- removes everything
infiny.wsl             <- the Box itself, about 500 MB
```

## Installing

1. Unpack the whole archive somewhere. Keep the files together — the installer
   looks for `infiny.wsl` next to itself.
2. Double-click `install-infiny.bat`. Windows will warn that the publisher is
   unknown — the project has no code-signing certificate. Check the SHA256
   published with the release if you want more than a click-through.
3. It asks where to put the Box. It needs about 2 GB unpacked, and the default
   is on `C:` — if that drive is tight, give it another one.
4. A shortcut called **Infiny Box** appears on the Desktop and in the Start
   menu. That is how you start it.

If WSL2 has never been enabled on this machine, the installer enables it and
asks for one reboot, then continues when you run it again. On a current
Windows 11 it is usually already on and no reboot happens.

## First run

The Box has **no model inside**. On first start it asks which endpoint to
connect to and tries to find one by itself — Ollama, LM Studio, llama.cpp or
vLLM running on your machine, or a cloud endpoint you type in.

One thing catches most people: a local server listening only on `127.0.0.1`
cannot be reached from inside the sandbox, by design of WSL networking. For
Ollama that means starting it with `OLLAMA_HOST=0.0.0.0`. The wizard says so
too, if it finds nothing.

## Uninstalling

Either run `uninstall-infiny.bat` from where the Box was installed, or use
"Infiny Box" in Windows Add/Remove Programs — the installer registers it there.

Uninstalling unregisters the WSL distribution and deletes its virtual disk.
Anything you created inside the Box goes with it. That is the point of a
sandbox, but it is worth knowing before you click.
