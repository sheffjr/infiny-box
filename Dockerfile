# Infiny Box — Phase 1: a sandbox container with an AI terminal inside.
#
# One file, three targets. The goal is "runs everywhere", and a `.wsl` file is
# really just `docker export` plus gzip (see build-wsl.sh) — so the base is
# shared across platforms anyway. Better to share it explicitly than to keep
# two copies that drift apart:
#
#   base       common layer, nothing platform-specific
#   wsl        + WSL config    → build-wsl.sh    → infiny.wsl (Windows)
#   container  + entrypoint    → build-docker.sh → docker run (macOS/Linux)
#
# What is deliberately NOT in here:
#   * models — you bring your own (`infiny --setup`);
#   * the GUI (ui/, routers/, bridge.py) — that is Phase 2, and lives elsewhere;
#   * GUI tools (grim/ydotool/wtype/foot) — there is no display in a container,
#     and no skill ever referenced them. ydotool also does not exist in
#     Debian 13 and simply broke the build.

# ══════════════════════════════════════════════════════════════════
FROM debian:trixie-slim AS base

ENV DEBIAN_FRONTEND=noninteractive
ENV HERMES_HOME=/root/.hermes
ENV SEARXNG_SETTINGS_PATH=/etc/searxng/settings.yml

# ── Force IPv4 ─────────────────────────────────────────────────
# Rootless containers (buildah/podman over slirp) usually have no IPv6 route,
# while deb.debian.org and github.com resolve to IPv6 first. The result:
#   Cannot initiate the connection to deb.debian.org:80 (2a04:4e42:600::644)
#       - connect (101: Network is unreachable)
# followed by "E: Unable to locate package systemd", which reads like a broken
# Dockerfile when what is broken is the network. git behaves the same but more
# gently: the clone hangs on an IPv6 timeout for ~134s before failing.
# gai.conf fixes getaddrinfo for everyone (curl, git, pip); apt.conf handles
# apt separately, because apt does not consult gai.conf.
RUN printf 'Acquire::ForceIPv4 "true";\n' > /etc/apt/apt.conf.d/99force-ipv4 && \
    printf 'precedence ::ffff:0:0/96  100\n' >> /etc/gai.conf

# ── Base packages ──────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    # dbus-user-session looks optional and is not: without it WSL prints
    # "Failed to start the systemd user session for 'user'" as the FIRST LINE
    # every time the Box starts, and `systemctl --user` answers "Failed to
    # connect to user scope bus". The first thing a user sees is then an error
    # message from a product that is actually fine.
    # Verified on a live Box 2026-08-13: install it, the warning goes away.
    systemd systemd-sysv dbus dbus-user-session \
    locales ca-certificates curl wget git sudo unzip \
    python3 python3-pip python3-venv \
    iproute2 iputils-ping \
    # pciutils provides lspci, which the system-info skill uses to identify the
    # GPU. Without it the flagship "tell me about this machine" request died at
    # the GPU step with "command not found" — and because the steps were
    # chained with &&, the whole report died with it and the model filled in a
    # template with empty brackets. Found in live use 2026-08-14.
    pciutils \
    # terminal tools the agent actually uses
    fd-find ripgrep fzf file less \
    # procps provides pkill/pgrep, used by restart_gateway() and
    # infiny-start.sh. It was never in the image: a latent bug that only
    # surfaced once the Box was first run end to end.
    procps \
    # node is needed by MCP servers
    nodejs npm \
    # SearXNG build dependencies (lxml compiles from source)
    build-essential libxml2-dev libxslt1-dev zlib1g-dev libffi-dev libssl-dev \
    && rm -rf /var/lib/apt/lists/* \
    # Debian installs the fd binary as `fdfind`; any skill calling `fd` would
    # get "command not found".
    && ln -sf /usr/bin/fdfind /usr/local/bin/fd

# ── Locales (UTF-8, no tofu boxes) ─────────────────────────────
RUN echo "en_US.UTF-8 UTF-8" >> /etc/locale.gen && \
    echo "ru_RU.UTF-8 UTF-8" >> /etc/locale.gen && \
    locale-gen
ENV LANG=en_US.UTF-8

# ── yazi (terminal file manager) ───────────────────────────────
# Baked into the image at build time rather than fetched on first run: for the
# end user it should simply be there. Errors are NOT silenced — if the release
# URL moves, the build must fail here rather than ship a Box without the yazi
# it promises. We already made that mistake with llama-server, where
# `2>/dev/null || echo` hid a 404.
#
# The retries and explicit timeouts are not paranoia. Measured 2026-08-01: from
# a rootless container GitHub answers, but stalls ~45s before the first byte
# (from WSL itself: 2.7s). A plain `curl -fsSL` times out and fails the build
# even though the link is live and the file downloads in 47s.
#
# The architecture is derived rather than hardcoded. It was the single place in
# this file naming x86_64 — everything else comes from apt, pip or Playwright,
# all of which resolve their own architecture — so a build on arm64 produced an
# image whose yazi was an amd64 binary that could not run. Nothing else stood in
# the way of building for Apple Silicon.
RUN set -eux; \
    case "$(dpkg --print-architecture)" in \
      amd64) YAZI_ARCH=x86_64 ;; \
      arm64) YAZI_ARCH=aarch64 ;; \
      *) echo "no yazi build for $(dpkg --print-architecture)" >&2; exit 1 ;; \
    esac; \
    curl -fsSL -o /tmp/yazi.zip \
      --retry 5 --retry-delay 5 --retry-all-errors \
      --connect-timeout 30 --max-time 600 \
      "https://github.com/sxyazi/yazi/releases/latest/download/yazi-${YAZI_ARCH}-unknown-linux-gnu.zip"; \
    unzip -q -j /tmp/yazi.zip '*/yazi' '*/ya' -d /usr/local/bin/; \
    chmod +x /usr/local/bin/yazi /usr/local/bin/ya; \
    rm -f /tmp/yazi.zip; \
    yazi --version

