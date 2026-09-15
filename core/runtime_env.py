"""
Infiny — working out which environment we are running in.

The module is called runtime_env rather than platform on purpose:
`core/platform.py` would shadow the standard `platform` module for any code
that ends up running with `core/` on sys.path. Debugging that costs hours.

Why it deserves its own module: the goal is "runs everywhere", and every
platform sandboxes differently (WSL2 on Windows, Docker/Podman on Linux and
macOS, bare Linux with no container at all). The differences are few but
scattered, and each one looks like a harmless detail — which is exactly how you
end up with a module that "somehow only works on the developer's machine".
Everything platform-specific lives here.

VERIFICATION STATUS (do not confuse tested with assumed):
  - WSL2 in NAT mode .......... TESTED on a live machine 2026-07-29
  - everything else ........... from documentation, NOT tested

So the functions here do not "know" the answer; they return a *list of
candidates* that gets checked by an actual probe anyway. Getting the candidate
order wrong costs a second; getting a hardcoded address wrong means "endpoint
not found" on a working system. That has already happened: for a year detection
talked to the WSL DNS proxy instead of the gateway and silently found nothing.
"""
import os
import re
import subprocess
import sys
from pathlib import Path

# The name under which the host machine is visible from inside Docker Desktop
# (Windows and macOS). On Linux, Docker does NOT create it — you need to run
# with `--add-host=host.docker.internal:host-gateway`. We keep it in the
# candidate list unconditionally: an extra address that fails to resolve costs
# one failed probe, whereas its absence on macOS means nothing is found at all.
DOCKER_HOST_ALIAS = "host.docker.internal"

WSL = "wsl"
DOCKER = "docker"
LINUX = "linux"
MACOS = "macos"
UNKNOWN = "unknown"


def detect_runtime() -> str:
    """
    Where we are running: wsl | docker | linux | macos | unknown.

    The order of checks is not arbitrary: Docker before WSL. It used to be the
    other way round, and that was a bug — Docker Desktop on Windows runs its
    containers on the same WSL2 kernel as ordinary distributions, so
    `/proc/sys/kernel/osrelease` inside ANY container started through Docker
    Desktop also contains "microsoft". Checking WSL first caught that as a false
    positive: detect_runtime() returned "wsl" inside a plain Docker container,
    host_candidates() never added host.docker.internal, and the wizard's
    endpoint discovery silently found nothing even though the host server was
    reachable. Caught by test-box.sh inside the Docker target on 2026-08-31:
    discover() returned [] while curl to host.docker.internal:11434 answered 200
    from that same container.
    /.dockerenv is a reliable marker of a container specifically, and never
    exists in a real WSL distribution, so checking it first is safe.
    """
    if sys.platform == "darwin":
        return MACOS
    if sys.platform != "linux":
        return UNKNOWN

    if Path("/.dockerenv").exists():
        return DOCKER
    try:
        cgroup = Path("/proc/1/cgroup").read_text()
        if "docker" in cgroup or "containerd" in cgroup or "podman" in cgroup:
            return DOCKER
    except OSError:
        pass

    if os.environ.get("WSL_DISTRO_NAME") or os.environ.get("WSL_INTEROP"):
        return WSL
    try:
        # WSL1 and WSL2 both write "microsoft" here.
        if "microsoft" in Path("/proc/sys/kernel/osrelease").read_text().lower():
            return WSL
    except OSError:
        pass

    return LINUX


def default_gateway() -> str | None:
    """
    The default gateway — the address at which the host is visible from inside
    the sandbox.

    Works identically for WSL2/NAT (a gateway like 172.22.x.1) and for Docker on
    Linux (the docker0 bridge gateway, usually 172.17.0.1). That sameness is the
    main reason the Linux path costs almost nothing: it is the same mechanism.

    We deliberately do NOT use the nameserver from /etc/resolv.conf. Measured
    2026-07-29: it holds 10.255.255.254, the WSL DNS proxy, which does not
    forward arbitrary ports and never answers on :11434. The real gateway was
    172.22.144.1.
    """
    try:
        out = subprocess.run(
            ["ip", "route", "show", "default"],
            capture_output=True, text=True, timeout=5,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r"default\s+via\s+(\d+\.\d+\.\d+\.\d+)", out)
    return m.group(1) if m else None


def host_candidates() -> list[str]:
    """
    Addresses where the user's host might be reachable. Order is priority.

    127.0.0.1 always comes first: it is correct both for WSL with
    networkingMode=mirrored and for bare Linux, where there is no sandbox and
    the "host" is us.
    """
    runtime = detect_runtime()
    candidates = ["127.0.0.1"]

    if runtime in (WSL, DOCKER):
        gw = default_gateway()
        if gw and gw not in candidates:
            candidates.append(gw)

    if runtime == DOCKER and DOCKER_HOST_ALIAS not in candidates:
        # On Docker Desktop (macOS/Windows) the gateway above points at the
        # internal Linux VM rather than at the user's machine, and is therefore
        # useless. Only the alias works here.
        candidates.append(DOCKER_HOST_ALIAS)

    return candidates


def sandbox_hint() -> str:
    """
    A human explanation of why a server on the host might not be visible.

    The text depends on the environment: "set OLLAMA_HOST=0.0.0.0" is
    meaningless on bare Linux, where we are already on localhost, and there it
    would only confuse.
    """
    # Local import: core/i18n.py pulls in stdlib only, but runtime_env is called
    # from places where extra module-level imports are unwelcome.
    from core.i18n import t as _

    runtime = detect_runtime()
    if runtime == WSL:
        return _("sandbox_wsl")
    if runtime == DOCKER:
        return _("sandbox_docker")
    return _("sandbox_native")
