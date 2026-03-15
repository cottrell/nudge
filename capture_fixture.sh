#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: $0 <agent> [duration_secs]"
  echo "  agent: claude | codex | copilot | gemini | vibe | qwen"
  echo "  duration_secs: capture duration (default 60)"
  exit 1
fi

AGENT="$1"
DURATION="${2:-60}"
DIR="$(cd "$(dirname "$0")" && pwd)"
SESSION="capture_${AGENT}_$(date +%Y%m%d_%H%M%S)"
TARGET="${SESSION}:0.0"

# Socket matches attach.sh naming: session_window-pane.sock
SOCK="/tmp/${SESSION}_0.0.sock"
RAW_TMP="/tmp/${SESSION}.raw.tmp"
TRANSITIONS_TMP="/tmp/${SESSION}.transitions.tmp"
FIXTURE_OUT="$DIR/fixtures/${AGENT}_capture.txt"
TRANSITIONS_OUT="$DIR/fixtures/${AGENT}_transitions.jsonl"

case "$AGENT" in
  claude) START_CMD="${CAPTURE_CMD:-claude --dangerously-skip-permissions}" ;;
  codex)  START_CMD="${CAPTURE_CMD:-codex}" ;;
  copilot) START_CMD="${CAPTURE_CMD:-copilot --allow-all}" ;;
  gemini) START_CMD="${CAPTURE_CMD:-gemini}" ;;
  vibe)   START_CMD="${CAPTURE_CMD:-vibe}" ;;
  qwen)   START_CMD="${CAPTURE_CMD:-qwen}" ;;
  *)
    echo "Unknown agent: $AGENT"
    exit 1
    ;;
esac

cleanup() {
  set +e
  tmux pipe-pane -t "$SESSION" >/dev/null 2>&1 || true
  if [ "${KEEP_SESSION:-0}" != "1" ]; then
    tmux kill-session -t "$SESSION" >/dev/null 2>&1 || true
  fi
  rm -f "$SOCK"
}
trap cleanup EXIT

rm -f "$RAW_TMP" "$TRANSITIONS_TMP" "$SOCK"
[ -x "$DIR/monitor-bin" ] || make -C "$DIR" build

tmux new-session -d -s "$SESSION"
tmux pipe-pane -t "$TARGET" "$DIR/monitor-bin --agent $AGENT --socket $SOCK --debug $RAW_TMP --state-log $TRANSITIONS_TMP"

tmux send-keys -t "$TARGET" -l -- "$START_CMD"
sleep 0.1
tmux send-keys -t "$TARGET" C-m

sock_status() {
  printf 'status' | nc -U "$SOCK" 2>/dev/null | python -c 'import json,sys; print(json.load(sys.stdin).get("state",""))' 2>/dev/null || true
}

latest_transition_state() {
  python - "$TRANSITIONS_TMP" <<'PY'
import json, sys
path = sys.argv[1]
last = ""
try:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            obj = json.loads(raw)
            if isinstance(obj, dict) and isinstance(obj.get("state"), str):
                last = obj["state"]
except FileNotFoundError:
    pass
print(last)
PY
}

transition_count() {
  python - "$TRANSITIONS_TMP" <<'PY'
import sys
path = sys.argv[1]
try:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        print(sum(1 for raw in f if raw.strip()))
except FileNotFoundError:
    print(0)
PY
}

transition_summary_since() {
  python - "$TRANSITIONS_TMP" "$1" <<'PY'
import json, sys
path, start = sys.argv[1], int(sys.argv[2])
seen_working = False
last = ""
try:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for idx, raw in enumerate((line for line in f if line.strip()), start=1):
            if idx <= start:
                continue
            obj = json.loads(raw)
            state = obj.get("state", "")
            if state == "working":
                seen_working = True
            last = state
except FileNotFoundError:
    pass
print(f"{int(seen_working)} {last}")
PY
}

