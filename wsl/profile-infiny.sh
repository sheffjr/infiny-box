# Start Infiny automatically on interactive login.
# Installed as /etc/profile.d/50-infiny.sh
#
# Why: there are two ways in, and they gave different first impressions.
#   * the shortcut from our installer calls `wsl -d Infiny -u root -- infiny`,
#     landing the user straight in Infiny;
#   * double-clicking infiny.wsl (WSL's own path) creates its own shortcut,
#     which opens a bare bash. The user sees `root@Infiny:~#` and has to work
#     out for themselves that they should type `infiny`.
# The second path is the more natural one — most people will take it — and it
# was the worse one. Now both lead to the same place.
#
# Be careful with the conditions: this file runs on every login, including
# non-interactive invocations like `wsl -d Infiny -- bash script.sh`. Starting
# an interactive agent there would break any automation, including our own
# acceptance suite, test-box.sh.

# Interactive shells only.
case $- in
    *i*) ;;
    *)   return ;;
esac

# Only when there is a real terminal.
[ -t 0 ] || return

# Escape hatch: INFINY_NO_AUTOSTART=1 gives a plain bash with no agent.
[ -n "${INFINY_NO_AUTOSTART:-}" ] && return

# Guard against re-entry (the agent may open a nested shell).
[ -n "${INFINY_AUTOSTARTED:-}" ] && return
export INFINY_AUTOSTARTED=1

# No exec: when the user leaves Infiny they land in an ordinary shell rather
# than a closed window. A sandbox is a tool, not a kiosk.
infiny
