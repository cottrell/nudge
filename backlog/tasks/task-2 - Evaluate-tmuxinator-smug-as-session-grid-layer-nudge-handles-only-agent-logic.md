---
id: TASK-2
title: 'Evaluate tmuxinator/smug as session-grid layer, nudge handles only agent logic'
status: To Do
assignee: []
created_date: '2026-04-30 09:11'
labels: []
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
nudge currently owns session/window/pane creation, grid layout, and agent-specific logic.
smug (https://github.com/ivaaaan/smug) is a Go binary tmux session manager that can replace
the layout layer. nudge would shrink to reading the same YAML for agent/babysit config only.

## Smug research (2026-04-30)

**Unknown YAML keys: silently ignored.** smug uses gopkg.in/yaml.v2 without
DisallowUnknownFields, so extra fields at pane level are a no-op. Safe to embed nudge
config as a `nudge:` block inside each pane entry.

Smug pane schema (the only fields smug uses):
  root: optional working dir
  type: horizontal|vertical split
  commands: list of shell commands to run

Pane identity: smug assigns tmux pane IDs at creation time (positional). After session
exists, nudge can resolve targets via `tmux list-panes -t <session> -F '#{pane_index} #{pane_id}'`.

Session handling: smug attaches to existing sessions rather than recreating them.

No YAML anchors or includes — only $VAR substitution.

## Concrete mapping

Current nudge config (swarm/tiy.yaml excerpt):

```yaml
session:
  name: tiy
layout:
  type: grid
  rows: 1
  cols: 3
panes:
  - pane: "0.0"
    title: codex
    agent: codex
    command: "codex --dangerously-bypass-approvals-and-sandbox"
    monitor: true
    babysit:
      enabled: true
      interval_secs: 600
      ...
```

Equivalent smug YAML with nudge fields interlaced:

```yaml
name: tiy
windows:
  - name: grid
    layout: even-horizontal
    panes:
      - commands:
          - "codex --dangerously-bypass-approvals-and-sandbox"
        nudge:
          title: codex
          agent: codex
          monitor: true
          babysit:
            enabled: true
            interval_secs: 600
            clear_every: 6
            long_prompt_file: "prompts/worker_long.md"
            short_prompt_file: "prompts/worker_short.txt"
      - commands:
          - "claude --dangerously-skip-permissions"
        nudge:
          title: claude
          agent: claude
          monitor: true
          babysit:
            enabled: false
            ...
      - commands:
          - "gemini -y"
        nudge:
          title: gemini
          agent: gemini
          monitor: true
          babysit:
            enabled: true
            ...
```

smug reads `commands`, `layout`, `name` — ignores `nudge:` entirely.
nudge reads `nudge:` blocks and resolves pane targets by position after smug has run.

## Layout mapping

nudge grid (rows x cols) → smug layout names:
  1 row, N cols  → even-horizontal
  N rows, 1 col  → even-vertical
  N x N grid     → tiled
  other          → tiled (approximate)

## What nudge would keep
- monitor.c / state detection
- babysit loop
- tmux-send (paste-buffer delivery)
- usage probing
- YAML parsing (nudge: blocks only)
- pane target resolution by index

## What nudge would drop
- session/window/pane creation (apply, ensure_grid, ensure_command in topology.py)
- layout config (rows, cols, grid type)
- most of swarm/topology.py

## What changes for the user
- `smug start tiy.yaml` instead of `python swarm/cli.py apply tiy.yaml`
- `python swarm/cli.py babysit apply tiy.yaml` stays the same (reads nudge: blocks)
- smug is a single Go binary, no runtime deps

## Open questions
- Does smug guarantee pane creation order matches YAML order? (needed for positional mapping)
- Title/rename: smug has no pane title support — nudge would still need to set titles after start
- Startup sequencing: nudge currently waits/retries; smug just fires commands
<!-- SECTION:DESCRIPTION:END -->
