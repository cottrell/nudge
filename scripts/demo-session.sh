#!/usr/bin/env bash
# aiswarm demo — ONE terminal you record.
#
# Outer typealong only does: mkdir, init, start.
# Everything else (sends, backlog, tasks, close task) runs in tmux pane 0.7
# (the operator shell) so you see it in the grid — not a second terminal.
#
# Recommended:
#   1. Large terminal, Ctrl+Alt+Shift+R to START recording
#   2. make demo
#   3. Watch init/start, then grid; ops scroll in bottom-right shell (0.7)
#      Zoom shell: Ctrl-b z   Pane numbers: Ctrl-b q
#   4. When ops finish, Ctrl-b d to detach
#   5. Ctrl+Alt+Shift+R to STOP recording
#   6. make demo-teardown
#
# Nested tmux: outer prefix then inner — often Ctrl-b Ctrl-b d to detach demo.
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SESSION_NAME="${AISWARM_DEMO_NAME:-aiswarm-demo}"
LATEST_LINK="/tmp/aiswarm-demo-latest"
DRIVE=1
MANUAL=0
RECORD=0
TEARDOWN=""
OUT_DIR=""
DRIVE_BOOT_SECS="${DRIVE_BOOT_SECS:-8}"
PAUSE="${DEMO_PAUSE:-0.6}"
COUNTDOWN="${RECORD_COUNTDOWN_SECS:-5}"
# Short window in pane 0.7 to click trust prompts before ops continue.
OPS_TRUST_SECS="${OPS_TRUST_SECS:-8}"

usage() {
  sed -n '2,20p' "$0" | sed 's/^# \?//'
  exit "${1:-0}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help) usage 0 ;;
    --no-drive) DRIVE=0; shift ;;
    --drive) DRIVE=1; shift ;;
    --manual) MANUAL=1; shift ;;
    --record) RECORD=1; shift ;;
    --teardown) TEARDOWN="${2:-}"; shift 2 ;;
    --name) SESSION_NAME="$2"; shift 2 ;;
    --dir) OUT_DIR="$2"; shift 2 ;;
    --setup-only) MANUAL=1; DRIVE=0; shift ;;
    --show|--start|--attach) shift ;;
    *) echo "unknown arg: $1" >&2; usage 1 ;;
  esac
done

say() { printf '%s\n' "$*"; }
run() {
  printf '\n\033[1;32m$ %s\033[0m\n' "$*"
  sleep "$PAUSE"
  eval "$@"
  sleep "$PAUSE"
}

# Plain prompt for screencasts (outer typealong; pane 0.7 also uses --norc + PS1).
export PS1='\$ '

session_name_from_dir() {
  local dir="$1" cfg name=""
  cfg="$dir/.aiswarm/config.yaml"
  [[ -f "$cfg" ]] && name="$(awk '/^session_name:/{print $2; exit}' "$cfg")"
  echo "${name:-$SESSION_NAME}"
}

teardown() {
  local dir="$1"
  if [[ "$dir" == "latest" ]]; then
    [[ -e "$LATEST_LINK" ]] || { echo "no $LATEST_LINK" >&2; exit 1; }
    dir="$(readlink -f "$LATEST_LINK")"
  fi
  [[ -d "$dir" ]] || { echo "teardown: bad dir $dir" >&2; exit 1; }
  local name
  name="$(session_name_from_dir "$dir")"
  say "Stopping '$name'…"
  (cd "$dir" && aiswarm stop 2>/dev/null) || true
  tmux has-session -t "$name" 2>/dev/null && tmux kill-session -t "$name" 2>/dev/null || true
  say "Tree left at: $dir"
}

if [[ -n "$TEARDOWN" ]]; then
  teardown "$TEARDOWN"
  exit 0
fi

if ! command -v aiswarm >/dev/null 2>&1; then
  echo "aiswarm not on PATH (cd $ROOT && make install-aiswarm)" >&2
  exit 1
fi

STAMP="$(date +%Y%m%d-%H%M%S)"
OUT_DIR="${OUT_DIR:-/tmp/aiswarm-demo-${STAMP}}"
mkdir -p "$OUT_DIR"
ln -sfn "$OUT_DIR" "$LATEST_LINK"

seed_claude_trust() {
  python3 - "$1" <<'PY' 2>/dev/null || true
import json, sys
from pathlib import Path
proj = str(Path(sys.argv[1]).resolve())
path = Path.home() / ".claude.json"
if not path.is_file():
    raise SystemExit(0)
data = json.loads(path.read_text())
projects = data.setdefault("projects", {})
entry = dict(projects.get(proj) or {})
if entry.get("hasTrustDialogAccepted") is not True:
    entry["hasTrustDialogAccepted"] = True
    projects[proj] = entry
    path.write_text(json.dumps(data, indent=2) + "\n")
PY
}

