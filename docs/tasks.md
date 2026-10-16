# Tasks dispatcher

Fixed babysit "please continue" prompts waste tokens when real work already lives in backlog. The dispatcher lists and claims backlog tasks itself, then delivers one concrete task to a free pane. Delivery uses the durable log, so the idle consumer still gates tmux-send. It uses `backlog task list|view --json` only. Do not scrape `--plain`.

`aiswarm start` does not start this dispatcher. Run `aiswarm tasks start` or a single `aiswarm tasks once`.

```yaml
# top-level (session)
tasks:
  source: backlog                 # v1 only; name stays generic for future sources
  backlog_dir: ../backlog         # optional; walks up for backlog/config.yml if omitted
  ingest: [To Do, In Progress]    # default; In Progress lets a restarted dispatcher recover claims
  poll_secs: 60
  min_chase_secs: 60              # min between chase re-prompts; default = poll_secs
  unassigned_only: true
  require_label: null             # e.g. auto — only tasks with this label
  claim_assignee_prefix: aiswarm  # assignee becomes aiswarm:<session>:<pane>
  require_idle: true
  via_log: true
  max_inflight: 0                 # 0 = unlimited; still one task per free pane
  clear_on_claim: true            # deliver /clear to pane before sending new task claim
  clear_every: 0                  # deliver /clear every N chase nudges (0 = disabled)
  complete_statuses: [Done]       # dep gate + assignment clear; case-insensitive

windows:
  - window_name: grid
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
          babysit:
            enabled: false        # prefer not both on same pane (fights tasks chase)
          tasks:
            enabled: true
            gate_command: null    # optional: shell command; pane is only free when exit code is 0
```

```bash
aiswarm tasks start
aiswarm tasks start --for 1h   # optional; auto-stop after an hour
aiswarm tasks status
aiswarm tasks once
aiswarm tasks once -D          # dry-run: resolved config + planned claims
aiswarm tasks stop
```

Monitored panes have tasks enabled by default. Opt out with `nudge.tasks.enabled: false`.

Claim happens before log delivery (`In Progress` plus assignee). Completion is not inferred from pane idle. The agent or a human marks the task Done via the backlog CLI. Local assignment state clears on the next poll when status is Done.

- **`skip_assignees`:** (default `[human]`) assignees the dispatcher will not claim or reclaim. Use `-a human` to park a task for people. Empty list disables the skip. Swarm ownership is only `aiswarm:<session>:<pane>`, never model names.
- **Dependency gate:** any incomplete dependency (status not in `complete_statuses`, default `Done`) blocks claim and chase of the parent, regardless of who owns the dep. The same predicate clears local assignments. Link with `backlog task edit TASK-NN --depends-on TASK-BLOCKER`. Cycles and missing ids still block.
- **Chase:** idle, still assigned, and deps Done means a short re-prompt until Done or unassign. Interval is `min_chase_secs` (default same as `poll_secs`). Raise it only to nudge less often.

Each `tasks once` pass, and each poll from `tasks start`, assigns at most one task to each free pane. A pane is free when it has no local assignment or pending comms-log event, passes its optional `gate_command` (if defined, must exit 0; `{pane}` and `{agent}` are replaced), and by default is idle (`require_idle: true`; monitor-unknown panes are also eligible). With N free panes and M candidate tasks, the pass claims `min(N, M)` tasks, further limited by `max_inflight` when that is greater than zero. Three free panes and ten To Dos claim three tasks this pass. The other seven wait until a later poll finds a free slot.

The dispatcher does not dump the whole To Do list onto one pane and does not queue multiple tasks on a pane that already has an assignment.

## Stalled assigned panes

After `healthcheck_chases` idle chases (default 3), the dispatcher sends one durable `HEALTHCHECK` with a nonce. The agent replies with `aiswarm healthcheck pong <pane> <nonce>`. Consumer delivery acks do not count. No pong before `healthcheck_timeout_secs` (default 300) restarts only that pane, re-attaches its monitor, and queues a chase. `healthcheck_max_restarts` (default 1) caps retries. Then the dispatcher leaves the assignment for an operator or a later peer-checkup path. This is not a continuous heartbeat and never scrapes provider-specific error text.
