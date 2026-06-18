#!/usr/bin/env bash
# swarm/usage/codex.sh - Scrapes Codex account usage via a temporary tmux session
set -euo pipefail

TEMP_SESSION="codex-usage-$$"
TEMP_TARGET="$TEMP_SESSION:0.0"

cleanup() {
  tmux kill-session -t "$TEMP_SESSION" 2>/dev/null || true
}
trap cleanup EXIT

# 1. Start Codex in a detached session
tmux new-session -d -s "$TEMP_SESSION" "codex"

# 2. Wait for REPL to be ready (look for prompt › or OpenAI Codex box)
BOOT_TIMEOUT=15
BOOTED=false
for ((i=0; i<BOOT_TIMEOUT*5; i++)); do
  output=$(tmux capture-pane -t "$TEMP_TARGET" -p 2>/dev/null || true)
  if echo "$output" | grep -q -E '›|OpenAI Codex'; then
    BOOTED=true
    break
  fi
  sleep 0.2
done

if [ "$BOOTED" = false ]; then
  echo "Error: Timed out waiting for Codex REPL to boot." >&2
  tmux capture-pane -t "$TEMP_TARGET" -p >&2
  exit 1
fi

# 3. Send "/status" command
/home/cottrell/dev/nudge/tmux-send --no-prefix "$TEMP_TARGET" "/status"

# 4. Wait for the stats screen to render (look for "Limits:")
RENDER_TIMEOUT=5
RENDERED=false
for ((i=0; i<RENDER_TIMEOUT*5; i++)); do
  output=$(tmux capture-pane -t "$TEMP_TARGET" -p 2>/dev/null || true)
  if echo "$output" | grep -q "Limits:"; then
    RENDERED=true
    break
  fi
  sleep 0.2
done

if [ "$RENDERED" = false ]; then
  echo "Error: Timed out waiting for status screen." >&2
  tmux capture-pane -t "$TEMP_TARGET" -p >&2
  exit 1
fi

# 4b. If limits need a refresh, query again
if echo "$output" | grep -q "refresh requested"; then
  sleep 1.0
  /home/cottrell/dev/nudge/tmux-send --no-prefix "$TEMP_TARGET" "/status"
  sleep 0.5
fi

# 5. Output the captured text
tmux capture-pane -t "$TEMP_TARGET" -p