# Operator script — runs *inside* pane 0.7 so the grid video shows it.
write_ops_script() {
  local dir="$1" name="$2" do_drive="$3" trust_secs="$4" boot_secs="$5"
  # runx: print and eval the identical string (no nicknames / ellipsis / mismatch).
  cat > "$dir/demo-ops.sh" <<EOF
#!/usr/bin/env bash
# Auto-run in aiswarm shell pane 0.7 (operator). Safe to re-run by hand.
set -euo pipefail
cd $(printf %q "$dir")
export PATH="\$HOME/.local/bin:\$PATH:\$(dirname "\$(command -v aiswarm 2>/dev/null || true)")"
export PS1='\$ '
SESSION_NAME=$(printf %q "$name")
DO_DRIVE=$(printf %q "$do_drive")
TRUST_SECS=$(printf %q "$trust_secs")
BOOT_SECS=$(printf %q "$boot_secs")

runx() {
  # Exactly one string: what you see is what runs.
  local cmd=\$*
  printf '\\n\\033[1;32m\$ %s\\033[0m\\n' "\$cmd"
  eval "\$cmd"
}

echo
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  OPERATOR PANE 0.7 — sends + backlog live here           ║"
echo "║  Zoom this pane: Ctrl-b z   (again to unzoom)            ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo
echo "You have ~\${TRUST_SECS}s to chase any 'trust this folder' prompts in"
echo "other panes (click them). Ops continue automatically after that."
for ((i=TRUST_SECS; i>0; i--)); do printf '\\r  trust window: %2ds  ' "\$i"; sleep 1; done
printf '\\r                              \\n\\n'

# Peer pings first (not the same work as the backlog task below).
if [[ "\$DO_DRIVE" == "1" ]]; then
  runx "aiswarm send 0.1 \\"Wave once with a one-word greeting, then stop.\\"" || true
  echo "(waiting \${BOOT_SECS}s for delivery / idle…)"
  sleep "\$BOOT_SECS"
  runx "aiswarm send 0.0 \\"One word only: ping. Then stop.\\"" || true
  sleep 3
fi

if ! command -v backlog >/dev/null 2>&1; then
  echo "backlog not on PATH — skip task coda"
else
  echo
  echo "=== backlog + tasks (still in pane 0.7) ==="
  echo "Task stays To Do / In Progress for agents — we do NOT mark Done here."
  runx "backlog init \$SESSION_NAME --defaults" || true
  runx "backlog config set autoOpenBrowser false" || true
  runx "aiswarm tasks start"
  # Distinct from peer pings so agents do not treat prior chat as completing this task.
  runx "backlog task create \\"write DEMO-OK file\\" -d \\"Create a file named demo-result.txt in the project root containing exactly the line: DEMO-OK\\" --ac \\"demo-result.txt exists with line DEMO-OK\\" --plain"
  runx "backlog task list --plain"
  runx "aiswarm tasks status"
  echo "(short wait for claim; watch log 0.6 / agents)"
  sleep 6
  runx "backlog task list --plain"
  runx "aiswarm tasks status"
fi

echo
echo "=== operator script done (task left open for agents) ==="
echo "Detach when ready: Ctrl-b d  (nested: Ctrl-b Ctrl-b d)"
echo "After detach, the outer demo may mark TASK-1 Done for the video coda."
echo "Stop GNOME record: Ctrl+Alt+Shift+R"
EOF
  chmod +x "$dir/demo-ops.sh"

  cat > "$dir/README.md" <<EOF
# $name

aiswarm demo. **Operator work happens in pane 0.7** (\`bash demo-ops.sh\`).

| id  | role |
|-----|------|
| 0.0–0.5 | agents |
| 0.6 | aiswarm log -w |
| 0.7 | shell — sends, backlog, tasks |

Record: Ctrl+Alt+Shift+R start/stop. Teardown: scripts/demo-session.sh --teardown latest
EOF

  cat > "$dir/demo-cmds.sh" <<'CMDS'
# Manual one-liners if not using demo-ops.sh
aiswarm send 0.1 "Wave once with a one-word greeting, then stop."
backlog init aiswarm-demo --defaults
aiswarm tasks start
backlog task create "write DEMO-OK file" -d "Create demo-result.txt with exactly: DEMO-OK" --ac "demo-result.txt has DEMO-OK" --plain
# mark Done only after agents finish — not immediately
CMDS
}

if [[ "$MANUAL" -eq 1 ]]; then
  write_ops_script "$OUT_DIR" "$SESSION_NAME" "$DRIVE" "$OPS_TRUST_SECS" "$DRIVE_BOOT_SECS"
  seed_claude_trust "$OUT_DIR"
  cat <<EOF

Manual (one terminal — ops in pane 0.7 after start):

  # Record: Ctrl+Alt+Shift+R start / same to stop → ~/Videos/Screencasts/

  mkdir -p $OUT_DIR && cd $OUT_DIR
  aiswarm init $SESSION_NAME --flavour demo
  mkdir -p backlog
  aiswarm start
  # In shell pane 0.7 (or after attach + select 0.7):
  bash demo-ops.sh
  tmux attach -t $SESSION_NAME

  $ROOT/scripts/demo-session.sh --teardown latest

demo-ops.sh written under $OUT_DIR
EOF
  exit 0
fi

if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
  echo "Session $SESSION_NAME already exists:" >&2
  echo "  $ROOT/scripts/demo-session.sh --teardown latest" >&2
  exit 1
fi

write_ops_script "$OUT_DIR" "$SESSION_NAME" "$DRIVE" "$OPS_TRUST_SECS" "$DRIVE_BOOT_SECS"
seed_claude_trust "$OUT_DIR"

RECORD_PID=""
cleanup() {
  [[ -n "${RECORD_PID:-}" ]] && kill -INT "$RECORD_PID" 2>/dev/null || true
}
trap cleanup EXIT

if [[ "$RECORD" -eq 1 && -n "${DISPLAY:-}" ]] && command -v ffmpeg >/dev/null 2>&1; then
  REC_FILE="$OUT_DIR/screencast-${STAMP}.mp4"
  ffmpeg -y -f x11grab -framerate 15 -i "${DISPLAY}.0" \
    -c:v libx264 -preset ultrafast -pix_fmt yuv420p \
    "$REC_FILE" >/tmp/aiswarm-demo-ffmpeg.log 2>&1 &
  RECORD_PID=$!
  say "ffmpeg whole-screen pid=$RECORD_PID → $REC_FILE"
fi

clear
cat <<'BANNER'
╔══════════════════════════════════════════════════════════════════╗
║  RECORD THIS TERMINAL  (Ctrl+Alt+Shift+R start / stop)           ║
║                                                                  ║
║  Outer:  aiswarm init + start only                               ║
║  Grid:   agent panes + log (0.6) + shell (0.7)                   ║
║  Shell:  demo-ops.sh — pings + backlog task (left open for agents)║
║          (zoom shell with Ctrl-b z if hard to read)              ║
╚══════════════════════════════════════════════════════════════════╝
BANNER
say "Countdown ${COUNTDOWN}s…"
for ((i=COUNTDOWN; i>0; i--)); do printf '\r  %2d ' "$i"; sleep 1; done
printf '\r     \n\n'

run "cd $(printf %q "$OUT_DIR")"
cd "$OUT_DIR"

run "aiswarm init $(printf %q "$SESSION_NAME") --flavour demo"
if [[ ! -d .git ]]; then
  git init -q
  git add -A
  git -c user.email=demo@localhost -c user.name=demo commit -q -m "demo" 2>/dev/null || true
fi

run "ls -a"
run "cat README.md"
run "head -30 .aiswarm/config.yaml"
run "mkdir -p backlog"

run "aiswarm start"
sleep 1

# Kick operator script in the shell pane, then attach so you see it live.
tmux select-pane -t "${SESSION_NAME}:0.7" 2>/dev/null \
  || tmux select-pane -t "${SESSION_NAME}:grid.7" 2>/dev/null \
  || true
tmux send-keys -t "${SESSION_NAME}:0.7" C-c 2>/dev/null || true
sleep 0.2
tmux send-keys -t "${SESSION_NAME}:0.7" -l -- "clear; bash ./demo-ops.sh"
tmux send-keys -t "${SESSION_NAME}:0.7" C-m

say ""
say ">>> Attaching — watch pane 0.7 (shell) for sends/backlog/tasks"
say ">>> Zoom 0.7: Ctrl-b z    Numbers: Ctrl-b q    Detach: Ctrl-b d"
sleep 1

tmux attach -t "$SESSION_NAME" || true

say ""
say "=== after detach: optional coda mark task Done (agents had time while you watched) ==="
if command -v backlog >/dev/null 2>&1 && [[ -f backlog/config.yml ]]; then
  # Only now — never race the agent by closing during ops.
  run "backlog task list --plain"
  run "backlog task edit 1 -s Done --final-summary \"Demo coda: operator closed TASK-1 after watching.\" --plain" || true
  run "backlog task 1 --plain" || true
fi

say ""
say "=== demo complete (ops ran in pane 0.7) ==="
say "STOP recording:  Ctrl+Alt+Shift+R"
say "Video:  ~/Videos/Screencasts/  or  ~/Videos/"
say "Teardown:  $ROOT/scripts/demo-session.sh --teardown latest"
if [[ -n "${REC_FILE:-}" && -f "${REC_FILE:-}" ]]; then
  say "ffmpeg file: $REC_FILE"
fi
