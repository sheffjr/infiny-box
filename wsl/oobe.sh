#!/bin/bash
# OOBE — runs once, when the distribution is installed.
set -e
echo ""
echo "  ╔═══════════════════════════════════════╗"
echo "  ║   Infiny — agentic Linux for Windows   ║"
echo "  ╚═══════════════════════════════════════╝"
echo ""
echo "  Setting things up on first run..."
# The 'user' account already exists in the image; this only confirms it.
if ! id user &>/dev/null; then
    useradd -m -s /bin/bash user
    echo "user ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers.d/infiny
fi
echo "  Done. Run:  infiny"
echo ""
