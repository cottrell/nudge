---
id: TASK-28
title: Add aiswarm bare-command workflow help and aiswarm instructions guides
status: To Do
assignee: []
created_date: '2026-07-16 09:36'
updated_date: '2026-07-16 09:36'
labels: []
dependencies:
  - TASK-27
references:
  - task-27
documentation:
  - doc-2
type: enhancement
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Mirror Backlog.md's agent-facing CLI briefing pattern for aiswarm.

Today bare `aiswarm` errors with argparse; help is only subcommands. Agent briefing is scattered across AGENTS.md AISWARM block, self-awareness.txt, README, and backlog docs.

Goal: make the CLI the durable place agents (and humans) go first for workflow procedure — without requiring default-config discovery or layout moves (those are separate).

Out of scope: cwd default config resolution, `.aiswarm/` harness dir, renaming nudgeswarm/ or package paths.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Bare aiswarm (no subcommand) prints a short common-workflow cheat sheet, not an argparse error
- [ ] #2 aiswarm instructions lists available guides (index)
- [ ] #3 aiswarm instructions overview covers when/how to use swarm: start/stop, send vs backlog vs attach, babysit vs tasks, do-not raw send-keys
- [ ] #4 At least one deeper guide exists (e.g. handoff and/or tasks); content can start from backlog doc-2 / README
- [ ] #5 AGENTS.md AISWARM block can stay short or point at aiswarm instructions (no requirement to delete self-awareness runtime map)
- [ ] #6 Command help (aiswarm <cmd> --help) remains for flags; instructions are workflow, not flag docs
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Add no-arg / instructions subcommand surface in swarm/cli.py (backlog-like index + named guides).
2. Author concise guide text (overview + handoff/tasks as needed); prefer short agent-token-friendly pages.
3. Wire tests for bare aiswarm and instructions listing/content smoke.
4. Optionally trim AGENTS AISWARM block to point at aiswarm instructions.
5. Do not implement default config discovery or .aiswarm layout in this task.
<!-- SECTION:PLAN:END -->
