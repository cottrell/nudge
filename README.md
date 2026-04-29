# nudge

Config-driven tmux agent orchestration and monitoring.

Primary workflow is the YAML swarm CLI under `swarm/cli.py`.

States: `unknown` `working` `idle` `rate_limited` `error`

## Swarm-first workflow

Create a starter config and AGENTS note:

```bash
python swarm/cli.py init <project>
```

View/edit `./swarm/<project>.yaml`.

Apply and run:

```bash
python swarm/cli.py apply ./swarm/<project>.yaml
python swarm/cli.py status ./swarm/<project>.yaml --brief
python swarm/cli.py status ./swarm/<project>.yaml --brief -w
python swarm/cli.py broadcast ./swarm/<project>.yaml "AGENTS.md updated; please re-read it."
python swarm/cli.py usage ./swarm/<project>.yaml
python swarm/cli.py babysit apply ./swarm/<project>.yaml
python swarm/cli.py babysit status ./swarm/<project>.yaml
python swarm/cli.py babysit stop ./swarm/<project>.yaml
```

Status/usage reliability note:

- monitor state is inferred from terminal text patterns and can be wrong when CLIs redraw, change UI copy, or emit ambiguous output
- `usage` parsing is best-effort regex extraction from captured pane text; it frequently misses, lags, or misreads values across agent/version changes
- treat `status`/`usage` as operator hints, not ground truth; manual pane inspection is still required for real decisions
- no better robust cross-agent mechanism is implemented yet beyond this text-scraping approach

Attach after apply if needed:

```bash
python swarm/cli.py apply ./swarm/<project>.yaml --attach
```

Built-in examples:

- `examples/swarm-single.yaml`
- `examples/swarm-grid.yaml`

## Config model

- one tmux session
- one tmux window
- grid shape via `layout.rows` and `layout.cols`
- panes with `pane`, optional `title`, `agent`, `command`, `monitor`, optional `babysit`

Notes:

- `rows`/`cols` are validated, and layout is applied via tmux `select-layout tiled`
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

## Backend status

- **C (`monitor-bin`)**: production backend
- **Python (`monitor.py`)**: reference/test oracle

`attach.sh` uses C by default. Set `MONITOR_BACKEND=python` to use Python.

Debug helpers:

```bash
MONITOR_DEBUG=1 ./attach.sh mysession claude
MONITOR_STATE_LOG=1 ./attach.sh mysession claude
```

Defaults:

- `MONITOR_DEBUG=1` writes raw lines to `/tmp/<session>_<window-pane>.raw`
- `MONITOR_STATE_LOG=1` writes transitions to `/tmp/<session>_<window-pane>.state.log`

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