# ── User account ───────────────────────────────────────────────
# Kept for compatibility; the Box itself runs as root (see the note further
# down about why that is a decision rather than an oversight).
RUN useradd -m -s /bin/bash user && \
    echo "user ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers.d/infiny && \
    echo "user:infiny" | chpasswd

# ── Infiny sources ─────────────────────────────────────────────
# Only what the Box needs. infiny_cli used not to be copied at all, so cli.py
# in the image failed on import — in Phase 1, where the CLI is the only client,
# that is a total blocker.
# infiny-mcp (vision and cursor) and the web-stack MCP wrapper no longer come
# along: the first belongs to Infiny OS, which has a screen, and the second
# died when page reading moved into the plugin provider at
# hermes/plugins/web/infiny-render. All that survives from web-stack is
# settings.yml for SearXNG, copied separately into /etc/searxng below.
COPY core        /opt/infiny/core
COPY infiny_cli  /opt/infiny/infiny_cli
COPY hermes      /opt/infiny/hermes
COPY cli.py      /opt/infiny/cli.py
# README and the acceptance suite go inside the image: someone whose Box did
# not come up is sitting in the Box, not on GitHub. `bash
# /opt/infiny/test-box.sh` needs to be at hand exactly when it is needed.
COPY README.md   /opt/infiny/README.md
COPY test-box.sh /opt/infiny/test-box.sh
# NOTICE ships for the same reason as README, plus one of its own: we
# distribute other people's software inside this image, including SearXNG
# under AGPL-3.0. Attribution that exists only in the repository never reaches
# someone holding just the .wsl file.
COPY NOTICE.md   /opt/infiny/NOTICE.md

# ── Python venv ────────────────────────────────────────────────
# pyyaml is mandatory: without it core/model_source.py will not import, which
# means the model-connection wizard does not start at all.
# rich + prompt_toolkit give the full CLI; without them it silently drops to
# --plain.
RUN python3 -m venv /opt/infiny/venv && \
    /opt/infiny/venv/bin/pip install --upgrade pip -q && \
    /opt/infiny/venv/bin/pip install -q \
        httpx psutil pyyaml rich prompt_toolkit setproctitle

