#!/usr/bin/env bash
set -euo pipefail

SESSION="${1:-agent_grid}"
WINDOW="${2:-grid}"

CMD='source ~/.bash_aliases && '
ATTACH="$HOME/dev/nudge/attach.sh"

tmux kill-session -t "$SESSION" 2>/dev/null || true
tmux new-session -d -s "$SESSION" -n "$WINDOW" "bash"

tmux split-window -h -t "$SESSION:$WINDOW" "bash"
tmux split-window -h -t "$SESSION:$WINDOW" "bash"
tmux select-pane -t "$SESSION:$WINDOW".0
tmux split-window -v -t "$SESSION:$WINDOW" "bash"
tmux split-window -h -t "$SESSION:$WINDOW" "bash"
tmux split-window -h -t "$SESSION:$WINDOW" "bash"
tmux select-layout -t "$SESSION:$WINDOW" tiled

echo "Attaching monitors..."
$ATTACH "$SESSION:$WINDOW.0" codex &
$ATTACH "$SESSION:$WINDOW.1" claude &
$ATTACH "$SESSION:$WINDOW.2" copilot &
$ATTACH "$SESSION:$WINDOW.3" gemini &
$ATTACH "$SESSION:$WINDOW.4" qwen &
$ATTACH "$SESSION:$WINDOW.5" vibe &
wait
sleep 1

echo "Starting agents..."
tmux send-keys -t "$SESSION:$WINDOW.0" "${CMD}aicodex" C-m
tmux send-keys -t "$SESSION:$WINDOW.1" "${CMD}aiclaude" C-m
tmux send-keys -t "$SESSION:$WINDOW.2" "${CMD}aicopilot" C-m
tmux send-keys -t "$SESSION:$WINDOW.3" "${CMD}aigemini" C-m
tmux send-keys -t "$SESSION:$WINDOW.4" "${CMD}aiqwen" C-m
tmux send-keys -t "$SESSION:$WINDOW.5" "${CMD}aimistral" C-m

echo "Done. Query with: echo status | nc -U /tmp/${SESSION}_${WINDOW}.0.sock"
tmux attach -t "$SESSION"
