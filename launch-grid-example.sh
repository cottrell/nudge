#!/usr/bin/env bash
# Example: Multi-agent grid launcher with proper monitor attachment.
# Usage: save as launch-grid.sh, chmod +x, then ./launch-grid.sh

SESSION="agents"
WINDOW="grid"
DIR="$(cd "$(dirname "$0")" && pwd)"

# Attach if already exists
if tmux has-session -t "$SESSION" 2>/dev/null; then
    tmux attach -t "$SESSION" || tmux switch-client -t "$SESSION"
    exit 0
fi

CMD='source ~/.bash_aliases && '

# Create session detached:
tmux new-session -d -s "$SESSION" -n "$WINDOW" "${CMD}aicodex"
tmux select-pane -t "$SESSION:$WINDOW".0 -T "codex"

# Top row:
tmux split-window -h -t "$SESSION:$WINDOW" "${CMD}aiclaude"
tmux split-window -h -t "$SESSION:$WINDOW" "${CMD}aicopilot"

# Bottom row: split from pane 0
tmux select-pane -t "$SESSION:$WINDOW".0
tmux split-window -v -t "$SESSION:$WINDOW" "${CMD}aigemini"
tmux split-window -h -t "$SESSION:$WINDOW" "${CMD}aiqwen"
tmux split-window -h -t "$SESSION:$WINDOW" "${CMD}aimistral"

tmux select-layout -t "$SESSION:$WINDOW" tiled
tmux select-pane -t "$SESSION:$WINDOW".0

# Wait for agents to initialize (look for idle prompts)
echo "Waiting for agents to initialize..."
sleep 5

# Attach monitors AFTER agents have started
ATTACH="$DIR/attach.sh"
echo "Attaching monitors..."
$ATTACH "$SESSION:$WINDOW.0" codex &
$ATTACH "$SESSION:$WINDOW.1" claude &
$ATTACH "$SESSION:$WINDOW.2" copilot &
$ATTACH "$SESSION:$WINDOW.3" gemini &
$ATTACH "$SESSION:$WINDOW.4" qwen &
$ATTACH "$SESSION:$WINDOW.5" mistral &
wait

echo "All monitors attached. Query with:"
echo "  echo status | nc -U /tmp/${SESSION}_${WINDOW}.0.sock"
echo ""
echo "Attach to session: tmux attach -t $SESSION"

tmux attach -t "$SESSION" || tmux switch-client -t "$SESSION"
