#!/usr/bin/env bash
# Poll a monitored session and nudge if idle/unknown for too long.
# Usage: ./babysit.sh <session-or-target> [interval_secs] [nudge_message]

if [ -z "$1" ]; then
    echo "Usage: $0 <session-or-target> [interval_secs] [nudge_message]"
    echo "  session-or-target tmux session or pane target (e.g. claude_myproject_alice or claude_myproject_alice:0.0)"
    echo "  interval_secs poll interval, default 60"
    echo "  nudge_message text to send when idle, default 'Please continue.'"
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
INTERVAL=${2:-60}
NUDGE=${3:-"Please continue."}

# Socket matches attach.sh naming: session_window-pane.sock
WINDOW_PANE="${TARGET#*:}"
SOCK="/tmp/${SESSION}_${WINDOW_PANE}.sock"

tmux list-panes -t "$TARGET" >/dev/null 2>&1 || {
    echo "Target pane not found: $TARGET"
    exit 1
}

echo "Babysitting $SESSION via $TARGET (interval=${INTERVAL}s)"

while true; do
    sleep "$INTERVAL"
    STATE=$(echo status | nc -U "$SOCK" 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin)['state'])" 2>/dev/null)
    case "$STATE" in
        idle|unknown)
            echo "$(date '+%H:%M:%S') $SESSION is $STATE — nudging"
            MSG="$NUDGE"
            if [ -n "$TMUX" ]; then
                SENDER=$(tmux display-message -p '#S')
                MSG="${SENDER}: ${MSG}"
            fi
            tmux send-keys -t "$TARGET" -l -- "$MSG"
            sleep 0.1
            tmux send-keys -t "$TARGET" C-m
            ;;
        rate_limited)
            echo "$(date '+%H:%M:%S') $SESSION is rate_limited — waiting"
            ;;
        *)
            echo "$(date '+%H:%M:%S') $SESSION is $STATE"
            ;;
    esac
done
