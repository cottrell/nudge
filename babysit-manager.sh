#!/usr/bin/env bash
# Config-driven babysit orchestration.
# Usage: ./babysit-manager.sh [config] {start|restart|stop|status}
#
# Config format (INI-style):
#   [session]
#   name = agents_myproject
#
#   [agents]
#   0.0 = claude
#   0.1 = gemini
#
#   [babysit]
#   0.0 = true|prompts/claude.md|600
#   0.1 = false||0  (disabled)

set -e
CONFIG="${1:-agents.conf}"

if [ ! -f "$CONFIG" ]; then
    echo "Config not found: $CONFIG"
    echo "Usage: $0 [config_file] {start|restart|stop|status}"
    exit 1
fi

# Parse INI-style config
get_section() {
    awk -v section="$1" '
        /^\[/ { current = substr($0, 2, length($0)-2) }
        current == section && /=/ { print }
    ' "$CONFIG"
}

get_value() {
    get_section "$1" | grep "^$2 = " | cut -d'=' -f2 | tr -d ' '
}

SESSION=$(get_value "session" "name")

if [ -z "$SESSION" ]; then
    echo "Error: [session] section missing 'name' in $CONFIG"
    exit 1
fi

cmd="${2:-start}"

case "$cmd" in
    start)
        echo "Starting babysit loops for session: $SESSION"
        get_section "babysit" | while IFS='=' read -r pane config; do
            [ -z "$pane" ] && continue
            pane=$(echo "$pane" | tr -d ' ')
            enabled=$(echo "$config" | cut -d'|' -f1)
            prompt_file=$(echo "$config" | cut -d'|' -f2)
            interval=$(echo "$config" | cut -d'|' -f3)
            
            [ "$enabled" != "true" ] && continue
            
            if [ ! -f "$prompt_file" ]; then
                echo "  Warning: prompt not found: $prompt_file (pane $pane)"
                continue
            fi
            
            prompt=$(cat "$prompt_file")
            ./babysit.sh "${SESSION}:${pane}" "$interval" "$prompt" &
            echo "  Started: ${SESSION}:${pane} (interval=${interval}s, prompt=$prompt_file)"
        done
        echo "Done."
        ;;
    
    restart)
        echo "Restarting babysit loops for session: $SESSION"
        pkill -f "babysit.sh ${SESSION}:" 2>/dev/null || true
        sleep 0.5
        $0 "$CONFIG" start
        ;;
    
    stop)
        echo "Stopping babysit loops for session: $SESSION"
        pkill -f "babysit.sh ${SESSION}:" 2>/dev/null || true
        echo "Done."
        ;;
    
    status)
        echo "Babysit loops for session: $SESSION"
        pgrep -af "babysit.sh ${SESSION}:" || echo "  None running"
        ;;
    
    *)
        echo "Usage: $0 [config_file] {start|restart|stop|status}"
        exit 1
        ;;
esac
