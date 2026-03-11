#!/bin/bash
# Read lines in one tmux pane and forward them to another pane.
# Usage: ./safe-keyboard.sh [target-pane]
# Default target is the pane above this one: {up-of}

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
