#!/usr/bin/env bash
# Launch or resume a monitored single-pane agent session.
# Usage: ./examples/launch-single-pane.sh <session> <agent>
set -e

if [ -z "$1" ] || [ -z "$2" ]; then
    echo "Usage: $0 <session> <agent>"
    echo "  session  tmux session name (e.g. claude_myproject_alice)"
    echo "  agent    claude, codex, copilot, gemini, vibe, qwen"
    echo ""
    echo "Socket: /tmp/<session>_0-0.sock (or /tmp/<session>_<window>-<pane>.sock for explicit targets)"
    exit 1
fi

SESSION=$1
AGENT=$2
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

if [[ "$SESSION" != *:*.* ]]; then
    if [[ "$SESSION" != *:* ]]; then
        WINDOW_PANE="0.0"
    elif [[ "$SESSION" != *.* ]]; then
        WINDOW_PANE="0.0"
    fi
else
    WINDOW_PANE="${SESSION#*:}"
fi
SESSION_NAME="${SESSION%%:*}"
SOCK="/tmp/${SESSION_NAME}_${WINDOW_PANE}.sock"

if tmux new-session -d -s "$SESSION" 2>/dev/null; then
    echo "Created session $SESSION"
    rm -f "$SOCK"
else
    echo "Session $SESSION already exists"
fi

if echo status | nc -U "$SOCK" 2>/dev/null | grep -q state; then
    echo "Monitor already running on $SOCK"
else
    echo "Attaching monitor..."
    "$ROOT_DIR/attach.sh" "$SESSION" "$AGENT"
fi

tmux attach -t "$SESSION"
