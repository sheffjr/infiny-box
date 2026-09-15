#!/bin/bash
# Records the README demo. Run it INSIDE the Box — `infiny` only exists there,
# and you are already root.
#
#   bash docs/record-demo.sh              # record everything, then build the gif
#   ONLY=3 bash docs/record-demo.sh       # re-shoot question 3, then rebuild
#   BUILD_ONLY=1 bash docs/record-demo.sh # just rebuild the gif from the casts
#
# WHAT IT IS. Six short exchanges cut together and looped: a question, an
# answer, cut, next. Each one shows a different thing the Box can do, and none
# of them needs a sentence of explanation underneath.
#
# WHY ONE CAST PER QUESTION. A local model gets an answer wrong or rambles now
# and then. Recording separately means a bad take costs one question instead of
# the whole reel — ONLY=n re-shoots it and the rest is untouched.
#
# WHY NOT VHS. charmbracelet/vhs is the obvious tool and it does not work here.
# It drives a headless Chromium through go-rod, Chromium refuses to start as
# root without --no-sandbox (crbug 638180), and once that is patched around the
# screencast still captures zero frames inside this container. Measured
# 2026-09-09. asciinema records the pty directly and agg renders the cast — no
# browser anywhere in the pipeline, which is the part that breaks.
#
# WHY TMUX. asciinema has to record a real terminal. Driving `infiny` with
# expect puts a second pty in the middle: the TUI redraws arrive in a handful of
# buffered chunks and a 231-second session renders as two frames. tmux gives a
# real client to record and a send-keys channel to type into it.

set -u

REPO=${REPO:-/mnt/d/Projects/jarvis}
OUT=${OUT:-$REPO/docs/assets/demo.gif}
CASTS=${CASTS:-/root/casts}
COLS=110
ROWS=30

# question | seconds to wait for the answer
#
# The waits are generous on purpose: cutting on "thinking…" is how the first
# takes were lost, and dead air costs nothing because the merge strips it.
# Search questions get longer — they are three model calls, not one.
QUESTIONS=(
  "what's today's date?|70"
  "who are you?|60"
  "what's the latest version of ollama?|170"
  "how much space is /opt using?|70"
  "какая погода в Нью-Йорке?|170"
  # One step, one unambiguous package name. "install cowsay and make it say
  # hello" read well and the model could not carry it: it installed both the
  # Debian package and the unrelated PyPI project of the same name, the latter
  # landing in /usr/local/bin where it shadowed the real one and broke the very
  # command it had been asked to run. Five minutes in it was still probing
  # `apt-cache policy say`, and the clip ended on a spinner. The limit is a
  # ceiling, not a wait — a fast answer still cuts straight away.
  "install htop|300"
)

need() { command -v "$1" >/dev/null || MISSING="${MISSING:-} $1"; }
need tmux; need asciinema; need agg; need python3
if [ -n "${MISSING:-}" ]; then
  echo "missing:${MISSING}" >&2
  cat >&2 <<'HELP'

  apt-get install -y asciinema tmux python3
  curl -fsSL -o /usr/local/bin/agg \
    https://github.com/asciinema/agg/releases/latest/download/agg-x86_64-unknown-linux-gnu
  chmod +x /usr/local/bin/agg
HELP
  exit 1
fi

export TERM=xterm-256color
mkdir -p "$CASTS"

# The default REPO is a host drive, and the Box mounts none — that is the
# product's promise, not an oversight. Saying so here beats a bare "no such
# file or directory" from the merge step, forty minutes into a recording.
if [ ! -d "$REPO" ]; then
  cat >&2 <<HELP
REPO=$REPO does not exist.

Host drives are not mounted inside the Box on purpose. Either mount one:
    mkdir -p /mnt/d && mount -t drvfs D: /mnt/d
or keep everything in the Box and copy the gif out afterwards:
    REPO=/root/jarvis bash docs/record-demo.sh
HELP
  exit 1
fi

# Wait until the agent has actually answered, rather than for a fixed number of
# seconds. Fixed sleeps lost two whole takes: every clip ended mid-thought and
# the script had no way to know.
#
# The signal is the braille spinner glyph, not the word beside it. Matching
# "thinking…" looks right and is wrong: during tool use the TUI replaces that
# label with what it is doing — "ollama latest version release date", "New York
# weather today" — so the word disappears while the turn is very much still
# running. Three clips were cut mid-search that way on 2026-09-09. The glyph is
# present for every one of those states and gone only when the turn ends.
#
# Three consecutive clear polls, because the spinner is briefly absent between
# steps of a multi-tool turn, and one unlucky sample lands in that gap.
spinner_present() {
  tmux capture-pane -p -t demo 2>/dev/null | grep -q '[⠁-⣿]'
}

wait_for_answer() {
  local max=$1 waited=0 clear=0
  sleep 4                                   # let the spinner appear first
  while [ "$waited" -lt "$max" ]; do
    if spinner_present; then
      clear=0
    else
      clear=$((clear + 1))
      if [ "$clear" -ge 3 ]; then
        # Six seconds, not two. The spinner goes out when the turn ends, but
        # the closing sentence is still streaming: the htop clip stopped on
        # "htop installed and ready at /u", cut mid-path. The merge strips the
        # extra idle again, so this costs nothing on screen.
        sleep 6
        return 0
      fi
    fi
    sleep 2
    waited=$((waited + 2))
  done
  return 1
}

