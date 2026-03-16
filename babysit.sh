#!/usr/bin/env bash
# Poll a monitored session and nudge if idle for too long.
# Usage: ./babysit.sh <session-or-target> [interval_secs] [long_nudge] [short_nudge]

if [ -z "$1" ]; then
    echo "Usage: $0 <session-or-target> [interval_secs] [long_nudge] [short_nudge]"
    echo "  session-or-target tmux session or pane target (e.g. claude_myproject_alice or claude_myproject_alice:0.0)"
    echo "  interval_secs poll interval, default 60"
    echo "  long_nudge sent once when babysit starts, default 'Please continue.'"
    echo "  short_nudge sent on later idle nudges, defaults to long_nudge"
    echo "  env BABYSIT_MAX_NONIDLE_SECS defaults to 1800; after that much continuous"
    echo "      unknown/working/error time, babysit sends a nudge anyway. Set to 0 to disable."
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
LONG_NUDGE=${3:-"Please continue."}
SHORT_NUDGE=${4:-"$LONG_NUDGE"}
MAX_NONIDLE_SECS=${BABYSIT_MAX_NONIDLE_SECS:-1800}

# Socket matches attach.sh naming: session_window-pane.sock
WINDOW_PANE="${TARGET#*:}"
SOCK="/tmp/${SESSION}_${WINDOW_PANE}.sock"

tmux list-panes -t "$TARGET" >/dev/null 2>&1 || {
    echo "Target pane not found: $TARGET"
    exit 1
}

echo "Babysitting $SESSION via $TARGET (interval=${INTERVAL}s)"
if [ "$MAX_NONIDLE_SECS" -gt 0 ] 2>/dev/null; then
    echo "Max non-idle override after ${MAX_NONIDLE_SECS}s"
fi

send_message() {
    MSG="$1"
    if [ -n "$TMUX" ]; then
        SENDER=$(tmux display-message -p '#S:#{window_index}.#{pane_index}')
        MSG="${SENDER}: ${MSG}"
    fi
    tmux send-keys -t "$TARGET" -l -- "$MSG"
    sleep 0.1
    tmux send-keys -t "$TARGET" C-m
}

if [ -n "$LONG_NUDGE" ]; then
    echo "$(date '+%H:%M:%S') $SESSION startup babysit prompt"
    send_message "$LONG_NUDGE"
fi

NONIDLE_SINCE=0

while true; do
    sleep "$INTERVAL"
    STATE=$(echo status | nc -U "$SOCK" 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin)['state'])" 2>/dev/null)
    NOW=$(date +%s)
    case "$STATE" in
        idle|rate_limited)
            NONIDLE_SINCE=0
            ;;
        unknown|working|error)
            if [ "$NONIDLE_SINCE" -eq 0 ] 2>/dev/null; then
                NONIDLE_SINCE=$NOW
            fi
            ;;
        *)
            NONIDLE_SINCE=0
            ;;
    esac
    case "$STATE" in
        idle)
            echo "$(date '+%H:%M:%S') $SESSION is idle — nudging"
            send_message "$SHORT_NUDGE"
            ;;
        unknown)
            if [ "$MAX_NONIDLE_SECS" -gt 0 ] 2>/dev/null && [ "$NONIDLE_SINCE" -gt 0 ] 2>/dev/null && [ $((NOW - NONIDLE_SINCE)) -ge "$MAX_NONIDLE_SECS" ]; then
                echo "$(date '+%H:%M:%S') $SESSION is unknown for $((NOW - NONIDLE_SINCE))s — nudging anyway"
                send_message "$SHORT_NUDGE"
                NONIDLE_SINCE=$NOW
            else
                echo "$(date '+%H:%M:%S') $SESSION is unknown — waiting"
            fi
            ;;
        rate_limited)
            echo "$(date '+%H:%M:%S') $SESSION is rate_limited — waiting"
            ;;
        working|error)
            if [ "$MAX_NONIDLE_SECS" -gt 0 ] 2>/dev/null && [ "$NONIDLE_SINCE" -gt 0 ] 2>/dev/null && [ $((NOW - NONIDLE_SINCE)) -ge "$MAX_NONIDLE_SECS" ]; then
                echo "$(date '+%H:%M:%S') $SESSION is $STATE for $((NOW - NONIDLE_SINCE))s — nudging anyway"
                send_message "$SHORT_NUDGE"
                NONIDLE_SINCE=$NOW
            else
                echo "$(date '+%H:%M:%S') $SESSION is $STATE"
            fi
            ;;
        *)
            echo "$(date '+%H:%M:%S') $SESSION is $STATE"
            ;;
    esac
done
