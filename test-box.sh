#!/bin/bash
# Infiny Box acceptance — checks exactly what a real user would do.
#
# Run INSIDE an installed Box:
#   wsl -d Infiny -u root bash /opt/infiny/test-box.sh  (Windows)
#   docker run -it infiny bash /opt/infiny/test-box.sh  (macOS/Linux)
#
# From /opt/infiny rather than from a host drive: drives are no longer mounted
# automatically (see check 1), so a path like /mnt/d/... simply does not exist
# in a fresh Box.
#
# Requires a running OpenAI-compatible endpoint on the host (Ollama or similar)
# listening on 0.0.0.0 — otherwise it is invisible from the sandbox, see
# explain_not_found().
#
# A note about the test rig: all WSL2 distributions share one network stack. If
# a hermes gateway is running in another distribution it occupies :8642 and the
# Box cannot start — while the port still listens and no process inside the Box
# owns it. Kill the other gateway before running.
set -u
cd /opt/infiny

FAIL=0
ok(){ echo "  ✓ $1"; }
no(){ echo "  ✗ $1"; FAIL=1; }
# A third outcome besides "works" and "broken": the outside world is
# temporarily unavailable. Mixing that with failure is not acceptable — the
# suite would then block a release over somebody else's rate limit, and people
# stop looking at a red that means nothing.
warn(){ echo "  ⚠ $1"; }

# Look for keys in the YAML rather than anywhere in the file: the words
# base_url and default appear in config.yaml comments, and a naive grep gives a
# false failure.
yaml_key(){ sed 's/#.*//' "$1" | grep -A8 '^model:' | grep -qE "^\s+$2:"; }

echo "════ 1. THE SANDBOX IS ISOLATED ════"
# The product's central promise: "a container you can afford to break". While
# WSL mounted host drives under /mnt by itself, that promise was false — the
# agent runs as root without confirmations, and nothing at all stood between it
# and the user's real files. We check the result, not the setting: is a drive
# actually mounted?
#
# We read the mount table rather than asking whether /mnt is empty. It never is,
# even on a healthy Box: WSL keeps its own wsl and wslg directories there, so an
# emptiness check would fail every single time.
DRV=$(mount | grep -c ' type drvfs ')
LETTERS=$(ls -d /mnt/[a-z] 2>/dev/null | tr '\n' ' ')
if [ "$DRV" != "0" ]; then
  no "host drives are mounted ($DRV drvfs) — the sandbox can see user files"
elif [ -n "$LETTERS" ]; then
  no "drive letters present in /mnt: $LETTERS"
else
  ok "host drives are not mounted"
fi
# And separately: that mounting by hand is still possible. Isolation by default
# must not turn into "you cannot share a folder at all" — README promises
# `mount -t drvfs D: /mnt/d`, and a promise should be tested rather than
# declared.
#
# We test by actually mounting, because the indirect signals lie: drvfs does NOT
# appear in /proc/filesystems at all (WSL attaches it with its own mount
# helper), and checking that list answered "not WSL" on a live WSL — a check
# incapable of failing correctly under any outcome.
#
# /.dockerenv is tested FIRST and short-circuits the "microsoft" check in
# /proc/version: Docker Desktop on Windows runs containers on the same WSL2
# kernel as ordinary distributions, so /proc/version inside ANY container
# started through Docker Desktop also contains "microsoft". The old check took a
# plain Docker container for WSL and went looking for drvfs, which cannot exist
# there. Caught live 2026-08-31 running this very suite inside the container
# target: the section took the WSL branch and failed on "mount -t drvfs did not
# work", when the only real breakage was the suite confusing Docker with WSL.
if [ ! -e /.dockerenv ] && grep -qi microsoft /proc/version 2>/dev/null; then
  MP=$(mktemp -d /tmp/infiny-drvfs-XXXXXX)
  # ro: the goal is to prove mounting is possible, not to acquire write access
  # to the host disk in the middle of an acceptance run.
  if mount -t drvfs -o ro C: "$MP" 2>/dev/null; then
    umount "$MP" 2>/dev/null
    # Whether it detached is part of the check, not cleanup: a suite that leaves
    # a host drive mounted behind it will lie about an automount regression on
    # the next run.
    if mount | grep -q ' type drvfs '; then
      no "the test mount did not detach — the Box is left holding a host drive"
    else
      ok "a folder can be mounted by hand and unmounted again"
    fi
  else
    no "mount -t drvfs failed — sharing a folder has become impossible"
  fi
  rmdir "$MP" 2>/dev/null
