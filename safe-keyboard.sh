#!/bin/bash
# safe-keyboard.sh
# A simple "safe input" loop for tmux.
# Usage: ./safe-keyboard.sh [target-pane]
#
# If target-pane is not specified, it defaults to the pane logically "above" this one.
#
# Workflow:
# 1. Open tmux.
# 2. Run your agent (e.g., `codex`) in the top pane.
# 3. Split the window (Ctrl+b ").
# 4. Run `./safe-keyboard.sh` in the bottom pane.
# 5. Type in the bottom pane safely. Output appears in the top.
#
# Note: To send keys directly to the agent from another terminal (skipping this script),
# use: tmux send-keys -t <session>:0.0 "command" Enter

TARGET="${1:-{up-of}}"

# Verify we are in tmux
if [ -z "$TMUX" ]; then
    echo "Error: This script must be run inside tmux."
    exit 1
fi

echo -e "\033[1;34mSafe Keyboard Active\033[0m"
echo "Targeting pane: $TARGET"
echo "Type safely below. Press Enter to send."

# Loop to read input and send it
while IFS= read -r -e -p "> " line; do
    # Send the literal characters of the line
    tmux send-keys -t "$TARGET" -l -- "$line"
    # Send the Enter key
    tmux send-keys -t "$TARGET" Enter
done
