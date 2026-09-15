#!/bin/bash
# Stop Infiny's background services.
#
# Rewritten 2026-09-03: the previous version killed `uvicorn bridge`,
# `hermes server` and `llama-server` — none of which we have run for months.
# Our services are `hermes gateway run` and `python -m searx.webapp`, so the
# script matched nothing and reported success. "Stopped." while everything
# kept running is worse than no command at all.
#
# Two paths, mirroring infiny-start.sh: under systemd the units own the
# processes, and killing them directly only makes the supervisor start them
# again three seconds later.
set -u

have_systemd() { [[ -d /run/systemd/system ]]; }

if have_systemd; then
    echo "Stopping Infiny services..."
    systemctl stop infiny-gateway 2>/dev/null || true
    systemctl stop infiny-search  2>/dev/null || true
else
    # Docker target: no supervisor. Stop the watchdog first, otherwise it
    # brings both services back within five seconds.
    echo "Stopping Infiny services..."
    pkill -f 'while true; do sleep 5' 2>/dev/null || true
    # Bracket in the pattern keeps pkill from matching its own command line.
    pkill -f 'hermes gateway run' 2>/dev/null || true
    pkill -f 'searx[.]webapp' 2>/dev/null || true
fi

sleep 1
still=""
curl -s -o /dev/null -m 2 http://127.0.0.1:8642/v1/models 2>/dev/null && still="gateway"
curl -s -o /dev/null -m 2 http://127.0.0.1:8888/ 2>/dev/null && still="${still:+$still, }search"

if [[ -n "$still" ]]; then
    # Saying "stopped" without checking is exactly the mistake that made
    # this rewrite necessary.
    echo "Still responding: $still  (check: infiny --status)"
    exit 1
fi
echo "Stopped."
