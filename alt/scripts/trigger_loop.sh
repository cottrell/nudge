#!/bin/bash
# Trigger Loop: Monitors backlog for changes and initiates "Things"

BACKLOG_DIR="./backlog/tasks"

if [ ! -d "$BACKLOG_DIR" ]; then
    echo "Error: Backlog directory $BACKLOG_DIR not found."
    exit 1
fi

echo "Starting Trigger Loop on $BACKLOG_DIR..."

# Ensure inotifywait is available
if ! command -v inotifywait &> /dev/null; then
    echo "inotifywait not found. Falling back to polling mode..."
    while true; do
        # Simplified polling logic: find tasks modified in the last 60 seconds
        find "$BACKLOG_DIR" -maxdepth 1 -name "*.md" -mmin -1
        sleep 60
    done
else
    inotifywait -m -e modify,create,moved_to "$BACKLOG_DIR" | while read -r directory events filename; do
        if [[ "$filename" == *.md ]]; then
            echo "[$(date +%T)] Event: $events on $filename"
            # Launch logic:
            # 1. Parse status from $BACKLOG_DIR/$filename
            # 2. If 'To Do', launch a new Task Session (Thing)
            # 3. If 'Done', signal cleanup
        fi
    done
fi
