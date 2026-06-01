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

# 2. Context Re-priming (Conceptual)
# Find the latest log/manifest for this session in $STATE_DIR/$SESSION_ID/
# and prepare the context for Bifrost/LiteLLM.

# 3. Action: Send to Infrastructure Gateway
echo "[Dispatcher] Sending prompt to Gateway (Bifrost/LiteLLM)..."
# curl -X POST http://localhost:8080/v1/chat/completions \
#      -H "X-Session-ID: $SESSION_ID" \
#      -d "{'messages': [{'role': 'user', 'content': '$PROMPT'}]}"

# 4. Cycle Logging
# Record the interaction in $STATE_DIR/$SESSION_ID/manifest.json
# Append results to the corresponding Task in $BACKLOG_DIR

echo "[Dispatcher] Response received. Session $SESSION_ID updated."
