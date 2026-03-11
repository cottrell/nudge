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
    sleep 0.1
    # Send Enter as a separate C-m keypress; this has been more reliable than Enter.
    tmux send-keys -t "$TARGET" C-m
done
