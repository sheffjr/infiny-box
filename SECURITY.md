# Security

## Reporting something

Open a [private security advisory][advisory] on this repository. If that is not
available to you, open a normal issue saying only that you have found something
and how to reach you — no details in public.

There is no bounty and no SLA. This is one person's project. What you will get
is an honest answer about whether it is a real problem and what is being done.

[advisory]: https://github.com/sheffjr/infiny-box/security/advisories/new

## What the Box actually protects

Be clear-eyed about this before you rely on it.

**The boundary is the container, not the user inside it.** The agent runs as
root, on purpose: the product promises it can install packages and repair its
own system, and a root that cannot do those things is a lie told to the model.
Isolation comes from WSL2 or Docker, and it is exactly as strong as WSL2 or
Docker is.

**Host drives are not mounted, and the agent can mount them anyway.** WSL's
drive support lives in the kernel, and root inside its own namespace may mount.
We turn off automatic mounting; we cannot turn off the capability without taking
away root. What we do remove is execution: Windows interop is disabled, so a
mounted drive is files to read and write, not a way to run programs as you.

**So the realistic worst case is your files, not your session.** If that is not
a strong enough boundary for what you are doing, run the Box on a machine you do
not mind losing. That is not a disclaimer, it is the intended usage.

**Prompt injection is real and unsolved here as everywhere.** The agent reads
web pages. A page can contain instructions aimed at it. Approvals exist for this
reason: `approvals.mode: manual` is the default, dangerous commands are gated,
and a small deny list is enforced even under `--yolo`. None of that is a
guarantee. Do not point the Box at hostile content and walk away.

## What we consider a vulnerability

- A way out of the sandbox that does not require the user's cooperation.
- Anything that leaks the model API key, the gateway token or conversation
  history off the machine.
- Command execution reaching the host through a path we thought was closed
  (interop, a mount we create, a service we expose).
- A network service reachable from outside the machine. Everything we run binds
  to 127.0.0.1; if something does not, that is a bug.

## What we do not

- The agent doing something destructive *inside* the Box. That is the product
  working as designed; it is a container you can afford to break.
- Prompt injection changing the agent's behaviour within the sandbox.
- Anything requiring the user to disable approvals and then approve the attack.

## Keys and secrets

The model API key you enter in the wizard is written to `~/.hermes/config.yaml`
inside the Box, `chmod 600`. Hermes reads it from there; it has nowhere else to
live. The gateway token is generated per installation in `~/.hermes/.env`, also
`0600` — nothing shared is baked into the image.

If you use the Docker target with `-v infiny-home:/root`, that volume contains
your key and travels with the volume. Treat it as you would an `.env` file.

## Supply chain

SearXNG is pinned to a commit and Hermes to a version, both in the `Dockerfile`,
both recorded in [NOTICE.md](NOTICE.md). The SearXNG commit is also written into
the image at `/opt/searxng/INFINY_PINNED_COMMIT`, so someone holding only the
`.wsl` file can still identify exactly which source they received.

The published image is not reproducible bit for bit — Debian packages and the
Playwright browser move underneath us. The CI workflow builds from the same
Dockerfile in a clean environment, which is the closest honest approximation.

The installer is not code-signed. SmartScreen will warn about it, and that
warning is accurate: this is a small project without a certificate. Verify the
SHA256 published with each release.
