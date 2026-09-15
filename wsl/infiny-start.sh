#!/bin/bash
# The `infiny` command — the way into Infiny Box.
#
# Phase 1: the client is the CLI and nothing else. A system interface is Phase 2.
#
# The services (gateway and search) live under a supervisor rather than being
# started "by hand" from here. The reason: on 2026-08-24 the agent killed a
# service, failed to bring it back, and reported that it had. While everything
# hung off `nohup`, that mistake meant a dead Box until a human intervened.
# Under systemd, "killed it" becomes "alive again in three seconds".
#
# But systemd is not everywhere: in the Docker target (macOS/Linux) PID 1 is our
# CLI and there are no units at all. Hence exactly two paths, and both have to
# work.
set -e

GATEWAY_URL="http://127.0.0.1:8642/v1/models"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
export HERMES_HOME

# The gateway counts as alive on 200 OR 401: a 401 means "the service is up and
# simply wants a key". Treating that as death spawns a second gateway, and two
# processes fighting over :8642 produce flickering 401/200 that take hours to
# track down.
gateway_alive() {
    local code
    code=$(curl -s -o /dev/null -m 2 -w '%{http_code}' "$GATEWAY_URL" 2>/dev/null || echo 000)
    [[ "$code" == "200" || "$code" == "401" ]]
}

search_alive() {
    curl -s -o /dev/null -m 2 http://127.0.0.1:8888/ 2>/dev/null
}

# The canonical test for a live systemd. `pidof systemd` lies inside a container
# where systemd may be installed without being PID 1.
have_systemd() {
    [[ -d /run/systemd/system ]]
}

/usr/local/bin/infiny-ensure-env

# Bringing up whatever is not answering lives in a function, because in the
# Docker target (see the else branch below) it happens repeatedly under a
# watchdog rather than once at startup. Without that, `kill -9` on the gateway
# or on search leaves the Box dead forever — nobody brings them back. Verified
# live 2026-08-31: a gateway killed by hand inside the container target did not
# answer immediately and still did not answer thirty seconds later — exactly the
# 2026-08-24 scenario that systemd with Restart=always exists for on WSL. In the
# Docker target this loop plays systemd's part.
start_missing_services() {
    if ! gateway_alive && command -v hermes &>/dev/null; then
        echo "→ Starting Hermes gateway..."
        # cd into HERMES_HOME is mandatory: otherwise .env is not picked up and
        # the Bearer key comes out empty. --replace is needed because Hermes
        # keeps its own lock, which survives the process being killed.
        ( cd "$HERMES_HOME" && setsid nohup hermes gateway run --replace \
            >/tmp/hermes-gateway.log 2>&1 </dev/null & )
        # We wait here, inside the function, rather than only once outside at
        # startup: the watchdog below calls this same function every 5 seconds,
        # and without the wait it sees a gateway that has not answered yet (a
        # cold model load takes up to a minute), starts a SECOND instance on top
        # of the first, then a third, and so on — --replace cannot resolve the
        # race fast enough. Verified live 2026-08-31: without this wait, three
        # hermes processes accumulated within 15 seconds and the port answered
        # nothing at all (000) — the same ":8642 has been fought over twice
        # already" race from this project's history, now in the Docker target.
        for _ in $(seq 1 30); do
            gateway_alive && break
            sleep 1
        done
    fi
    if [[ -d /opt/searxng ]] && ! search_alive; then
        echo "→ Starting search (SearXNG)..."
        # cd / — Python mixes cwd into sys.path, and from a /mnt/... path (which
        # is where the Windows shortcut launches the Box from) SearXNG dies with
        # OSError: Input/output error. A daemon has no use for someone else's
        # working directory.
        ( cd / && SEARXNG_SETTINGS_PATH=/etc/searxng/settings.yml \
          PYTHONPATH=/opt/searxng \
              setsid nohup /opt/infiny/venv/bin/python -m searx.webapp \
              >/tmp/searxng.log 2>&1 </dev/null & )
        # Same watchdog race as the gateway above, but SearXNG usually starts
        # faster — 15 seconds is comfortable.
        for _ in $(seq 1 15); do
            search_alive && break
            sleep 1
        done
    fi
}

if have_systemd; then
    # The units are enabled in the image, so boot has usually started them
    # already. The start here covers the case where someone stopped them by hand.
    gateway_alive || { echo "→ Starting Hermes gateway..."; systemctl start infiny-gateway 2>/dev/null || true; }
    search_alive  || { echo "→ Starting search (SearXNG)...";  systemctl start infiny-search  2>/dev/null || true; }
else
    # Docker target: no supervisor, so we do it ourselves.
    start_missing_services

    # The watchdog lives in the background regardless of what happens to this
    # process afterwards (below: exec into cli.py). A background subshell
    # started before the exec is not replaced by it and survives as a separate
    # process in the container. Five seconds between checks is the same order as
    # RestartSec=3 on the WSL units: not instant, but not noticeable either.
    #
    # Its output goes to a log, NOT to the terminal. The subshell inherits
    # stdout from this shell, which hands it to the CLI through exec — so
    # "→ Starting Hermes gateway..." from a service that died in the middle of
    # the night would land in the middle of the interface, on top of the agent's
    # reply. Nothing is lost by redirecting: the restart is recorded in
    # /tmp/hermes-gateway.log and /tmp/searxng.log anyway.
    ( while true; do sleep 5; start_missing_services; done ) \
        >>/tmp/infiny-watchdog.log 2>&1 &
fi

# Wait for the gateway: without it the very first question goes nowhere.
for _ in $(seq 1 30); do
    gateway_alive && break
    sleep 1
done
gateway_alive || echo "⚠ Gateway is not responding. Log: /tmp/hermes-gateway.log"

# From here the CLI does everything: if no model source is configured, it starts
# the first-run wizard itself. Through exec, so that Ctrl+C and exit codes
# behave like an ordinary program rather than getting lost in a wrapper.
cd /opt/infiny
exec ./venv/bin/python /opt/infiny/cli.py "$@"
