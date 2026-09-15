#!/usr/bin/env python3
"""Cut the recorded question clips together into one asciicast.

Each clip is a whole exchange recorded in real time, and most of its duration is
the model thinking. The obvious fix — collapse the long pauses — does not work
here: the agent's TUI repaints a spinner every ~100ms, so there are no pauses to
collapse. Measured 2026-09-09, a 71.8s clip came out at 71.2s.

So this scales time instead of removing it. Every event is kept, which is what
keeps the terminal state consistent; only the timestamps move. The head of a
clip (the question landing) and its tail (the finished answer) play at real
speed, and the middle is compressed to a fixed budget however long it actually
took. A 172s clip and a 62s clip therefore produce the same length on screen.

Usage: merge-casts.py <casts-dir> <output.cast>
"""
import json
import sys
from pathlib import Path

HEAD_SRC = 3.0   # seconds of source treated as "the question arriving"
HEAD_OUT = 1.0   # ...played back in this long
TAIL_SRC = 7.0   # seconds of source treated as "the answer landing"
TAIL_OUT = 1.1   # ...played back in this long
MID_OUT = 0.7    # everything between, whatever its real duration
HOLD = 1.5       # still frame on the finished answer before the next question
TAIL_TRIM = 0.4  # status bar ticking after the answer is already complete
# How far into a clip to look for its opening clear. The recorder clears about
# two seconds in and sends the question about five seconds after that, so the
# window only has to cover the gap — and must stay well short of the answer,
# where the TUI clears again on its own.
HEAD_SCAN = 6.5
MIN_KEEP = 0.5    # a head trim may never eat more than half a clip's events

def is_clear(data):
    """True if this chunk wipes the whole screen.

    The obvious marker, erase-display, is not the one that matters: measured on
    a real cast, the only \\x1b[2J came from tmux's redraw at second zero, while
    the TUI's own /clear arrived as home-cursor followed by erase-to-end. That
    clears just as completely, so both forms count.

    Cursor-addressed erases like \\x1b[16;1H...\\x1b[J are deliberately excluded:
    those erase from partway down and leave the top of the screen standing, so
    the events before them are still load-bearing.
    """
    if "\x1b[2J" in data or "\x1b[3J" in data:
        return True
    home = data.find("\x1b[H")
    return home != -1 and "\x1b[J" in data[home:]


def load(path):
    header, events = None, []
    for i, line in enumerate(path.read_text(encoding="utf-8",
                                            errors="replace").splitlines()):
        line = line.strip()
        if i == 0:
            header = json.loads(line)
            continue
        if not line.startswith("["):
            continue
        try:
            t, kind, data = json.loads(line)
        except (ValueError, TypeError):
            continue
        if kind == "o":
            events.append((t, data))
    return header, events


def trim_head(events):
    """Drop everything before the clip's opening screen clear, and rebase time.

    Dropping leading events is normally forbidden here — the screen is built by
    the byte stream, so cutting the front loses content. A clear-display is the
    one exception: after it, nothing before it can still be on screen, so the
    prefix is provably redundant.

    What that prefix contains is worth losing. Attaching the recorder makes tmux
    repaint the pane, and agg renders that repaint as a shattered welcome panel
    — border fragments scattered across the top of every frame until they scroll
    away. The echo of the "/clear" line goes with it.

    No clear found (an old cast, or a TUI that stops using rich) means the clip
    is returned untouched, which is the previous behaviour.
    """
    last = None
    for i, (t, data) in enumerate(events):
        if t > HEAD_SCAN:
            break
        if is_clear(data):
            last = i
    if last is None:
        return events, 0.0
    if len(events) - last < len(events) * MIN_KEEP:
        # A clear this deep into the clip is not the opening one, it is the TUI
        # repainting mid-answer. Trimming to it throws the clip away: a 12s
        # question whose only clear sat at second 12 came out as two events.
        return events, 0.0
    t0 = events[last][0]
    return [(t - t0, data) for t, data in events[last:]], t0


def remap(t, end):
    """Source timestamp -> output timestamp, three segments, all monotonic."""
    head_src = min(HEAD_SRC, end)
    tail_start = max(head_src, end - TAIL_SRC)

    if t <= head_src:
        frac = t / head_src if head_src else 0.0
        return frac * HEAD_OUT
    if t < tail_start:
        span = tail_start - head_src
        frac = (t - head_src) / span if span else 0.0
        return HEAD_OUT + frac * MID_OUT
    span = end - tail_start
    frac = (t - tail_start) / span if span else 0.0
    return HEAD_OUT + MID_OUT + frac * TAIL_OUT


def main():
    if len(sys.argv) != 3:
        print(__doc__.strip(), file=sys.stderr)
        return 2

    casts_dir, out_path = Path(sys.argv[1]), Path(sys.argv[2])
    clips = sorted(casts_dir.glob("*.cast"), key=lambda p: int(p.stem))
    if not clips:
        print(f"no .cast files in {casts_dir}", file=sys.stderr)
        return 1

    header, merged, clock = None, [], 0.0

    for clip in clips:
        head, events = load(clip)
        if not events:
            print(f"  ! {clip.name}: empty, skipped", file=sys.stderr)
            continue
        if header is None:
            header = head

        events, cut = trim_head(events)
        if not events:
            print(f"  ! {clip.name}: nothing left after the head trim",
                  file=sys.stderr)
            continue

        raw_end = events[-1][0]
        end = max(raw_end - TAIL_TRIM, 0.001)
        kept = [[round(clock + remap(t, end), 3), "o", data]
                for t, data in events if t <= end]
        if not kept:
            print(f"  ! {clip.name}: nothing left after trim", file=sys.stderr)
            continue

        merged.extend(kept)
        print(f"  {clip.name}: {raw_end:6.1f}s recorded -> "
              f"{kept[-1][0] - kept[0][0]:4.1f}s on screen "
              f"({len(kept)} events, {cut:.1f}s trimmed off the front)")
        clock = kept[-1][0] + HOLD

    if not merged:
        print("nothing to merge", file=sys.stderr)
        return 1

    header.pop("duration", None)
    header.pop("idle_time_limit", None)
    with out_path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(header) + "\n")
        for ev in merged:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")

    print(f"\n{len(clips)} clips -> {out_path}  ({merged[-1][0]:.1f}s total)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