else
  ok "not WSL — drvfs does not apply"
fi

echo
echo "════ 2. THE IMAGE IS CLEAN ════"
yaml_key hermes/config.yaml base_url && no "base_url left in the config template" \
                                     || ok "no model configured — as it should be"
# We check NOT that .env is absent but that the key was generated locally.
# Requiring absence was wrong: the Box creates .env on the first login, so by
# the time this runs it legitimately exists. What matters is that the key is not
# baked into the image, shared by everyone. Absence from the image itself is
# checked at build time; here we look at the key's shape — ensure_gateway_env()
# generates 64 hexadecimal characters (secrets.token_hex(32)).
if [ -f ~/.hermes/.env ]; then
  KEY=$(grep -m1 '^API_SERVER_KEY=' ~/.hermes/.env 2>/dev/null | cut -d= -f2-)
  if printf '%s' "$KEY" | grep -qE '^[0-9a-f]{64}$'; then
    ok "gateway key generated locally (64 hex)"
  else
    no "gateway key looks wrong: '${KEY:0:12}...' (${#KEY} chars)"
  fi
else
  ok ".env not created yet — it appears on first run"
fi

echo
echo "════ 3. TOOLS ════"
for c in yazi fd rg fzf file less node git pkill hermes infiny; do
  command -v "$c" >/dev/null && ok "$c" || no "$c IS MISSING"
done

echo
echo "════ 4. THE MODEL CONNECTION WIZARD ════"
# The model's position in the list can be given as an argument:
#   bash test-box.sh 3
# The default is the first, which is what a real person would pick. But if the
# first happens to be a large model, a cold load eats minutes — so for repeat
# runs it is convenient to name a deliberately light one.
MODEL_N="${1:-1}"
OUT=$(printf '1\n%s\n' "$MODEL_N" | ./venv/bin/python cli.py --setup 2>&1)

# We match phrases in BOTH languages. The wizard is bilingual (core/i18n.py,
# English by default, `/lang ru` switches), and this suite must not depend on
# whichever language sits in ~/.infiny/lang.
#
# This is not hypothetical caution: on 2026-09-03 translating the wizard into
# English brought down section 4 entirely — "tool calling failed", "gateway did
# not start" — while section 5 in the same run got a perfectly good answer from
# the agent. The product worked; the test, still looking for Russian strings,
# lied.
echo "$OUT" | grep -E "Подключаю|Connecting" | tail -1
echo "$OUT" | grep -qE "Вызов инструментов работает|Tool calling works" \
  && ok "tool calling verified" || no "tool calling failed"
echo "$OUT" | grep -qE "Infiny на связи|Infiny is online" \
  && ok "gateway came up" || no "gateway did not come up"

# The context window has to reach the config as a measured value. Without it
# Hermes takes the architectural maximum from the GGUF (262,144) and behaves as
# though space were unlimited: history compression fires at the wrong time, and
# its own small-window guard never fires at all, because it compares against
# that same inflated number.
#
# We read the LIVE config, not the repository template. Check 2 above looks at
# hermes/config.yaml and is right to: no model belongs there. The wizard writes
# to ~/.hermes/config.yaml, and reading the template produced an eternal "not
# measured" — a failure indistinguishable from a real one.
LIVE=~/.hermes/config.yaml
CTX=$(sed 's/#.*//' "$LIVE" 2>/dev/null | grep -A12 '^model:' \
      | grep -oE '^\s+context_length:\s*[0-9]+' | grep -oE '[0-9]+' | head -1)
if [ -n "$CTX" ]; then
  ok "context window written to the config: $CTX"
  echo "$OUT" | grep -qE "Окно контекста|Context window" \
    || no "written to the config but never shown to the user"
  # The threshold is duplicated from core/model_source.HERMES_MINIMUM_CONTEXT on
  # purpose: the suite should also catch the case where that constant is quietly
  # lowered in the code.
  if [ "$CTX" -lt 64000 ]; then
    echo "$OUT" | grep -qE "ВНИМАНИЕ|WARNING" \
      && ok "window is small ($CTX) — the warning was shown" \
      || no "window is small ($CTX) and the user was not warned"
  fi