# ── SearXNG — search INSIDE the Box ────────────────────────────
# Installed from source into the same venv instead of via docker-compose, and
# the reason is not convenience: web-research has to work inside a container,
# and docker-compose inside a container means docker-in-docker or mounting the
# host socket — a hole in the very sandbox the Box exists to provide. SearXNG
# is an ordinary Python application; it does not need a daemon.
#
# IMPORTANT: install requirements.txt, NOT `pip install -e /opt/searxng`.
# The editable install fails with ModuleNotFoundError: msgspec, because
# SearXNG's setup.py imports searx/__init__.py, which already needs runtime
# dependencies — a chicken and egg. Verified 2026-08-01. Hence PYTHONPATH
# elsewhere: the package is not in site-packages, it runs from source.
#
# The commit is PINNED rather than "whatever is on master". Two reasons, both
# serious.
#
# Reproducibility, first: with a floating master every build produces a
# different image, and "rebuild the same thing" becomes impossible. An upstream
# regression can then be neither located nor rolled back.
#
# The second matters more. SearXNG is AGPL-3.0 and we distribute it inside the
# image. AGPL requires being able to provide *the* source that was
# distributed. With `--depth 1` and no commit we did not even know which one
# left: the cleanup step below deletes /opt/searxng/.git, so the finished image
# held no trace at all. The obligation was not merely unmet, it was unmeetable.
#
# Update deliberately: change the SHA here and in NOTICE.md, rebuild, run the
# acceptance suite. The date is next to it so the drift is visible.
ARG SEARXNG_COMMIT=8f452ee89293d9a752a776f4c33f5a5f124fff97
# 2026-09-03

# git has no retry of its own and GitHub stalls from inside a container, so we
# wrap it in a loop. Five attempts with a growing pause rather than three at
# 10s: on 2026-08-25 a build died having used exactly three in a row, while the
# same clone from the Box itself took a second and github answered 200. The
# build container's network flickers for longer than we were willing to wait,
# and every such loss costs twenty minutes of rebuilding from scratch.
RUN for i in 1 2 3 4 5; do \
        ( git init -q /opt/searxng && \
          git -C /opt/searxng remote add origin https://github.com/searxng/searxng && \
          git -C /opt/searxng fetch -q --depth 1 origin "$SEARXNG_COMMIT" && \
          git -C /opt/searxng checkout -q FETCH_HEAD ) && break; \
        echo "SearXNG clone failed (attempt $i), waiting $((i * 15))s"; \
        rm -rf /opt/searxng; sleep $((i * 15)); \
    done; \
    test -f /opt/searxng/requirements.txt && \
    printf '%s\n' "$SEARXNG_COMMIT" > /opt/searxng/INFINY_PINNED_COMMIT && \
    /opt/infiny/venv/bin/pip install -q -r /opt/searxng/requirements.txt && \
    mkdir -p /etc/searxng
COPY web-stack/searxng/settings.yml /etc/searxng/settings.yml

# ── Playwright browser location ────────────────────────────────
# PLAYWRIGHT_BROWSERS_PATH is shared: the browser is installed as root and
# launched by the gateway, so the default ~/.cache/ms-playwright would not be
# found. The install itself happens further down, in the Hermes venv — pages
# are read by the infiny-render plugin provider, which the gateway process
# imports, not by a separate MCP server on the Box's venv. Only the variable
# lives here, because the build-time install needs it too.
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright

# ── Hermes (the brain) ─────────────────────────────────────────
# Installed from PyPI, NOT via the curl script at hermes-agent.nousresearch.com.
# Verified 2026-08-01: that domain returns 403 for everything including its own
# root — the installer is not there any more. And the previous line,
#   curl ... | bash || echo "Hermes will install on first run"
# swallowed the error, so the image built WITHOUT a brain and looked healthy:
# config, SOUL.md and skills all present, no hermes binary anywhere. The same
# "invisible failure" pattern that already cost us time on llama-server.
#
# The PyPI package is official: author "Nous Research". No need to clone the
# repository, which weighs 2.1 GB.
#
# The version is PINNED for the same reason as the SearXNG commit above:
# without it every build pulls whatever is newest, and an image built today
# differs unpredictably from yesterday's. Hermes is the Box's brain; silently
# swapping it between builds means not knowing what we shipped or what the
# acceptance suite actually ran against.
#
# Update deliberately: raise the version here and in NOTICE.md, rebuild, run
# test-box.sh in full.
ARG HERMES_VERSION=0.19.0
#
# A separate venv: Hermes pins its dependencies hard, and mixing them with ours
# (rich / prompt_toolkit / playwright / searxng) is a reliable way to get a
# version conflict for nothing.
#
# `hermes --version` at the end is mandatory: if the install falls apart, the
# build must fail here rather than ship a Box with no brain.
#
# The [all] extra is required, NOT bare hermes-agent. Bare installs the core
# without aiohttp, and the OpenAI-compatible API server on :8642 never comes
# up:
#   WARNING gateway.run: API Server: aiohttp not installed
#   WARNING gateway.run: No adapter available for api_server
# The symptom misleads: port :8642 IS listening (the gateway stub), so you get
# 401 "Invalid API key" rather than connection refused, and go hunting through
# your keys. [all] is exactly what the official setup-hermes.sh installs
# (`pip install -e ".[all]"`) and what runs on the development machine where
# all 267 benchmark measurements were taken. Deviating from a verified
# configuration to save ~130 MB is not worth it.
RUN python3 -m venv /opt/hermes-venv && \
    /opt/hermes-venv/bin/pip install --upgrade pip -q && \
    /opt/hermes-venv/bin/pip install -q "hermes-agent[all]==${HERMES_VERSION}" && \
    /opt/hermes-venv/bin/python -c 'import aiohttp; print("aiohttp", aiohttp.__version__)' && \
    printf '#!/usr/bin/env bash\nunset PYTHONPATH\nunset PYTHONHOME\nexec /opt/hermes-venv/bin/hermes "$@"\n' \
        > /usr/local/bin/hermes && \
    chmod +x /usr/local/bin/hermes && \
    hermes --version