wait_for_state() {
  local want="$1" timeout="$2" stable="${3:-2}" now state seen count last_count
  now=$(date +%s)
  local deadline=$((now + timeout))
  seen=0
  last_count=-1
  while [ "$(date +%s)" -lt "$deadline" ]; do
    state="$(latest_transition_state)"
    [ -n "$state" ] || state="$(sock_status)"
    count="$(transition_count)"
    if [ "$state" = "$want" ]; then
      if [ "$count" = "$last_count" ]; then
        seen=$((seen + 1))
      else
        seen=1
      fi
      if [ "$seen" -ge "$stable" ]; then
        return 0
      fi
    else
      seen=0
    fi
    last_count="$count"
    sleep 1
  done
  return 1
}

wait_for_output_and_idle() {
  local before_lines="$1" before_events="$2" timeout="$3" lines summary seen_working state
  local deadline=$(( $(date +%s) + timeout ))
  while [ "$(date +%s)" -lt "$deadline" ]; do
    lines=$(wc -l < "$RAW_TMP" 2>/dev/null || echo 0)
    summary="$(transition_summary_since "$before_events")"
    seen_working="${summary%% *}"
    state="${summary#* }"
    if [ "$lines" -gt "$before_lines" ] && [ "$seen_working" = "1" ] && [ "$state" = "idle" ]; then
      return 0
    fi
    sleep 1
  done
  return 1
}

# Wait for agent to reach idle (ready prompt), then send a simple prompt
echo "Waiting for agent to start..."
wait_for_state idle "${STARTUP_WAIT:-60}" || {
  echo "Agent did not reach idle startup state" >&2
  exit 1
}

PROMPT="${CAPTURE_PROMPT:-say hello}"
echo "Sending prompt: $PROMPT"
before_lines=$(wc -l < "$RAW_TMP" 2>/dev/null || echo 0)
before_events=$(transition_count)
tmux send-keys -t "$TARGET" -l -- "$PROMPT"
sleep 0.1
tmux send-keys -t "$TARGET" C-m

# Wait for response output + return to idle
wait_for_output_and_idle "$before_lines" "$before_events" "$DURATION" || {
  echo "Capture did not settle back to idle within ${DURATION}s" >&2
  exit 1
}

python - "$RAW_TMP" "$FIXTURE_OUT" <<'PY'
import re
import sys

src, dst = sys.argv[1], sys.argv[2]

with open(src, "r", encoding="utf-8", errors="replace") as f:
    text = f.read()

rules = [
    (r"/home/[A-Za-z0-9._-]+", "/home/USER"),
    (r"(\\x1b\[[0-9;]*m)?[A-Za-z0-9._-]+@[A-Za-z0-9._-]+", r"\1USER@HOST"),
    (r"sk-[A-Za-z0-9]{20,}", "sk-REDACTED"),
    (r"Bearer\s+[A-Za-z0-9._\-]+", "Bearer REDACTED"),
    (r"(?i)(api[_-]?key|token|authorization)\s*[:=]\s*[^'\"\\s]+", r"\\1=REDACTED"),
]

for pat, repl in rules:
    text = re.sub(pat, repl, text)

with open(dst, "w", encoding="utf-8") as f:
    f.write(text)
PY

python - "$TRANSITIONS_TMP" "$TRANSITIONS_OUT" <<'PY'
import re
import sys

src, dst = sys.argv[1], sys.argv[2]

with open(src, "r", encoding="utf-8", errors="replace") as f:
    text = f.read()

rules = [
    (r"/home/[A-Za-z0-9._-]+", "/home/USER"),
    (r"(\\x1b\[[0-9;]*m)?[A-Za-z0-9._-]+@[A-Za-z0-9._-]+", r"\1USER@HOST"),
    (r"sk-[A-Za-z0-9]{20,}", "sk-REDACTED"),
    (r"Bearer\s+[A-Za-z0-9._\-]+", "Bearer REDACTED"),
    (r"(?i)(api[_-]?key|token|authorization)\s*[:=]\s*[^'\"\\s]+", r"\\1=REDACTED"),
]

for pat, repl in rules:
    text = re.sub(pat, repl, text)

with open(dst, "w", encoding="utf-8") as f:
    f.write(text)
PY

echo "Captured fixture: $FIXTURE_OUT"
echo "State changes:    $TRANSITIONS_OUT"
echo "Session:          $SESSION"
if [ "${KEEP_SESSION:-0}" = "1" ]; then
  echo "KEEP_SESSION=1 set; tmux session left running."
fi