else
  # Not a failure: the server may not be Ollama-compatible, and then writing
  # nothing is more honest than inventing a number. But telling that apart from
  # a broken measurement needs human eyes, so we say it plainly.
  echo "  · context window not measured — the server did not serve /api/ps"
fi

echo
echo "════ 5. THE AGENT ANSWERS ════"
# Three attempts, not one. Not because "it is flaky" but from a measurement on
# 2026-08-31: on this exact question qwen3.5:9b answers with a fragment
# ("Tok" instead of "Tokyo") or does not answer at all in roughly a third of
# runs — the gateway then returns "No reply: the model returned empty content
# after retries".
#
# Verified that this is NOT us: the same question sent directly to the gateway,
# bypassing our CLI, produces the same fragments, and the stream deltas match
# the final output byte for byte. Nothing in the harness truncates anything —
# the model is non-deterministic.
#
# A single sample of a non-deterministic answer as an acceptance criterion is a
# random-failure generator, and people stop looking at a suite that goes red at
# random. So we ask up to three times and report how many it took.
ANSWERED=0
for attempt in 1 2 3; do
  A=$(timeout 300 ./venv/bin/python cli.py --plain --no-stream \
        "Answer in one word: what is the capital of Japan?" 2>&1 | tail -3)
  echo "  attempt $attempt: $A"
  # Both languages: a Box switched to Russian will answer in Russian, and that
  # is a correct answer, not a failure.
  if echo "$A" | grep -qi "tokyo\|токио"; then
    ANSWERED=$attempt
    break
  fi
done
if [ "$ANSWERED" = "1" ]; then
  ok "the agent answered the question"
elif [ "$ANSWERED" != "0" ]; then
  warn "the agent answered on attempt $ANSWERED — the model is inconsistent"
else
  no "the agent did not answer in three attempts"
fi

echo
echo "════ 6. SEARCH INSIDE THE BOX ════"
# No docker-compose: SearXNG lives in this same container, because otherwise
# web-research would require docker-in-docker — a hole in the sandbox.
if ! curl -s -o /dev/null -m 2 http://127.0.0.1:8888/ 2>/dev/null; then
  SEARXNG_SETTINGS_PATH=/etc/searxng/settings.yml PYTHONPATH=/opt/searxng \
    nohup ./venv/bin/python -m searx.webapp > /tmp/searxng.log 2>&1 &
