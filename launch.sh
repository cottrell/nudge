#!/usr/bin/env bash
# Launch or resume a monitored agent session.
# Usage: ./launch.sh <session> <agent>
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

# Create session if it doesn't exist
if tmux new-session -d -s "$SESSION" 2>/dev/null; then
    echo "Created session $SESSION"
    rm -f "$SOCK"  # clean up stale socket from previous run
else
    echo "Session $SESSION already exists"
fi

# Check if monitor is already attached by querying the socket
if echo status | nc -U "$SOCK" 2>/dev/null | grep -q state; then
    echo "Monitor already running on $SOCK"
else
    echo "Attaching monitor..."
    "$DIR/attach.sh" "$SESSION" "$AGENT"
fi

tmux attach -t "$SESSION"
