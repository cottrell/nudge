# nudge

Config-driven tmux agent orchestration and monitoring.

Primary workflow is the YAML swarm CLI under `swarm/cli.py`.

States: `unknown` `working` `idle`

## Swarm-first workflow

Create a starter config and AGENTS note:

```bash
python swarm/cli.py init <project>
```

View/edit `./swarm/<project>.yaml`.

Apply and run:

```bash
python swarm/cli.py apply ./swarm/<project>.yaml
python swarm/cli.py apply --skip-grid ./swarm/<project>.yaml
python swarm/cli.py status ./swarm/<project>.yaml --brief
python swarm/cli.py status ./swarm/<project>.yaml --brief -w
python swarm/cli.py broadcast ./swarm/<project>.yaml "AGENTS.md updated; please re-read it."
python swarm/cli.py usage ./swarm/<project>.yaml
python swarm/cli.py stop ./swarm/<project>.yaml
python swarm/cli.py babysit apply ./swarm/<project>.yaml
python swarm/cli.py babysit status ./swarm/<project>.yaml
python swarm/cli.py babysit stop ./swarm/<project>.yaml
```

Status/usage reliability note:

- monitor state is activity-based: any pane output means `working`; 10 seconds without output means `idle`
- output content is not classified, so agent UI text changes do not affect state detection
- quiet long-running commands can appear idle, while continuous idle-screen redraws can appear working
- `usage` is handled separately and remains best-effort; treat it as an operator hint

Attach after apply if needed:

```bash
python swarm/cli.py apply ./swarm/<project>.yaml --attach
```

tmuxp-first flow:

```bash
tmuxp load ./swarm/<project>.yaml
python swarm/cli.py apply --skip-grid ./swarm/<project>.yaml
```

Built-in examples:

- `examples/swarm-single.yaml`
- `examples/swarm-grid.yaml`

## Config model

- one tmux session
- one or more tmux windows
- each window has `window_name`, `layout`, and `panes`
- pane command is `shell_command`
- nudge metadata is under `nudge.*` (`title`, `agent`, `monitor`, `babysit`)

Notes:

- pane IDs are derived as `W.N` (window index, pane index)
- `apply` creates/expands windows and applies per-window tmux layout
- `apply --skip-grid` skips session/window creation and only sets up monitors/titles/commands
- `apply` and `babysit apply` write runtime files under `/tmp/nudge-swarm/<session>/`
- runtime map: `/tmp/nudge-swarm/<session>/runtime.json`
- self-awareness note: `/tmp/nudge-swarm/<session>/self-awareness.txt`

## Internal plumbing

These are low-level helpers used by swarm tooling and power users:

- `attach.sh` (monitor attach to pane)
- `tmux-send` (safe text+Enter send)
- `keyboard-2pane.sh` (line relay utility)
- `babysit.sh` and `babysit-manager.sh` (legacy/manual babysit path)

When messaging panes manually, prefer `tmux-send` over raw `tmux send-keys`.

## Build and test

```bash
make build
make test
make test-python
make test-c
make test-swarm
```

Python helpers live in `pyproject.toml`:

```bash
uv sync
```

## Capture fixtures

Fixture replay tests depend on real captured agent output in `fixtures/*_capture.txt`.

Fixtures now exercise real terminal byte streams rather than expected UI patterns.
Re-capture when replay tests expose an input-handling issue or fixtures become stale.

Commands:

```bash
make capture AGENT=claude DUR=60
make capture_codex DUR=60
make capture_copilot DUR=60
make capture_gemini DUR=60
make capture_vibe DUR=60
make capture_qwen DUR=60
make capture_all DUR=60
```

Practical cadence: re-capture on breakage or visible upstream CLI changes, not on a fixed schedule.

## Backend status

- **C (`monitor-bin`)**: production backend
- **Python (`monitor.py`)**: reference/test oracle

`attach.sh` uses C by default. Set `MONITOR_BACKEND=python` to use Python.

Debug helpers:

```bash
MONITOR_DEBUG=1 ./attach.sh mysession claude
MONITOR_STATE_LOG=1 ./attach.sh mysession claude
MONITOR_IDLE_SECS=20 ./attach.sh mysession claude
```

Defaults:

- `MONITOR_DEBUG=1` writes raw lines to `/tmp/<session>_<window-pane>.raw`
- `MONITOR_STATE_LOG=1` writes transitions to `/tmp/<session>_<window-pane>.state.log`
- `MONITOR_IDLE_SECS` controls the quiet period before `idle` (default: 10)

The monitor deliberately reports activity, not semantic agent status. It does not
distinguish waiting for input, rate limiting, errors, or silent computation.

## Similar projects

- [ccmanager](https://github.com/kbwo/ccmanager)
- [tallr](https://github.com/kaihochak/tallr)
- [agent-tmux-monitor](https://github.com/damelLP/agent-tmux-monitor)
- [tmuxcc](https://github.com/nyanko3141592/tmuxcc)
- [agent-deck](https://github.com/asheshgoplani/agent-deck)
- [agent-of-empires](https://github.com/njbrake/agent-of-empires)
- [tmux-agent-indicator](https://github.com/accessd/tmux-agent-indicator)
- [tmuxp](https://tmuxp.git-pull.com/)
- [tmuxinator](https://github.com/tmuxinator/tmuxinator)
- [teamocil](https://github.com/remiprev/teamocil)
- [Zellij](https://zellij.dev/)

See `AGENTS.md` for contribution guidance and `TODO.md` for planned work.