fi
c=000
for _ in $(seq 1 45); do
  c=$(curl -s -o /dev/null -m 2 -w '%{http_code}' http://127.0.0.1:8888/ 2>/dev/null) || c=000
  [ "$c" = "200" ] && break; sleep 1
done
if [ "$c" = "200" ]; then
  # Parse the response once and take two numbers from it: how many results, and
  # which engines stayed silent. An empty result set with healthy engines is our
  # breakage; an empty result set with a non-empty unresponsive_engines is
  # somebody else's rate limit. Conflating them is not allowed, see warn() above.
  read -r N DEADSIX <<EOF
$(curl -s -m 40 "http://127.0.0.1:8888/search?q=debian+trixie&format=json" \
  | ./venv/bin/python -c 'import sys, json
try:
    d = json.load(sys.stdin)
except Exception:
    print(-1, "unreadable-response"); raise SystemExit
bad = d.get("unresponsive_engines") or []
names = ",".join(str(e[0]) if isinstance(e, (list, tuple)) and e else str(e) for e in bad)
print(len(d.get("results", [])), names or "-")' 2>/dev/null)
EOF
  N=${N:-0}
  if [ "$N" -gt 0 ]; then
    ok "search works, results: $N"
  elif [ "$N" = "-1" ]; then
    no "SearXNG answered 200 but the body was not JSON"
  elif [ "${DEADSIX:--}" != "-" ]; then
    warn "search empty — upstream not answering: $DEADSIX"
  else
    no "search answers, engines are alive, and there are no results — that is us"
  fi
else
  no "SearXNG did not start (log: /tmp/searxng.log)"
fi

echo
echo "════ 7. TOOLS REACH THE MODEL ════"
# This is the check across the SEAM, and it is the important one. Section 6
# above stayed green for two weeks while the agent had no search at all:
# SearXNG answered, the MCP server started, the config was correct — and the
# tool never reached the model, because the server's name collided with a
# built-in Hermes toolset. Component checks cannot catch that by definition:
# nothing was broken in a component, it was broken between them.
SURFACE=$(cd ~/.hermes && timeout 120 /opt/hermes-venv/bin/python - <<'PY' 2>/dev/null
import logging; logging.basicConfig(level=logging.CRITICAL)
from hermes_cli.plugins import discover_plugins; discover_plugins(force=True)
from tools.registry import discover_builtin_tools; discover_builtin_tools()
from hermes_cli.config import load_config
from hermes_cli.tools_config import _get_platform_tools
from toolsets import resolve_toolset
import tools.registry as R
reg = next(getattr(R, a) for a in dir(R)
           if hasattr(getattr(R, a), "get_definitions") and not isinstance(getattr(R, a), type))
names = set()
for ts in _get_platform_tools(load_config(), "api_server"):
    try: names.update(resolve_toolset(ts))
    except Exception: pass
print(" ".join(sorted(d.get("name") or d.get("function", {}).get("name", "")
                      for d in reg.get_definitions(names, quiet=True))))
PY
)
for t in web_search web_extract terminal read_file; do
  echo "$SURFACE" | grep -qw "$t" && ok "the model can see $t" \
                                  || no "the model can NOT see $t — the tool never reaches the agent"
done

echo
echo "════ 8. SEARCH AND READING ACTUALLY WORK ════"
# Call the tools directly, bypassing the model: a failure here is the harness's
# fault rather than the model declining to call anything. Telling those two
# apart is the entire point of an acceptance suite.
WEB=$(cd ~/.hermes && timeout 180 /opt/hermes-venv/bin/python - <<'PY' 2>/dev/null
import logging; logging.basicConfig(level=logging.CRITICAL)
from hermes_cli.plugins import discover_plugins; discover_plugins(force=True)
from tools.registry import discover_builtin_tools; discover_builtin_tools()
import tools.registry as R
reg = next(getattr(R, a) for a in dir(R)
           if hasattr(getattr(R, a), "dispatch") and not isinstance(getattr(R, a), type))
s = str(reg.dispatch("web_search", {"query": "debian trixie release"}))
print("SEARCH_OK" if "http" in s else "SEARCH_FAIL", s[:200].replace("\n", " "))
e = str(reg.dispatch("web_extract", {"urls": ["https://example.com"]}))
print("EXTRACT_OK" if "Example Domain" in e else "EXTRACT_FAIL", e[:200].replace("\n", " "))
PY
)
if echo "$WEB" | grep -q "^SEARCH_OK"; then
  ok "web_search returned real links"
else
  # An empty result set happens for two entirely different reasons, and
  # confusing them is expensive: "the harness does not deliver search to the
  # agent" is a release blocker (that is how it was broken for two weeks), while
  # "brave and duckduckgo throttled us for asking too often" is somebody else's
  # rate limit that passes on its own.
  #
  # SearXNG can tell them apart: it returns unresponsive_engines listing the
  # engines that did not answer. Ask it directly.
  DEAD=$(curl -s -m 45 "http://127.0.0.1:8888/search?q=debian+trixie+release&format=json" \
         | ./venv/bin/python -c 'import sys, json
try:
    d = json.load(sys.stdin)
except Exception:
    print("SEARXNG_NO_JSON"); raise SystemExit
bad = d.get("unresponsive_engines") or []
print("; ".join(" ".join(str(x) for x in e) if isinstance(e, (list, tuple)) else str(e)
                for e in bad))' 2>/dev/null)
  if [ -n "$DEAD" ] && [ "$DEAD" != "SEARXNG_NO_JSON" ]; then
    warn "web_search empty — upstream not answering, not our breakage: $DEAD"
    warn "  try again in a few minutes; if it repeats on a fresh query and"
    warn "  without the list above, then it is us"
  else
    no "web_search does not work: $(echo "$WEB" | grep SEARCH | head -1)"
  fi
fi
echo "$WEB" | grep -q "^EXTRACT_OK" && ok "web_extract rendered the page" \
                                    || no "web_extract does not work: $(echo "$WEB" | grep EXTRACT | head -1)"

echo
echo "════════════════════════════════"
if [ $FAIL -eq 0 ]; then echo "ACCEPTANCE PASSED"; else echo "THERE ARE FAILURES"; fi
exit $FAIL
