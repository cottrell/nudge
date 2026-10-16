# Workflow

Short start is in the [README](../README.md). This page is send, categories, and handoff.

`aiswarm start` creates the tmux grid. It is not a declarative update: changing pane or window counts in the YAML after the swarm is running makes `start` refuse and tell you to recreate the session. Worker and monitor config is more forgiving on re-start.

One tmux session per YAML file (`session_name`). One monitor (`monitor-bin`) per `monitor: true` pane, each with its own Unix socket `/tmp/<session>_<W.N>.sock`. Comms workers (log consumers that deliver on idle) start for monitored panes. Babysit is not turned on by `start`. Tasks are not turned on by `start`.

```bash
aiswarm start --attach
aiswarm start --skip-grid          # tmuxp already loaded the grid
tmuxp load .aiswarm/config.yaml
```

Built-in examples: `examples/swarm-single.yaml`, `examples/swarm-grid.yaml`.

## Commands

```bash
aiswarm start --skip-grid
aiswarm status --brief -w
aiswarm broadcast "AGENTS.md updated; please re-read it."
aiswarm broadcast --via-log "use durable log"    # write to event log instead of direct send
aiswarm send 0.0 "hello via log"                 # durable, delivered on idle
aiswarm send any "investigate the failure"       # durable, exactly one idle pane
aiswarm send --at +30m 0.0 "poke in 30m"         # scheduled delivery (+2h, +30m, ISO timestamp)
aiswarm send -s otherswarm 0.1 "hi from nudge"   # cross-swarm, via its runtime.json
aiswarm log --pending
aiswarm cursors
aiswarm clear-comms -y
aiswarm quota
aiswarm av-usage
```

Broadcast and log-delivered messages are sent literally. Do not add synthetic sender prefixes, and keep slash commands like `/clear` unchanged. Direct sends still work with `tmux-send`. Prefer that, or the log commands, over raw `tmux send-keys`.

## `send any`

`send any` is the single-consumer counterpart to broadcast. It queues immediately, even when all panes are busy. The comms worker routes it to exactly one idle monitored pane. Panes holding local Backlog task assignments are skipped. This does not require `aiswarm tasks start`, and it does not add task completion or chase semantics.

## Scheduled send

`aiswarm send --at <ISO timestamp|+Nh|+Nm|+Ns>` defers delivery (`+2h`, `+30m`, `+45s`, `2026-10-02T12:00:00`). The message is stored in the durable event log with a not-before timestamp and delivered only after that time and the normal idle conditions. It does not head-of-line block later immediate messages. Due times show in `aiswarm log --pending` and `aiswarm status`.

## Pane categories

List labels per pane (`nudge.categories: [heavy, claude]`; several allowed). `aiswarm send heavy "msg"` is `send any` restricted to panes carrying that category. A category with no free pane stays queued. A target that is no pane, `any`, or a configured category is an error. `aiswarm status` ends with a per-category rollup (panes, idle, pending messages, open `cat:` tasks). Names may not be `any`, `mcp`, or a pane id. Backlog tasks labelled `cat:heavy` are only dispatched to panes with that category (all `cat:` labels required). Unlabelled tasks go anywhere.

## Agent-to-agent handoff

Prefer short `aiswarm send` pokes, durable results in backlog, and a short done-ping. Do not attach to a peer pane. Snapshot with `aiswarm capture`. Block in-process with `aiswarm wait` (polls the monitor, one line of output). TUI findings are not done.

Longer example: `backlog/docs/doc-2 - Agent-to-agent-handoff-via-send-backlog-and-ping.md`.
