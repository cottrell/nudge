---
id: TASK-2
title: 'Use tmuxp as session/grid layer, nudge handles only agent logic'
status: Done
assignee: []
created_date: '2026-04-30 09:11'
updated_date: '2026-06-18 09:46'
labels: []
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Replace nudge's custom session/pane creation with tmuxp (https://tmuxp.git-pull.com/).
tmuxp is Python, widely used, and exposes a flat uniform pane list — all panes look
identical in the YAML regardless of their position. nudge embeds its config in `nudge:`
blocks alongside each pane entry; tmuxp ignores unknown keys.

## YAML format

```yaml
session_name: tiy
windows:
  - window_name: grid
    layout: tiled
    panes:
      - shell_command: "codex --dangerously-bypass-approvals-and-sandbox"
        nudge:
          title: codex
          agent: codex
          monitor: true
          babysit:
            enabled: true
            interval_secs: 600
            clear_every: 6
            long_prompt_file: prompts/worker_long.md
            short_prompt_file: prompts/worker_short.txt

      - shell_command: "claude --dangerously-skip-permissions"
        nudge:
          title: claude
          agent: claude
          monitor: true
          babysit:
            enabled: false

      - shell_command: "gemini -y"
        nudge:
          title: gemini
          agent: gemini
          monitor: true
          babysit:
            enabled: true
            interval_secs: 600
            clear_every: 6
            long_prompt_file: prompts/worker_long.md
            short_prompt_file: prompts/worker_short.txt
```

tmuxp reads `session_name`, `window_name`, `layout`, `shell_command` — ignores `nudge:`.
nudge reads `nudge:` blocks and resolves pane targets by position after tmuxp has run.

## Layout mapping

nudge grid (rows x cols) → tmuxp layout names (standard tmux layout names):
  1 row, N cols  → even-horizontal
  N rows, 1 col  → even-vertical
  N x N grid     → tiled
  other          → tiled

## What nudge would keep
- monitor.c / state detection
- babysit loop
- tmux-send (paste-buffer delivery)
- usage probing
- YAML parsing (nudge: blocks only)
- pane target resolution by index
- pane title-setting (tmuxp has no pane title support)

## What nudge would drop
- session/window/pane creation (apply, ensure_grid, ensure_command in topology.py)
- layout config (rows, cols, grid type)
- most of swarm/topology.py

## What changes for the user
- `tmuxp load tiy.yaml` instead of `python swarm/cli.py apply tiy.yaml`
- `python swarm/cli.py babysit apply tiy.yaml` stays the same (reads nudge: blocks)

## Open questions
- Does tmuxp silently ignore unknown keys? Needs verification before building the reader.
- Startup sequencing: nudge currently waits/retries on socket readiness; tmuxp just fires commands.
<!-- SECTION:DESCRIPTION:END -->
