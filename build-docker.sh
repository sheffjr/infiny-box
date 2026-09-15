#!/bin/bash
# Infiny Box — build the image for macOS and Linux.
#
# The same Dockerfile as the .wsl artifact, a different target. Windows gets
# infiny.wsl (WSL2 is built into the OS and Docker is not needed); macOS and
# Linux get this image.
#
# Run: bash build-docker.sh
set -e
cd "$(dirname "$0")"

IMAGE="${1:-infiny}"

echo "═══ Building Infiny Box (Docker) ═══"
docker build --target container -f Dockerfile -t "$IMAGE" . || {
    echo "⚠ Build failed. Is Docker running?"
    exit 1
}

# Take the size from the same place the user will read it. `image inspect .Size`
# and the SIZE column of `docker images` differ by a factor of three on
# Docker 29 (994 MB against 3.84GB for the same image — different ways of
# counting layers), and printing our own number means looking like a liar the
# first time somebody checks.
SIZE=$(docker images "$IMAGE" --format '{{.Size}}' | head -1)
echo ""
echo "✓ Image $IMAGE is ready (${SIZE:-size unknown})"
echo ""
echo "Run:"
echo "  docker run -it --rm \\"
# The container target runs as root (WORKDIR /root in the Dockerfile), not as
# the `user` account — the volume has to persist /root, or config.yaml, the
# gateway key and the history are lost on every --rm. This used to say
# /home/user: same volume name, but the mount point was an extra empty
# directory and NOTHING was persisted. The build never caught it, because
# docker build does not check the contents of instructions it prints.
echo "    -v infiny-home:/root \\"
# Without this a container on Linux cannot reach the host by name, and endpoint
# discovery is left with the docker0 gateway alone. On Docker Desktop (macOS)
# the alias always exists, so the extra flag is harmless there.
echo "    --add-host=host.docker.internal:host-gateway \\"
echo "    $IMAGE"
echo ""
echo "Connect a model from inside: infiny --setup"
echo "The model server on the host must listen on 0.0.0.0, not 127.0.0.1."
