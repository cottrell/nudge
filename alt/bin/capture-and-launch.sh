#!/bin/bash
# alt/bin/capture-and-launch.sh
# Launch a TUI agent for a Thing node, capture native session ID, record it.
# Usage: ./capture-and-launch.sh <agent> <thing_id> <node_id> <command...>
# Example: ./capture-and-launch.sh claude thing-foo impl-1 claude --model sonnet "...prompt..."

set -euo pipefail

AGENT=$1; shift
THING_ID=$1; shift
NODE_ID=$1; shift
CMD=("$@")

STATE_DIR="./alt/state/things/$THING_ID"
mkdir -p "$STATE_DIR"

TEMP_SESSION="alt-thing-${THING_ID}-${NODE_ID}-$$"
TARGET="$TEMP_SESSION:0.0"

cleanup() {
  tmux kill-session -t "$TEMP_SESSION" 2>/dev/null || true
}
# For real launches we may not trap kill; use for probe only. Comment for persistent.
# trap cleanup EXIT

echo "[alt] Launching $AGENT for $THING_ID/$NODE_ID in $TEMP_SESSION"

tmux new-session -d -s "$TEMP_SESSION" "${CMD[*]}"

# Wait briefly for boot and session creation
sleep 2

# Get pane pid, find agent process
PANE_PID=$(tmux display-message -t "$TARGET" -p '#{pane_pid}' 2>/dev/null || echo "")
if [ -z "$PANE_PID" ]; then
  echo "Failed to get pane pid" >&2
  exit 1
fi

# Find child agent pid (common case: direct or under shell)
AGENT_PID=$(pgrep -P "$PANE_PID" -f "$AGENT" | head -1 || echo "$PANE_PID")

SESSION_ID=""

case "$AGENT" in
  claude|Claude)
    JSON="~/.claude/sessions/${AGENT_PID}.json"
    if [ -f $JSON ]; then
      SESSION_ID=$(python3 -c "
import json, os, sys
p = os.path.expanduser('$JSON')
with open(p) as f: d = json.load(f)
print(d.get('sessionId', ''))
" 2>/dev/null || echo "")
    fi
    ;;
  codex|Codex)
    # Look for recent rollout jsonl, extract id from filename or content
    RECENT=$(find ~/.codex/sessions -name '*.jsonl' -newermt '2 minutes ago' 2>/dev/null | head -1)
    if [ -n "$RECENT" ]; then
      SESSION_ID=$(basename "$RECENT" | sed -E 's/.*-([0-9a-f-]+)\.jsonl/\1/')
    fi
    ;;
  *)
    # Fallback: look for UUID in recent capture or files
    CAP=$(tmux capture-pane -t "$TARGET" -p 2>/dev/null | grep -oE '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' | head -1 || echo "")
    SESSION_ID="$CAP"
    ;;
esac

if [ -z "$SESSION_ID" ]; then
  # Synthetic fallback
  SESSION_ID="${AGENT}:$$-$(date +%s)"
  echo "[alt] No native session ID captured, using synthetic: $SESSION_ID"
else
  echo "[alt] Captured native session ID: $SESSION_ID (pid $AGENT_PID)"
fi

# Record to thing state (simple for now; later graph.json or sqlite)
echo "{\"node_id\": \"$NODE_ID\", \"agent\": \"$AGENT\", \"session_id\": \"$SESSION_ID\", \"pid\": $AGENT_PID, \"launched_at\": \"$(date -Iseconds)\", \"cmd\": \"${CMD[*]}\"}" > "$STATE_DIR/${NODE_ID}.json"

# For persistent worker: do not kill. Leave the tmux session or switch to direct launch.
# For probe/test: uncomment trap or kill here.
# tmux kill-session -t "$TEMP_SESSION" || true

echo "[alt] Node $NODE_ID recorded. Session: $SESSION_ID"
echo "$SESSION_ID"  # stdout for caller
