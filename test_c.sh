#!/usr/bin/env bash
set -e
SOCK=/tmp/test-monitor-c.sock
rm -f "$SOCK"

# feed a working line then keep stdin open
{ echo "⠙ Thinking…"; sleep 5; } | ./monitor-bin --agent claude --socket "$SOCK" &
PID=$!
sleep 0.3

echo -n "status: "
printf "status" | nc -U "$SOCK"

echo -n "tail:   "
printf "tail" | nc -U "$SOCK"

kill $PID 2>/dev/null
rm -f "$SOCK"
echo "done"
