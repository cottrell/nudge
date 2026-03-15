#!/bin/bash
# Read lines in one tmux pane and forward them to another pane.
# Usage: ./keyboard-2pane.sh [target-pane]
# examples/launch-2pane.sh passes an explicit target like session:0.0.

# Verify we are in tmux
if [ -z "$TMUX" ]; then
    echo "Error: This script must be run inside tmux."
    exit 1
fi

if [ -n "$1" ]; then
    TARGET="$1"
else
    TARGET="$(tmux display-message -p '#S:#{window_index}.0')"
fi

# Some tmux/shell startup paths have leaked a trailing } into the argument.
case "$TARGET" in
    *:*.0\}|*:*.1\}|*:*.2\}|*:*.3\}|*:*.4\}|*:*.5\}|*:*.6\}|*:*.7\}|*:*.8\}|*:*.9\})
        TARGET="${TARGET%\}}"
        ;;
esac

tmux list-panes -t "$TARGET" >/dev/null 2>&1 || {
    echo "Error: Target pane not found: $TARGET"
    exit 1
}

echo -e "\033[1;34m2-Pane Keyboard Active\033[0m"
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
