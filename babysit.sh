#!/usr/bin/env bash
# Poll a monitored session and nudge if idle/unknown for too long.
# Usage: ./babysit.sh <session> [interval_secs] [nudge_message]

if [ -z "$1" ]; then
    echo "Usage: $0 <session> [interval_secs] [nudge_message]"
    echo "  session       tmux session name (e.g. claude_myproject_alice)"
    echo "  interval_secs poll interval, default 60"
    echo "  nudge_message text to send when idle, default 'Please continue.'"
    exit 1
fi

SESSION=$1
INTERVAL=${2:-60}
NUDGE=${3:-"Please continue."}
SOCK="/tmp/${SESSION}.sock"

echo "Babysitting $SESSION (interval=${INTERVAL}s)"

while true; do
    sleep "$INTERVAL"
    STATE=$(echo status | nc -U "$SOCK" 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin)['state'])" 2>/dev/null)
    case "$STATE" in
        idle|unknown)
            echo "$(date '+%H:%M:%S') $SESSION is $STATE — nudging"
            tmux send-keys -t "$SESSION" "$NUDGE"
            sleep 0.1
            tmux send-keys -t "$SESSION" C-m
            ;;
        rate_limited)
            echo "$(date '+%H:%M:%S') $SESSION is rate_limited — waiting"
            ;;
        *)
            echo "$(date '+%H:%M:%S') $SESSION is $STATE"
            ;;
    esac
done
