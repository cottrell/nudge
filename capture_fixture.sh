#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: $0 <agent> [duration_secs]"
  echo "  agent: claude | codex | copilot | gemini | vibe"
  echo "  duration_secs: capture duration (default 60)"
  exit 1
fi

AGENT="$1"
DURATION="${2:-60}"
DIR="$(cd "$(dirname "$0")" && pwd)"
SESSION="capture_${AGENT}_$(date +%Y%m%d_%H%M%S)"
TARGET="${SESSION}:0.0"
SOCK="/tmp/${SESSION}.sock"
RAW_TMP="/tmp/${SESSION}.raw.tmp"
FIXTURE_OUT="$DIR/fixtures/${AGENT}_capture.txt"
STATES_OUT="$DIR/fixtures/${AGENT}_states.jsonl"

case "$AGENT" in
  claude) START_CMD="${CAPTURE_CMD:-claude --dangerously-skip-permissions}" ;;
  codex)  START_CMD="${CAPTURE_CMD:-codex}" ;;
  copilot) START_CMD="${CAPTURE_CMD:-copilot --allow-all}" ;;
  gemini) START_CMD="${CAPTURE_CMD:-gemini}" ;;
  vibe)   START_CMD="${CAPTURE_CMD:-vibe}" ;;
  *)
    echo "Unknown agent: $AGENT"
    exit 1
    ;;
esac

cleanup() {
  set +e
  [ -n "${POLL_PID:-}" ] && kill "$POLL_PID" 2>/dev/null || true
  tmux pipe-pane -t "$SESSION" >/dev/null 2>&1 || true
  if [ "${KEEP_SESSION:-0}" != "1" ]; then
    tmux kill-session -t "$SESSION" >/dev/null 2>&1 || true
  fi
  rm -f "$SOCK"
}
trap cleanup EXIT

rm -f "$RAW_TMP" "$SOCK"

tmux new-session -d -s "$SESSION"
tmux pipe-pane -t "$SESSION" "python $DIR/monitor.py --agent $AGENT --socket $SOCK --debug $RAW_TMP"
: > "$STATES_OUT"
(
  while true; do
    sleep 1
    STATUS=$(echo status | nc -U "$SOCK" 2>/dev/null || true)
    [ -z "$STATUS" ] && continue
    printf '{"ts":"%s","status":%s}\n' "$(date -Iseconds)" "$STATUS" >> "$STATES_OUT"
  done
) &
POLL_PID=$!

tmux send-keys -t "$TARGET" -l -- "$START_CMD"
sleep 0.1
tmux send-keys -t "$TARGET" C-m

# Wait for agent to reach idle (ready prompt), then send a simple prompt
echo "Waiting for agent to start..."
sleep "${STARTUP_WAIT:-8}"

PROMPT="${CAPTURE_PROMPT:-say hello}"
echo "Sending prompt: $PROMPT"
tmux send-keys -t "$TARGET" -l -- "$PROMPT"
sleep 0.1
tmux send-keys -t "$TARGET" C-m

# Wait for response + return to idle
sleep "$DURATION"

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

echo "Captured fixture: $FIXTURE_OUT"
echo "State timeline:   $STATES_OUT"
echo "Session:          $SESSION"
if [ "${KEEP_SESSION:-0}" = "1" ]; then
  echo "KEEP_SESSION=1 set; tmux session left running."
fi
