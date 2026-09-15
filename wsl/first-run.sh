#!/bin/bash
# Runs when the distribution boots (wsl.conf boot.command). Idempotent.
#
# Phase 1, "Infiny Box": there is NO model in the box. Downloading llama-server
# and Qwen3-4B was removed from here — not as "not working yet" but on purpose:
#   * the binary was fetched by a static asset name
#     (releases/latest/download/llama-bin-ubuntu-x64.zip) which almost certainly
#     returns 404, and the error was swallowed by `2>/dev/null || echo` — so the
#     failure was invisible;
#   * the model weighed 2.6 GB and downloaded on first start, which killed the
#     "two clicks" promise and made installation impossible without internet;
#   * on CPU that combination gave a 250s time to first token (round 1), so even
#     the successful path was unusable.
# The user brings their own model: `infiny --setup`.
LOG=/tmp/infiny-boot.log
exec >> "$LOG" 2>&1
echo "=== Infiny boot $(date) ==="

# Emergency Hermes install — only if the image was built without network and has
# no brain at all. Normally this is never reached: the Dockerfile installs
# hermes-agent from PyPI and fails the build if that does not work.
#
# This used to read `su - user -c ...`, which was wrong twice over. The Box runs
# as root (wsl.conf: default=root, units: HOME=/root), so the install landed in
# /home/user/.hermes — somewhere nothing ever looks afterwards. And `|| true`
# swallowed any failure, so a Box with no brain looked healthy: exactly the
# "invisible failure" pattern that already cost us time on llama-server.
if ! command -v hermes &>/dev/null && [[ ! -x /opt/hermes-venv/bin/hermes ]]; then
    echo "→ Hermes missing from the image - installing (needs network)..."
    if curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash; then
        echo "→ Hermes installed."
    else
        # Not swallowed. A Box without Hermes does not work, and the user needs
        # to learn that here rather than from "gateway not responding" three
        # steps into the wizard.
        echo "!! Hermes install FAILED. The Box has no agent."
        echo "!! Check the network and rerun:  bash /opt/infiny/first-run.sh"
    fi
fi

echo "=== boot script done ==="