# ── Playwright + Chromium — in the BRAIN's venv ────────────────
# Pages are read by the infiny-render plugin provider, and the gateway process
# imports it, so playwright has to live in the Hermes venv. It used to sit in
# the Box's venv because a separate MCP server did the rendering; that server
# is gone. Keeping playwright in both venvs would be pointless — there is one
# browser and it lives outside either of them.
#
# Baked into the image rather than downloaded on first run: the build happens
# once, here, and the user downloads nothing but their own model. Pulling
# 400 MB of Chromium at startup would be exactly the download that made us drop
# the bundled local model.
RUN /opt/hermes-venv/bin/pip install -q playwright && \
    /opt/hermes-venv/bin/playwright install --with-deps chromium && \
    chmod -R a+rX /opt/playwright

# The whole Box runs as ROOT, and that is a decision rather than carelessness.
# SOUL.md promises the model "inside the Box you are root: install what you
# need, break things and fix them" — while the agent actually ran as `user` and
# hit a permission denial on its first install, after which it gave up ("I do
# not have sudo rights"). Observed on both models 2026-08-22. Isolation comes
# from the container, not from a user/root boundary inside it, so it is more
# honest to make the promise true than to teach the model to prefix sudo.
# Checked separately: Playwright/Chromium starts fine as root — that was the
# main risk of the move and it did not materialise.

# Skills are DIRECTORIES containing SKILL.md, not loose .md files. The layout
# changed on 2026-07-24 while fixing routing; the old `cp hermes/skills/*.md`
# has matched nothing since and broke the build silently.
# Plugins go where Hermes looks for them — $HERMES_HOME/plugins. The user
# directory specifically, not site-packages: upgrading hermes-agent must not
# wipe our page-reading provider.
RUN mkdir -p $HERMES_HOME/skills $HERMES_HOME/plugins && \
    cp /opt/infiny/hermes/config.yaml $HERMES_HOME/config.yaml && \
    cp /opt/infiny/hermes/SOUL.md $HERMES_HOME/SOUL.md && \
    cp -r /opt/infiny/hermes/skills/. $HERMES_HOME/skills/ && \
    cp -r /opt/infiny/hermes/plugins/. $HERMES_HOME/plugins/

