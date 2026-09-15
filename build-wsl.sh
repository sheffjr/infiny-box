#!/bin/bash
# Infiny Box — build the portable .wsl (one file, runs on Windows)
#
# Produces infiny.wsl: the user installs it with a single command and gets an
# isolated agentic Linux. No ISO, no USB stick, no bare metal.
#
# Run inside WSL2 or on Linux: bash build-wsl.sh
#
# The engine picks itself. Docker Desktop is no longer required — on the
# development machine it regularly fails to start, and tying artifact releases
# to the least reliable link in the chain is a bad trade. buildah and podman
# work without a daemon and rootless.
set -e
cd "$(dirname "$0")"

OUT="infiny.wsl"
ROOTFS_TAR="infiny-rootfs.tar"
IMAGE="infiny-wsl"

echo "═══ Building Infiny Box (.wsl) ═══"

# ── 1. Pick an engine ─────────────────────────────────────────
# Order: buildah (daemonless, already present in the build image) → podman →
# docker. Docker comes last precisely because of the daemon dependency.
ENGINE=""
for e in buildah podman docker; do
    if command -v "$e" >/dev/null 2>&1; then
        # A docker without a live daemon is useless, so test rather than trust
        # the binary: WSL carries a Docker Desktop CLI shim that exists even
        # when Docker itself is down.
        if [[ "$e" == "docker" ]] && ! docker version >/dev/null 2>&1; then
            continue
        fi
        ENGINE="$e"
        break
    fi
done

if [[ -z "$ENGINE" ]]; then
    echo "⚠ Found neither buildah, nor podman, nor a running docker."
    echo "  Debian/Ubuntu:  sudo apt install buildah"
    exit 1
fi
echo "→ Engine: $ENGINE"

# ── 2. Build the rootfs (the wsl target of the shared Dockerfile) ──
echo "→ Building the image..."
case "$ENGINE" in
    buildah) buildah bud   --target wsl -f Dockerfile -t "$IMAGE" . ;;
    podman)  podman build  --target wsl -f Dockerfile -t "$IMAGE" . ;;
    docker)  docker build  --target wsl -f Dockerfile -t "$IMAGE" . ;;
esac

# ── 3. Export a FLAT tar ──────────────────────────────────────
# WSL expects a rootfs: an ordinary filesystem tar, not a layered OCI archive.
# Hence `export` rather than `save`.
echo "→ Exporting the rootfs..."
rm -f "$ROOTFS_TAR"
case "$ENGINE" in
    buildah)
        # buildah has no export, so we mount the container and tar it ourselves.
        #
        # `buildah unshare` is needed ONLY in rootless mode, where mounting
        # requires a user namespace and fails with Permission denied without it.
        # As root it is not needed and actively harmful — the wrapper swallowed
        # errors, and the build failed at export with no message at all
        # (2026-08-03).
        if [[ $EUID -eq 0 ]]; then
            ctr=$(buildah from "$IMAGE")
            mnt=$(buildah mount "$ctr")
            tar -C "$mnt" -cf "$PWD/$ROOTFS_TAR" .
            buildah umount "$ctr" >/dev/null
            buildah rm "$ctr" >/dev/null
        else
            buildah unshare bash -euc '
                ctr=$(buildah from "'"$IMAGE"'")
                mnt=$(buildah mount "$ctr")
                tar -C "$mnt" -cf "'"$PWD/$ROOTFS_TAR"'" .
                buildah umount "$ctr" >/dev/null
                buildah rm "$ctr" >/dev/null
            '
        fi
        ;;
    podman|docker)
        CID=$($ENGINE create "$IMAGE")
        $ENGINE export "$CID" -o "$ROOTFS_TAR"
        $ENGINE rm "$CID" >/dev/null
        ;;
esac

[[ -s "$ROOTFS_TAR" ]] || { echo "⚠ the rootfs is empty — the build failed"; exit 1; }

# ── 3a. Strip the container engine's own fingerprint ──────────
# `docker create` stamps /.dockerenv into the container filesystem and `export`
# captures it faithfully, so the .wsl shipped a file announcing "you are inside
# Docker" to everything that asks. Inside WSL that is false.
#
# Not cosmetic. The acceptance suite tells a container from a WSL distribution
# by exactly this file, so it took the container branch, skipped the drvfs
# isolation check entirely — the single most important check in the suite — and
# reported a tick for it. Our self-healing skill reads the same file.
#
# It surfaced only now because the engine order is buildah → podman → docker and
# earlier builds ran under buildah, which creates no such file. A release built
# on a machine that only has docker would have shipped it.
if tar -tf "$ROOTFS_TAR" .dockerenv >/dev/null 2>&1; then
    echo "→ Removing /.dockerenv left behind by $ENGINE..."
    tar --delete -f "$ROOTFS_TAR" .dockerenv
    ! tar -tf "$ROOTFS_TAR" .dockerenv >/dev/null 2>&1 \
        || { echo "⚠ could not remove /.dockerenv from the rootfs"; exit 1; }
fi

# ── 4. gzip it (what Microsoft recommends for .wsl) ───────────
echo "→ Packing into $OUT..."
gzip -c "$ROOTFS_TAR" > "$OUT"
rm -f "$ROOTFS_TAR"

SIZE=$(du -sh "$OUT" | cut -f1)
echo ""
echo "✓ $OUT is ready ($SIZE)"
echo ""
echo "Install on Windows:"
echo "  wsl --install --from-file $OUT"
echo "Run:"
echo "  wsl -d Infiny        (or the Infiny shortcut in the Start menu)"
echo "The first run offers to connect a model."
