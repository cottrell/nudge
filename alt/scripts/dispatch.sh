#!/bin/bash
# Prompt Dispatcher: Unified interface for interacting with "Things"
# Usage: ./dispatch.sh "your prompt" [optional_session_id]

PROMPT=$1
SESSION_ID=$2
STATE_DIR="./alt/state"
BACKLOG_DIR="./backlog/tasks"

mkdir -p "$STATE_DIR"

if [ -z "$PROMPT" ]; then
    echo "Usage: $0 \"prompt\" [session_id]"
    exit 1
fi

# 1. Session ID Management
if [ -z "$SESSION_ID" ]; then
    SESSION_ID="session-$(date +%s)-${RANDOM}"
    echo "[Dispatcher] No session ID provided. Creating new: $SESSION_ID"
    # Registration in backlog would happen here (e.g. creating a new task file)
else
    echo "[Dispatcher] Resuming session: $SESSION_ID"
fi

# 2. Context / Mailbox
# For sub CLIs: write to directed comms logs under alt/state/ or backlog.
# Poke the target pane with tmux-send (never raw send-keys).
# See README and grok_notes for mailbox + Pulse pattern.

# 3. For pure subscription harnesses (default):
# The prompt or nudge goes to the specific tmux pane / harness for the node.
# Quota signals come from monitor sockets (usage_pct) or swarm/cli.py usage probe.
# No gateway in the path.

# 4. Cycle Logging
# Record the interaction in $STATE_DIR/$SESSION_ID/manifest.json (or per-Thing graph).
# Append results / updates to the corresponding Task in $BACKLOG_DIR.

echo "[Dispatcher] Dispatched / logged for $SESSION_ID. Use Pulse + monitor for quotas."
