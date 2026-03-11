#!/usr/bin/env bash
# Usage: ./attach.sh <session> <agent>
# Example: ./attach.sh claude_myproject_alice claude
set -e

if [ -z "$1" ] || [ -z "$2" ]; then
    echo "Usage: $0 <session> <agent>"
    echo "  session  tmux session name (e.g. claude_myproject_alice)"
    echo "  agent    claude, codex, copilot, gemini, vibe"
    exit 1
fi

SESSION=$1
AGENT=$2
SOCK="/tmp/${SESSION}.sock"
DIR="$(cd "$(dirname "$0")" && pwd)"

# Set MONITOR_BACKEND=python to use the Python version
if [ "${MONITOR_BACKEND:-c}" = "python" ]; then
    CMD="python $DIR/monitor.py"
else
    [ -x "$DIR/monitor-bin" ] || { echo "monitor-bin not found — run: make build"; exit 1; }
    CMD="$DIR/monitor-bin"
fi

DEBUG_FLAG=""
if [ "${MONITOR_BACKEND:-c}" = "python" ] && [ -n "$MONITOR_DEBUG" ]; then
    DEBUG_FLAG="--debug /tmp/${SESSION}.raw"
    echo "Debug log: /tmp/${SESSION}.raw"
fi

tmux pipe-pane -t "$SESSION" "$CMD --agent $AGENT --socket $SOCK $DEBUG_FLAG"
echo "Monitoring $SESSION → $SOCK (backend: ${MONITOR_BACKEND:-c})"
echo "Query: echo status | nc -U $SOCK"