# ── Shrinking the image ────────────────────────────────────────
# Done AFTER everything is installed, as its own step — and it only works
# because .wsl is built with a flat `export` rather than layers. In an ordinary
# layered image, deleting late saves nothing: layers stack and the file stays
# in the one below. Here the filesystem collapses into a single tar, so what is
# deleted really goes.
#
# The compiler and headers were needed exactly once, to build lxml for SearXNG.
# In a finished Box they are not needed for a second, and they weigh more than
# Chromium.
#
# The `import lxml` check at the end is mandatory: if the cleanup took a
# runtime library with it, the build must fail here rather than turn into a Box
# with broken search.
#
# Do NOT touch perl-modules: git depends on perl, and `--auto-remove` would
# take git with it. SearXNG calls git at startup to determine its own version
# and dies with FileNotFoundError. Verified on a live Box 2026-08-01 — the
# megabytes saved cost us working search.
RUN apt-get purge -y --auto-remove \
        build-essential libxml2-dev libxslt1-dev zlib1g-dev libffi-dev libssl-dev \
        python3-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /var/cache/apt/* \
              /usr/share/doc /usr/share/man /usr/share/locale/[a-df-qs-z]* \
              /opt/searxng/.git /root/.cache \
    && find / -xdev -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true

# Playwright installs TWO browser builds plus ffmpeg, and one gets used.
# `chromium.launch(headless=True)` in this version starts
# chromium_headless_shell, so that is what we keep. Full chromium (389 MB) is
# only needed for headless=False, and we have no window at all; ffmpeg (4.9 MB)
# records video, also not our case.
#
# Do NOT determine this from `p.chromium.executable_path`: the property is
# static and returns the full Chromium path regardless of what actually starts.
# I fell for it first, deleted the shell, and got
#   BrowserType.launch: Executable doesn't exist at .../chrome-headless-shell
# The only reliable method is to launch the browser after deleting, which is
# what the check below does.
RUN rm -rf /opt/playwright/chromium-[0-9]* /opt/playwright/ffmpeg-*

# Do NOT check only Python imports. The first version of this check did exactly
# that — and missed that `--auto-remove` had taken git (via perl), and that
# pkill had never been in the image at all. The Box built "green" and fell
# apart on its first real run. Everything the runtime uses gets checked here.
RUN /opt/infiny/venv/bin/python -c 'import lxml.etree, msgspec, flask; print("SearXNG deps OK")' && \
    /opt/infiny/venv/bin/python -c 'import httpx, yaml, rich, prompt_toolkit, setproctitle; print("CLI deps OK")' && \
    hermes --version && \
    yazi --version && \
    for b in git pkill pgrep curl fd rg fzf file less node python3; do \
        command -v "$b" >/dev/null || { echo "MISSING BINARY: $b"; exit 1; }; \
    done && echo "binaries present" && \
    /opt/hermes-venv/bin/python -c "\
from playwright.sync_api import sync_playwright;\
p=sync_playwright().start();b=p.chromium.launch(headless=True);\
pg=b.new_page();pg.set_content('<h1>ok</h1>');\
print('Chromium renders:', pg.inner_text('h1'));b.close();p.stop()"

# A check across the SEAM, not of a component. The previous acceptance asked
# "does the service answer?" and stayed green for two weeks while search was
# dead: the tool existed at every level except the last — it never reached the
# agent. Here we ask precisely that last question: the provider loaded, and
# Hermes hands extract to it. Building a Box that will lie about search again
# is not acceptable.
RUN cd $HERMES_HOME && /opt/hermes-venv/bin/python -c "\
from hermes_cli.plugins import discover_plugins; discover_plugins(force=True);\
from agent.web_search_registry import get_provider;\
p=get_provider('infiny-render');\
assert p is not None, 'the infiny-render plugin did not load';\
assert p.supports_extract(), 'infiny-render does not advertise extract';\
assert p.is_available(), 'infiny-render reports itself unavailable';\
print('page-reading provider present:', p.display_name)"

# ── Commands ───────────────────────────────────────────────────
COPY wsl/infiny-start.sh /usr/local/bin/infiny
COPY wsl/infiny-stop.sh  /usr/local/bin/infiny-stop
COPY wsl/infiny-ensure-env.sh /usr/local/bin/infiny-ensure-env

# Services under a supervisor. While the gateway and search hung off `nohup`,
# any agent mistake ("killed the service and could not bring it back") meant a
# dead Box until a human intervened — observed 2026-08-24. Under systemd that
# becomes "alive again in three seconds".
#
# `systemctl enable` will not work during a build: systemd is not running and
# the bus is unavailable. We do the same thing by hand — the symlink into
# multi-user.target.wants is exactly what enable creates.
COPY wsl/infiny-gateway.service /etc/systemd/system/infiny-gateway.service
COPY wsl/infiny-search.service  /etc/systemd/system/infiny-search.service
RUN chmod +x /usr/local/bin/infiny-ensure-env && \
    mkdir -p /etc/systemd/system/multi-user.target.wants && \
    ln -sf /etc/systemd/system/infiny-gateway.service \
           /etc/systemd/system/multi-user.target.wants/infiny-gateway.service && \
    ln -sf /etc/systemd/system/infiny-search.service \
           /etc/systemd/system/multi-user.target.wants/infiny-search.service

# Autostart on interactive login, so that double-clicking infiny.wsl lands in
# Infiny rather than a bare bash. Details and guard conditions are in the file.
COPY wsl/profile-infiny.sh /etc/profile.d/50-infiny.sh

# Exactly two commands, and both go through infiny-start.sh.
#
# A third binary used to be baked here, /usr/local/bin/infiny-cli — a bare
# `exec python cli.py` that went around the entire startup path. Removed
# 2026-09-03. It was left over from the architecture that had a GUI (the
# "lifeboat without graphics", for when the interface failed to come up). The
# GUI is Phase 2; the Box has none, so there was nothing to rescue anyone from.
#
# The problem was not the extra kilobyte. That path skipped everything the
# supervisor exists for: it started no services, waited for no gateway and ran
# no watchdog. In the Docker target, where infiny-start.sh is what brings the
# services up at all, it would hand you a CLI with no gateway behind it. And it
# appeared in no documentation, so the only people who could find it were
# someone reading PATH out of curiosity — or the agent itself, which our own
# skills tell to go and repair the system.
RUN chmod +x /usr/local/bin/infiny /usr/local/bin/infiny-stop

# The system introduces itself as Infiny Box — but only where a human reads it.
#
# /etc/os-release is a symlink to the vendor file at /usr/lib/os-release, and
# replacing the symlink with a real file is the mechanism the spec provides for
# exactly this: /etc wins over /usr/lib, the vendor copy stays intact underneath,
# and a base-files upgrade cannot quietly revert the branding.
#
# ID stays `debian`, deliberately. The agent's whole job is installing software
# the user asks for, and third-party install scripts branch on ID. A well
# written one consults ID_LIKE; plenty just test `[ "$ID" = debian ]` and refuse
# otherwise. Changing ID buys standards purity and costs compatibility we cannot
# test, so it is not worth it — the user-visible name is what the question "what
# system am I on" actually returns.
#
# Every Debian field is carried over verbatim. Dropping them is not cosmetic:
# VERSION_CODENAME is what installers interpolate into an apt source line, and a
# missing one turns "deb ... trixie main" into "deb ...  main".
# printf rather than a heredoc on purpose: heredocs in RUN need BuildKit, and
# build-wsl.sh picks whichever of buildah, podman or docker it finds.
#
# The build reads the file back and asserts on it. A missing VERSION_CODENAME
# would turn a third-party `deb ... $VERSION_CODENAME main` into a broken source
# line, and that failure belongs here rather than on a user's machine months
# from now.
RUN rm -f /etc/os-release && \
    printf '%s\n' \
      'PRETTY_NAME="Infiny Box 0.1 (Debian GNU/Linux 13 trixie)"' \
      'NAME="Infiny Box"' \
      'VERSION_ID="13"' \
      'VERSION="13 (trixie)"' \
      'VERSION_CODENAME=trixie' \
      'DEBIAN_VERSION_FULL=13.6' \
      'ID=debian' \
      'INFINY_VERSION="0.1"' \
      'HOME_URL="https://github.com/sheffjr/infiny-box"' \
      'SUPPORT_URL="https://github.com/sheffjr/infiny-box/issues"' \
      'BUG_REPORT_URL="https://github.com/sheffjr/infiny-box/issues"' \
      > /etc/os-release && \
    . /etc/os-release && \
    [ "$ID" = debian ] && [ "$VERSION_CODENAME" = trixie ] && \
    echo "os-release: $PRETTY_NAME (ID=$ID, codename=$VERSION_CODENAME)"

# ══════════════════════════════════════════════════════════════════
# Windows: exported to infiny.wsl (build-wsl.sh)
FROM base AS wsl

COPY wsl/wsl.conf              /etc/wsl.conf
COPY wsl/wsl-distribution.conf /etc/wsl-distribution.conf
COPY wsl/terminal-profile.json /opt/infiny/terminal-profile.json
COPY wsl/first-run.sh          /opt/infiny/first-run.sh
COPY wsl/oobe.sh               /etc/oobe.sh
RUN chmod +x /opt/infiny/first-run.sh /etc/oobe.sh

CMD ["/bin/bash"]

# ══════════════════════════════════════════════════════════════════
# macOS / Linux: docker run -it infiny
FROM base AS container

WORKDIR /root
# Straight into the CLI: a container has neither wsl.conf's boot.command nor an
# OOBE, and the Box should open in one window exactly as it does on Windows.
# The CLI starts the first-run wizard itself when no model source is set.
CMD ["/usr/local/bin/infiny"]
