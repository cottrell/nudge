#!/usr/bin/env bash
# Usage: ./attach.sh <session-or-target> <agent>
# Example: ./attach.sh claude_myproject_alice claude
set -e

if [ -z "$1" ] || [ -z "$2" ]; then
    echo "Usage: $0 <session-or-target> <agent>"
    echo "  session-or-target  tmux session or pane target (e.g. claude_myproject_alice or claude_myproject_alice:0.0)"
    echo "  agent    claude, codex, copilot, gemini, vibe"
    exit 1
fi

TARGET=$1
if [[ "$TARGET" != *:*.* ]]; then
    if [[ "$TARGET" != *:* ]]; then
        TARGET="${TARGET}:0.0"
    elif [[ "$TARGET" != *.* ]]; then
        TARGET="${TARGET}.0"
    fi
fi
SESSION=${TARGET%%:*}
AGENT=$2
SOCK="/tmp/${SESSION}.sock"
DIR="$(cd "$(dirname "$0")" && pwd)"

tmux list-panes -t "$TARGET" >/dev/null 2>&1 || {
    echo "Target pane not found: $TARGET"
    exit 1
}

# Set MONITOR_BACKEND=python to use the Python version
if [ "${MONITOR_BACKEND:-c}" = "python" ]; then
    CMD="python $DIR/monitor.py"
else
    [ -x "$DIR/monitor-bin" ] || { echo "monitor-bin not found — run: make build"; exit 1; }
    CMD="$DIR/monitor-bin"
fi

DEBUG_FLAG=""
if [ -n "${MONITOR_DEBUG:-}" ]; then
    DEBUG_PATH="${MONITOR_DEBUG}"
    if [ "$DEBUG_PATH" = "1" ]; then
        DEBUG_PATH="/tmp/${SESSION}.raw"
    fi
    DEBUG_FLAG="--debug $DEBUG_PATH"
    echo "Debug log: $DEBUG_PATH"
fi

STATE_LOG_FLAG=""
if [ -n "${MONITOR_STATE_LOG:-}" ]; then
    STATE_LOG_PATH="${MONITOR_STATE_LOG}"
    if [ "$STATE_LOG_PATH" = "1" ]; then
        STATE_LOG_PATH="/tmp/${SESSION}.state.log"
    fi
    STATE_LOG_FLAG="--state-log $STATE_LOG_PATH"
    echo "State log: $STATE_LOG_PATH"
fi

tmux pipe-pane -t "$TARGET" "$CMD --agent $AGENT --socket $SOCK $DEBUG_FLAG $STATE_LOG_FLAG"
echo "Monitoring $TARGET → $SOCK (backend: ${MONITOR_BACKEND:-c})"
echo "Query: echo status | nc -U $SOCK"
