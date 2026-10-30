#!/usr/bin/env bash
# swarm/usage/agy.sh - Scrapes Antigravity account usage via a temporary tmux session
set -euo pipefail

TEMP_SESSION="agy-usage-$$"
TEMP_TARGET="$TEMP_SESSION:0.0"

cleanup() {
  tmux kill-session -t "$TEMP_SESSION" 2>/dev/null || true
}
trap cleanup EXIT

# 1. Start agy in a detached session
# Tall window so the 38-line /usage overlay renders in full; a default 80x24
# pane pages it ("(1-10 of 38 lines)") and only the first screen is captured.
tmux new-session -d -s "$TEMP_SESSION" -x 200 -y 80 "agy"

# 2. Wait for REPL to be ready (look for prompt > or ? for shortcuts)
BOOT_TIMEOUT=15
BOOTED=false
for ((i=0; i<BOOT_TIMEOUT*5; i++)); do
  output=$(tmux capture-pane -t "$TEMP_TARGET" -p 2>/dev/null || true)
  if echo "$output" | grep -q -E '>|\? for shortcuts'; then
    BOOTED=true
    break
  fi
  sleep 0.2
done

if [ "$BOOTED" = false ]; then
  echo "Error: Timed out waiting for agy REPL to boot." >&2
  tmux capture-pane -t "$TEMP_TARGET" -p >&2
  exit 1
fi

# 3. Send "/usage" command
~/dev/nudge/tmux-send --no-prefix "$TEMP_TARGET" "/usage"

# 4. Wait for the stats screen to render (look for "used", "left", or "Resets")
RENDER_TIMEOUT=10
RENDERED=false
prev=""
stable=0
for ((i=0; i<RENDER_TIMEOUT*5; i++)); do
  output=$(tmux capture-pane -t "$TEMP_TARGET" -p 2>/dev/null || true)
  if echo "$output" | grep -q -E 'used|left|Resets|hours|%'; then
    # Groups render one after another; settle before capturing or the later
    # ones (Claude/GPT, Argon) are missed.
    if [ "$output" = "$prev" ]; then
      stable=$((stable+1))
    else
      stable=0
    fi
    prev="$output"
    if [ "$stable" -ge 3 ]; then
      RENDERED=true
      break
    fi
  fi
  sleep 0.2
done
if [ "$RENDERED" = false ] && [ -n "$prev" ]; then
  RENDERED=true
fi

if [ "$RENDERED" = false ]; then
  echo "Error: Timed out waiting for usage screen." >&2
  tmux capture-pane -t "$TEMP_TARGET" -p >&2
  exit 1
fi

# 5. Output the captured text
tmux capture-pane -t "$TEMP_TARGET" -p
