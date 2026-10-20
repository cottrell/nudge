<!-- AISWARM/NUDGE GUIDELINES START -->
## Swarm

Swarm CLI: `aiswarm` (on PATH; `make install-aiswarm` from the nudge repo).

Read workflow first:
- `aiswarm` — common commands cheat sheet
- `aiswarm instructions overview` — required agent briefing
- `aiswarm instructions tasks` — backlog dispatcher
- `aiswarm this` — this swarm's config + runtime.json path

After start, machine map (not git): `/tmp/nudge-swarm/j/runtime.json`

Config: `.aiswarm/config.yaml` (cwd walk-up), `$AISWARM_CONFIG`, or explicit path.
Messaging: `aiswarm send <pane> "msg"` (durable log). Do NOT raw `tmux send-keys`.
Do NOT attach/stream a peer pane. Snapshot: `aiswarm capture`. Block until idle: `aiswarm wait`.
Human presence: `aiswarm presence` (`IN` -> ask questions; `OUT` -> autonomous progress on routine authorized tasks, do not pause for trivial approvals; seek approval if material architecture/design decision requires it).
TUI findings are not done: file backlog tasks/docs, ping the requester, then idle.
<!-- AISWARM/NUDGE GUIDELINES END -->
