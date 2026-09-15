#!/bin/bash
# Infiny Box — install the build environment on a clean Debian/Ubuntu.
#
# Why this file exists. On 2026-08-03 the development distribution was wiped
# along with WSL, and it turned out the list of build dependencies was written
# down nowhere — it lived only inside that distribution, configured by hand
# months earlier. Recovering it took FIVE failed builds in a row, each
# revealing exactly one missing thing:
#   buildah    -> "found neither buildah, nor podman, nor a running docker"
#   crun/runc  -> "exec: no command" (nothing to run the container with)
#   nftables   -> "netavark: unable to execute nft"
#   /run/user  -> "Error loading default container config"
#   as root    -> "/etc/hosts: permission denied" in rootless mode
#   netavark   -> 'could not find "netavark" in one of [...]' — surfaced
#                 2026-08-13, the sixth time in the same place: the list was
#                 still incomplete
# Not one of them was predictable. Each had to be hit and fixed.
#
# Run once: bash setup-build-env.sh
set -e

echo "═══ Infiny Box build environment ═══"

if ! command -v apt-get >/dev/null; then
    echo "⚠ Debian or Ubuntu expected. On another distribution, install"
    echo "  buildah, crun and nftables by hand."
    exit 1
fi

echo "→ Installing packages..."
# A bounded number of retries, and timeouts. Without them a single unreachable
# package hangs the install forever in "Tried to start delayed item" — that is
# how the 2026-08-28 build was lost. ForceIPv4 is here because Debian mirrors
# publish AAAA records where no IPv6 route exists, and apt dutifully waits out
# the timeout on every one of them.
APT_OPTS="-o Acquire::Retries=3 -o Acquire::http::Timeout=20 -o Acquire::ForceIPv4=true"

sudo apt-get $APT_OPTS update -qq
sudo apt-get $APT_OPTS install -y --no-install-recommends \
    buildah \
    crun runc \
    nftables iptables \
    netavark aardvark-dns \
    slirp4netns uidmap \
    gzip tar curl git

echo
echo "→ Checking..."
FAIL=0
for b in buildah crun nft tar gzip git curl; do
    if command -v "$b" >/dev/null; then
        printf '  ✓ %s\n' "$b"
    else
        printf '  ✗ %s IS MISSING\n' "$b"; FAIL=1
    fi
done

echo
if [[ $FAIL -ne 0 ]]; then
    echo "⚠ Something is missing — the build will fail. See the output above."
    exit 1
fi

echo "✓ Done. To build:  bash build-wsl.sh"
echo
echo "Note: build-wsl.sh builds as whichever user runs it. Rootless mode needs"
echo "configured subuid/subgid and a working /run/user/\$UID; if namespace"
echo "permissions get in the way, running it under sudo is simpler — the"
echo "container itself still provides the isolation:"
echo "  sudo -E bash build-wsl.sh"
