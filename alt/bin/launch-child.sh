#!/bin/bash
# alt/bin/launch-child.sh
# Fire-and-forget launch for a Thing child node using -p / exec style.
# Per-provider best effort (no universal clean pattern exists):
#
# - claude: supports --session-id at creation. Generate and pass it.
# - codex: prints "session id:" in the exec banner. Capture from output.
# - grok:   newest session dir under ~/.grok/sessions/<cwd-encoded>/ after launch.
# - agy:    newest session-* file in ~/.gemini/tmp or ~/.cache after launch.
#
# We record the SID we actually got so the node can be resumed/forked later.
# Records node on start and on finish.
#
# Usage: launch-child.sh <thing_id> <node_id> <agent> <prompt>
#        launch-child.sh ... --fork-from <parent_sid>   # for claude continuation
# Example: ./launch-child.sh thing-abc impl-1 codex "do the refactor"

set -euo pipefail

THING=$1
NODE=$2
AGENT=$3
PROMPT=$4

STATE_DIR="./alt/state/things/$THING"
mkdir -p "$STATE_DIR"
NODE_FILE="$STATE_DIR/$NODE.json"

# Best per-provider strategy for getting a usable session_id.
# No universal "clean" way exists because providers behave differently.
#
# - Claude: supports --session-id at launch time. Generate one and pass it.
# - Codex: prints the ID in the exec banner. Capture it from output.
# - Agy / Grok: no way to supply at creation; capture via fs observation after launch.
#
# We generate the ID inside the case only when the provider lets us supply it.
# Otherwise we capture whatever the provider assigned.

LOG="$STATE_DIR/$NODE.output.txt"
SID=""

case "$AGENT" in
  codex)
    echo "[launch] codex exec for $NODE"
    codex exec "$PROMPT" >"$LOG" 2>&1 &
    cpid=$!
    for _ in {1..60}; do
      SID=$(grep -o 'session id: [0-9a-f-]*' "$LOG" | head -1 | cut -d: -f2- | tr -d ' ' || echo "")
      [ -n "$SID" ] && break
      sleep 0.1
    done
    [ -z "$SID" ] && SID=$(grep -o 'rollout-[0-9a-f-]*' "$LOG" | head -1 || echo "")
    wait $cpid || true
    ;;
  claude)
    # Best option: we can create/supply the ID ourselves at launch.
    SID=$(uuidgen 2>/dev/null || python3 -c 'import uuid; print(uuid.uuid4())')
    echo "[launch] claude -p --session-id $SID for $NODE"
    claude -p --session-id "$SID" --dangerously-skip-permissions "$PROMPT" >"$LOG" 2>&1 &
    cpid=$!
    sleep 1
    # Defensive: if the on-disk file ends up with a different id, prefer it.
    if [ -f ~/.claude/sessions/$cpid.json ]; then
      SID2=$(python3 -c "
import json, sys
print(json.load(open(sys.argv[1])).get('sessionId',''))
" ~/.claude/sessions/$cpid.json 2>/dev/null || echo "")
      [ -n "$SID2" ] && SID=$SID2
    fi
    wait $cpid || true
    ;;
  agy)
    echo "[launch] agy -p for $NODE"
    agy -p --dangerously-skip-permissions "$PROMPT" >"$LOG" 2>&1 &
    apid=$!
    sleep 0.5
    # Mechanical fs capture of what the launch created.
    SID=$(find ~/.gemini/tmp ~/.cache -type f -name 'session-*' -newermt '3 seconds ago' 2>/dev/null | head -1 | grep -o '[0-9a-f-]\{36\}' | head -1 || echo "")
    [ -z "$SID" ] && SID=$(grep -o '[0-9a-f]\{8\}-[0-9a-f]\{4\}-[0-9a-f]\{4\}-[0-9a-f]\{4\}-[0-9a-f]\{12\}' "$LOG" | head -1 || echo "")
    wait $apid || true
    ;;
  grok)
    echo "[launch] grok for $NODE"
    grok -p --always-approve "$PROMPT" >"$LOG" 2>&1 &
    gpid=$!
    sleep 0.5
    # Scoped to cwd + newest dir after launch.
    CWD_ENC=$(echo -n "$PWD" | sed 's|/|%2F|g')
    SID=$(ls -1t ~/.grok/sessions/$CWD_ENC/ 2>/dev/null | head -1 || echo "")
    wait $gpid || true
    ;;
  *)
    SID="synthetic-$(date +%s)-$$"
    "$AGENT" "$PROMPT" >"$LOG" 2>&1 || true
    ;;
esac

# Record start with SID
cat > "$NODE_FILE" <<EOF
{
  "thing": "$THING",
  "node": "$NODE",
  "agent": "$AGENT",
  "session_id": "$SID",
  "launched_at": "$(date -Iseconds)",
  "prompt": "$PROMPT",
  "status": "running",
  "log": "$LOG"
}
EOF
echo "[launch] start recorded $NODE sid=$SID"

# Finish
python3 -c '
import json, sys, datetime
f = sys.argv[1]
with open(f) as fh: d = json.load(fh)
d["finished_at"] = datetime.datetime.now().isoformat()
d["status"] = "done"
with open(f, "w") as fh: json.dump(d, fh, indent=2)
' "$NODE_FILE"

echo "[launch] finish recorded for $NODE"
echo "SID: $SID"
