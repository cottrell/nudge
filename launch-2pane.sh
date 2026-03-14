#!/bin/bash
# Create a monitored split-pane tmux session with a dedicated input pane.
#
# Usage: ./launch-2pane.sh <session_name> <agent> [command]
# Example: ./launch-2pane.sh my-chat codex
#
# Layout:
# -------------------------
# |                       |
# |      Top Pane (0)     |  <-- Runs your agent/command. Monitored on $SESSION_NAME:0.0
# |                       |
# -------------------------
# |    Bottom Pane (1)    |  <-- Runs keyboard-2pane.sh (input). Target externally via: tmux send-keys -t $SESSION_NAME:0.1
# -------------------------

SESSION_NAME="$1"
AGENT="$2"
COMMAND="${3:-bash}" # Default to bash if no command provided
DIR="$(cd "$(dirname "$0")" && pwd)"

# Socket matches attach.sh naming: session_window-pane.sock
# Top pane (0.0) gets the monitor
SOCK="/tmp/${SESSION_NAME}_0.0.sock"

if [ -z "$SESSION_NAME" ] || [ -z "$AGENT" ]; then
    echo "Usage: $0 <session_name> <agent> [command]"
    exit 1
fi

if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    echo "Session '$SESSION_NAME' already exists. Attaching..."
else
    rm -f "$SOCK"
    tmux new-session -d -s "$SESSION_NAME" "$COMMAND"
fi

if [ "$(tmux list-panes -t "$SESSION_NAME" | wc -l)" -lt 2 ]; then
    tmux split-window -t "$SESSION_NAME:0" -v -l 5
fi

tmux send-keys -t "$SESSION_NAME:0.1" C-c 2>/dev/null || true
tmux send-keys -t "$SESSION_NAME:0.1" -l -- "$DIR/keyboard-2pane.sh $SESSION_NAME:0.0"
sleep 0.1
tmux send-keys -t "$SESSION_NAME:0.1" C-m

# Check if monitor is already running by querying the socket with retries
# pane_pipe=1 alone isn't sufficient - the monitor process must be ready
monitor_running() {
    [ "$(tmux display-message -p -t "$SESSION_NAME:0.0" '#{pane_pipe}')" = "1" ] || return 1
    # Retry socket query up to 5 times with 100ms delays
    for i in 1 2 3 4 5; do
        if echo status | nc -U "$SOCK" 2>/dev/null | grep -q state; then
            return 0
        fi
        sleep 0.1
    done
    return 1
}

if monitor_running; then
    echo "Monitor already running on $SESSION_NAME:0.0 via $SOCK"
else
    echo "Attaching monitor to $SESSION_NAME:0.0..."
    "$DIR/attach.sh" "$SESSION_NAME:0.0" "$AGENT"
fi

tmux select-pane -t "$SESSION_NAME:0.1"
tmux attach-session -t "$SESSION_NAME"
