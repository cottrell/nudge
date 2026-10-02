---
id: TASK-83
title: 'Consider hierarchical CLI organization for aiswarm (think only, no commitment)'
status: To Do
assignee: []
created_date: '2026-10-02 09:46'
labels:
  - cli
  - parked
dependencies: []
priority: low
type: spike
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
aiswarm has ~25 flat top-level commands. Evaluate whether grouping into noun-verb subcommands helps or just costs. THINK/DECIDE ONLY; do not implement unless the decision is yes. Current flat list: instructions, this, sessions, swarms, init, start, status, broadcast, stop, worker, clear-comms, log, send, healthcheck, clear, av-usage, quota, quota-debug (alias quota_debug), help (alias models), capture, wait, babysit, tasks. Already grouped: babysit, tasks, worker (start|stop|status style).

Candidate shape (strawman):
- lifecycle: start, stop, status, init, this, sessions, swarms
- pane/comms: send, broadcast (send --all?), clear, log, clear-comms -> 'comms log|clear', healthcheck
- pane inspection: capture, wait -> 'pane capture|wait <id>' (also a natural home for swarm:pane qualified addressing)
- usage: quota, quota-debug, av-usage -> 'usage quota|debug|av'
- agents: help/models -> 'models', instructions
- keep babysit, tasks, worker as-is

Considerations: (+) discoverability, shorter --help, consistent places for shared options like qualified swarm:pane and -c config; (+) fewer odd names (clear = send /clear; clear-comms vs clear confusion). (-) breaks muscle memory, agent prompts, AGENTS.md/instructions, README and tests that spell current commands; (-) longer to type for the hot paths (send, status, wait) - keep top-level aliases for hot commands; (-) argparse subparser nesting boilerplate, though cli.py is already large. Middle path: keep every flat command as an alias, only regroup in help output (argparse metavar/help sections) with no behavior change.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Write down a recommendation: do nothing / regroup help only / full hierarchy with flat aliases
- [ ] #2 If yes: list which commands move, which stay top-level hot aliases, and the deprecation story for agent prompts and docs
- [ ] #3 Estimate blast radius: grep instructions.py, README, AGENTS.md, tests for spelled commands
<!-- AC:END -->
