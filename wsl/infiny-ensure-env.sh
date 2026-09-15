#!/bin/bash
# Prepares ~/.hermes/.env before the gateway starts.
#
# Split out of infiny-start.sh into its own file because the unit's ExecStartPre
# now does the same job: systemd brings the gateway up at boot, BEFORE anyone
# runs the CLI, and .env has to exist by then.
#
# BOTH variables are required, which is not obvious:
#   API_SERVER_ENABLED=true — turns on the OpenAI-compatible server on :8642;
#                             without it there is no endpoint whatsoever;
#   API_SERVER_KEY          — the Bearer token; the server will not start
#                             without one.
# A fresh image has no .env, so the CLI got 401 and said nothing — which looked
# like "the agent is broken".
#
# SEARXNG_URL enables Hermes' BUILT-IN web_search through our own SearXNG.
# Without it the built-in search is dead (check_web_api_key() = False) and is
# silently cut by the gate, leaving the agent with no search at all — exactly
# the bug that survived two weeks.
#
# The key is generated per installation. Baking a shared one into the image is
# not an option: it would be identical for everyone who downloads the Box.
set -u

# A systemd service has NO $HOME — and with `set -u` this script died on
# `HOME: unbound variable`, which made ExecStartPre return 1 and left the
# gateway in an endless restart loop (the counter reached 20 within a minute).
# Caught on the very first clean install with the supervisor, 2026-08-24.
HERMES_HOME="${HERMES_HOME:-${HOME:-/root}/.hermes}"
ENV_FILE="$HERMES_HOME/.env"

mkdir -p "$HERMES_HOME"
touch "$ENV_FILE"

grep -q '^API_SERVER_ENABLED=' "$ENV_FILE" 2>/dev/null || \
    echo 'API_SERVER_ENABLED=true' >> "$ENV_FILE"

grep -q '^API_SERVER_KEY=' "$ENV_FILE" 2>/dev/null || \
    printf 'API_SERVER_KEY=%s\n' \
        "$(head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')" >> "$ENV_FILE"

grep -q '^SEARXNG_URL=' "$ENV_FILE" 2>/dev/null || \
    echo 'SEARXNG_URL=http://127.0.0.1:8888' >> "$ENV_FILE"

chmod 600 "$ENV_FILE"

# SearXNG's secret_key, for the same reason as API_SERVER_KEY above: baked into
# the image it would be identical for EVERYONE who downloaded the Box.
# settings.yml carries the placeholder "infiny-change-me-in-production", and it
# would have stayed that way.
#
# The risk is lower here than for the gateway key (SearXNG listens on 127.0.0.1
# only, and the limiter is off), but explaining why every user shares one secret
# costs more than generating a real one once at first boot.
SEARX_SETTINGS=/etc/searxng/settings.yml
if [[ -w "$SEARX_SETTINGS" ]] && grep -q 'infiny-change-me-in-production' "$SEARX_SETTINGS"; then
    # The key is strictly hexadecimal, so by construction it cannot contain
    # anything that would break sed.
    SEARX_KEY="$(head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')"
    sed -i "s|infiny-change-me-in-production|$SEARX_KEY|" "$SEARX_SETTINGS"
    unset SEARX_KEY
fi
