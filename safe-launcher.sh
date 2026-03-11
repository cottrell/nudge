#!/bin/bash
# safe-launcher.sh
# Automates the setup of a "safe" tmux environment.
#
# Usage: ./scripts/safe-launcher.sh <session_name> [command]
# Example: ./scripts/safe-launcher.sh my-chat codex
#
# Layout:
# -------------------------
# |                       |
# |      Top Pane (0)     |  <-- Runs your agent/command. Target externally via: tmux send-keys -t $SESSION_NAME:0.0
# |                       |
# -------------------------
# |    Bottom Pane (1)    |  <-- Runs safe-keyboard.sh (input). Target externally via: tmux send-keys -t $SESSION_NAME:0.1
# -------------------------

SESSION_NAME="$1"
COMMAND="${2:-bash}" # Default to bash if no command provided

if [ -z "$SESSION_NAME" ]; then
    echo "Usage: $0 <session_name> [command]"
    exit 1
fi

# check if session exists
if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    echo "Session '$SESSION_NAME' already exists. Attaching..."
    tmux attach-session -t "$SESSION_NAME"
    exit 0
fi

# 1. Create the session (detached)
# We start with the user's desired command in the initial window
tmux new-session -d -s "$SESSION_NAME" "$COMMAND"

# 2. Split the window vertically, creating a small bottom pane (5 lines high)
tmux split-window -t "$SESSION_NAME:0" -v -l 5

# 3. In the bottom pane (index 1), run the safe-keyboard script
# We target the pane above us using the default behavior of safe-keyboard.sh ({up-of})
# We use the absolute path to ensure it runs from anywhere
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
tmux send-keys -t "$SESSION_NAME:0.1" "$SCRIPT_DIR/safe-keyboard.sh" C-m

# 4. Select the bottom pane so typing starts there immediately
tmux select-pane -t "$SESSION_NAME:0.1"

# 5. Attach to the session
tmux attach-session -t "$SESSION_NAME"