preflight() {
  echo "── preflight: can the agent answer at all?"
  tmux send-keys -t demo "say ok" Enter
  if ! wait_for_answer 180; then
    echo >&2
    echo "The agent never answered. Nothing was recorded." >&2
    echo "Almost always the model endpoint: check that your server is up and" >&2
    echo "reachable from in here, then run 'infiny --status'." >&2
    tmux capture-pane -p -t demo 2>/dev/null | tail -6 >&2
    return 1
  fi
  echo "   ok"
}

start_session() {
  tmux kill-session -t demo 2>/dev/null
  tmux new-session -d -s demo -x "$COLS" -y "$ROWS"
  # tmux's own status line is recording apparatus, not product. asciinema
  # records the attached client whole, so without this the green bar — session
  # name, window list, and the host's machine name — sits in every frame of the
  # README's first image.
  tmux set-option -t demo status off
  # Everything the viewer does not need happens before any camera is on:
  # starting the agent, and turning off the approval prompt that would stall a
  # take. The model stays loaded across all six questions, which is also why
  # the first answer is not slower than the rest.
  tmux send-keys -t demo "infiny" Enter
  sleep 14
  tmux send-keys -t demo "/mode yolo" Enter
  sleep 5
}

record_one() {
  local idx=$1 q=$2 max=$3
  echo "── [$idx] $q"
  # /new drops the previous exchange so every clip opens on a clean prompt.
  # It also keeps each answer honest: no question is helped by the one before.
  tmux send-keys -t demo "/new" Enter
  sleep 5
  # setsid puts the recorder in its own process group. asciinema runs as three
  # processes, and a signal sent to the single pid in $! reaches none of the
  # other two: two separate takes left it alive for three quarters of an hour
  # after the client had detached, surviving both INT and TERM, with the whole
  # reel stuck behind question one. Signalling -$rec hits the group.
  setsid asciinema rec --overwrite -c "tmux attach -t demo" "$CASTS/$idx.cast" >/dev/null 2>&1 &
  local rec=$!
  sleep 2
  # The clear happens INSIDE the recording, on purpose. Attaching a client makes
  # tmux repaint the pane, and agg renders that repaint as a broken welcome
  # panel — border fragments strewn across the top of the frame. Clearing from
  # within the cast gives the TUI a full, clean redraw that renders correctly,
  # and merge-casts.py then drops everything up to the clear, so neither the
  # broken repaint nor the "/clear" line itself survives into the gif.
  tmux send-keys -t demo "/clear" Enter
  sleep 5
  local t0=$SECONDS
  tmux send-keys -t demo "$q" Enter
  if ! wait_for_answer "$max"; then
    echo "   ! no answer in ${max}s — clip will be dead air" >&2
    FAILED="${FAILED:-} $idx"
  fi
  tmux detach-client -s demo 2>/dev/null
  # asciinema normally notices the client is gone and exits by itself — measured
  # at two seconds. It does not always: one take left the recorder alive for
  # thirty minutes with nothing attached, and `wait` held the whole reel behind
  # question one. SIGINT is asciinema's documented stop signal and it still
  # finalises the cast, so a nudged clip is a usable clip.
  for _ in $(seq 1 20); do
    kill -0 "$rec" 2>/dev/null || break
    sleep 0.5
  done
  if kill -0 "$rec" 2>/dev/null; then
    echo "   recorder did not exit on detach — stopping its process group"
    kill -INT  -"$rec" 2>/dev/null
    sleep 3
    kill -TERM -"$rec" 2>/dev/null
    sleep 2
    kill -KILL -"$rec" 2>/dev/null
  fi
  wait "$rec" 2>/dev/null
  echo "   answered in $((SECONDS - t0))s, $(du -h "$CASTS/$idx.cast" 2>/dev/null | cut -f1)"
}

if [ -z "${BUILD_ONLY:-}" ]; then
  start_session
  if ! preflight; then
    tmux kill-session -t demo 2>/dev/null
    exit 1
  fi
  for i in "${!QUESTIONS[@]}"; do
    n=$((i + 1))
    # ONLY takes one number or several: ONLY=3 or ONLY="3 5 6"
    if [ -n "${ONLY:-}" ] && ! printf '%s\n' ${ONLY} | grep -qx "$n"; then
      continue
    fi
    IFS='|' read -r q w <<< "${QUESTIONS[$i]}"
    record_one "$n" "$q" "$w"
  done
  tmux kill-session -t demo 2>/dev/null
  if [ -n "${FAILED:-}" ]; then
    echo >&2
    echo "questions that never answered:${FAILED}" >&2
    echo "re-shoot one with: ONLY=<n> bash docs/record-demo.sh" >&2
  fi
fi

python3 "$REPO/docs/merge-casts.py" "$CASTS" /root/demo.cast || exit 1

# --idle-time-limit is a second safety net; the merge has already flattened the
# long thinking pauses. --speed stays low because the content is already tight,
# and speeding up readable text only makes it unreadable.
THEME="0E1116,C9D1D9,0E1116,F47067,57AB5A,C69026,539BF5,B083F0,39C5CF,C9D1D9,545D68,FF938A,6BC46D,DAAA3F,6CB6FF,DCBDFB,56D4DD,ECF2F8"
mkdir -p "$(dirname "$OUT")"
agg --theme "$THEME" --font-size 16 --speed 1 --idle-time-limit 1 --fps-cap 12 \
    /root/demo.cast "$OUT" || exit 1

echo
echo "gif: $OUT ($(du -h "$OUT" | cut -f1))"
