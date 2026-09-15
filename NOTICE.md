# Third-party software in Infiny Box

Copyright 2026 sheffjr

Infiny Box itself is licensed under the Apache License, Version 2.0 — see
[LICENSE](LICENSE). That covers the code written for this project. Everything
listed below belongs to other people and keeps its own licence.

Infiny Box is mostly other people's work, carefully assembled. This file says
whose, under what terms, and what we changed. If something here is wrong or
incomplete, that is a bug — please open an issue.

The versions below are what shipped in the image built on 2026-09-14 and were
verified against that image, package by package; they move as upstream moves.

---

## Hermes Agent — the brain

**Nous Research** · MIT · <https://github.com/NousResearch/hermes-agent>
Version **0.19.0**, installed from PyPI as `hermes-agent[all]==0.19.0`.
Pinned in the `Dockerfile` (`ARG HERMES_VERSION`) — the version you get is the
version we tested against, not whatever was newest on build day.

Hermes is the agent itself: the conversation loop, tool calling, approvals,
context management, the gateway on `:8642`. Practically everything Infiny does
when it *thinks*, Hermes does.

**Infiny Box is not a fork of Hermes.** We install it as a dependency and do not
modify its source. What we add around it:

- `hermes/config.yaml` — configuration only
- `hermes/SOUL.md` — the agent persona
- `hermes/skills/` — our own skill documents
- `hermes/plugins/web/infiny-render` — our own web-extract provider, written
  against Hermes' public plugin API

Bugs in agent behaviour usually belong upstream, not here.

---

## SearXNG — search

**SearXNG contributors** · **AGPL-3.0** · <https://github.com/searxng/searxng>

Cloned unmodified at image build time, pinned to commit
**`8f452ee89293d9a752a776f4c33f5a5f124fff97`** (2026-09-03). The same commit is
written into the image at `/opt/searxng/INFINY_PINNED_COMMIT`, so anyone holding
only the `.wsl` file can still tell exactly which source they received:

```
git clone https://github.com/searxng/searxng
git -C searxng checkout 8f452ee89293d9a752a776f4c33f5a5f124fff97
```

This pin exists because AGPL-3.0 requires being able to provide *the* source
that was distributed. Earlier builds cloned whatever was on `master` that day
and then deleted `.git` from the image — leaving no way to answer the question
at all.

SearXNG runs inside the Box on `127.0.0.1:8888` and is the only reason the agent
can search the web without an API key. We do not modify its code. The one file
we supply is `web-stack/searxng/settings.yml` — configuration, enabling the JSON
output format the agent needs and adjusting engine timeouts.

**AGPL-3.0 is a strong copyleft licence.** Its full text ships inside the image
at `/opt/searxng/LICENSE`. If you redistribute this image, or build a service on
it, read that licence — it has obligations that MIT and Apache do not, including
for software offered to users over a network.

We are not lawyers and this file is not legal advice.

---

## Playwright and Chromium — reading pages

**Microsoft** · Apache-2.0 · <https://github.com/microsoft/playwright-python>
Version 1.62.0, plus the Chromium build Playwright downloads
(`/opt/playwright`). Chromium itself is BSD-3-Clause with additional components
under their own licences.

Used by our `infiny-render` provider to render JavaScript-heavy pages that plain
HTTP fetching cannot read.

---

## Debian and the command-line tools

The image is built on **Debian GNU/Linux 13 (trixie)**. The tools the agent uses
as hands come from Debian's archive, each under its own licence:

| tool | version | what it is for |
|---|---|---|
| `ripgrep` | 14.1.1 | searching file contents |
| `fd-find` | 10.2.0 | finding files |
| `fzf` | 0.60.3 | fuzzy selection |
| `file` | 5.46 | identifying file types |
| `less` | 668 | paging |
| `git` | 2.47.3 | version control |
| `nodejs` | 20.19.2 | JavaScript runtime |

`yazi` (file manager, MIT) is installed from its upstream GitHub release rather
than from Debian.

Licences vary — several are GPL. The authoritative text for every package is in
the image itself, at `/usr/share/doc/<package>/copyright`. We have not modified
any of them.

---

## Python libraries

Used by the Infiny CLI:

| package | version | licence |
|---|---|---|
| `httpx` | 0.28.1 | BSD-3-Clause |
| `psutil` | 7.2.2 | BSD-3-Clause |
| `PyYAML` | 6.0.3 | MIT |
| `rich` | 15.0.0 | MIT |
| `prompt_toolkit` | 3.0.53 | BSD-3-Clause |
| `setproctitle` | 1.3.7 | BSD-3-Clause |

SearXNG brings 19 further Python dependencies of its own; they are listed in
`/opt/searxng/requirements.txt` inside the image.

---

## What is actually ours

Everything else in this repository:

- `infiny_cli/` — the terminal client, the first-run wizard, the bilingual
  string table
- `core/` — endpoint discovery, model switching, environment detection
- `cli.py` — entry point
- `Dockerfile`, `build-wsl.sh`, `build-docker.sh` — how the two images are built
- `wsl/` — WSL integration, systemd units, service supervision
- `hermes/` — configuration, persona and skills for Hermes, and our web-extract
  plugin
- `test-box.sh` — the acceptance suite

The idea Infiny Box sells is not any one of these components. It is that a
person on Windows can run one installer and get a sandboxed Linux machine an
agent may freely operate — with search, a browser, and a shell — without
assembling seven projects by hand first.

That assembly is the work. The parts belong to the people named above.
