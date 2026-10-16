# Config

YAML shape and what `start` actually launches. The short path is in the [README](../README.md).

- one tmux session
- one or more tmux windows
- each window has `window_name`, `layout`, and `panes`
- pane command is `shell_command`. A value that is exactly a key in `swarm/models.yaml` (`codex:heavy`) expands to that command on load. Any other string is launched as written.
- nudge metadata is under `nudge.*` (`title`, `agent`, `monitor`, `babysit`, `comms`, `tasks`)
- `comms.enabled` (defaults to `monitor`) is served by the session worker, which consumes each pane's durable log and delivers on idle
- optional top-level `tasks:` configures a task-dispatch group in that same session worker (v1 source: backlog)

## Start and workers

- Pane IDs are `W.N` (window index, pane index).
- `start` creates the tmux grid from the YAML. Re-running it after a pane-count or layout change on a live session is refused. Recreate the session.
- One monitor per `monitor: true` pane (started by `start`).
- `start` ensures one Python `session_worker.py` for the swarm. It multiplexes comms and message delivery for monitored panes.
- `babysit start` enables the babysit prompt group for panes with `babysit.enabled: true`. It does not affect the base comms loop. `--for 1h` (also `30m`, `90s`, or seconds) auto-disables that group when the deadline passes. `babysit stop` clears any timer.
- `session_worker.py` is the one process shown in `ps` for a swarm, not one Python process per pane. It handles comms for every configured pane and enables babysit prompts only for panes in that group. `pane_worker.py` is the compatibility entrypoint.
- `tasks start` enables a session-level group in that same worker. See [tasks](tasks.md).
- `tasks stop` / `tasks start` only toggle that group. They do not restart the shared worker or reload edited Python. `tasks start --for 1h` writes a deadline into `tasks/enabled.json`. The session worker drops the group when it expires, and `tasks stop` removes the timer. Use `aiswarm worker restart` to load current installed or editable-source code without stopping tmux panes, agents, or monitors.
- `worker restart` preserves pane specs, enabled group flags, task assignment state, and the durable comms database and cursors. It validates the recorded worker process before terminating it.

## Paths

- `start`, `babysit start`, and `tasks start` write runtime files under `/tmp/nudge-swarm/<session>/`
- runtime map: `/tmp/nudge-swarm/<session>/runtime.json` (path via `aiswarm this`)
- provider session IDs: `aiswarm sessions` (also `session-ids.json` next to the config and under the runtime dir). Claude and Grok are launched with `--session-id`. Live panes are matched by PID and open files, not newest-cwd.
- tasks dispatcher state and enable flag: `/tmp/nudge-swarm/<session>/tasks/`
- presence state: `/tmp/nudge-swarm/presence_global.json` and `/tmp/nudge-swarm/<session>/presence_local.json`

## `start --resume`

`aiswarm start --resume` splices a recorded id into the pane command before mint.

- Claude and Grok get `-r <id>` (an existing `--session-id` is removed first).
- Antigravity gets `--conversation <id>`.
- Codex becomes `codex resume <id>` plus the config flags.
- No recorded id keeps `pane.command` (Claude and Grok still mint).
- Plain `start` always mints.
