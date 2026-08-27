---
id: TASK-70
title: Evaluate machine-wide nudge supervisor versus per-swarm workers
status: To Do
assignee: []
created_date: '2026-08-27 10:10'
labels:
  - architecture
  - swarm
  - process-model
dependencies:
  - TASK-67
references:
  - backlog/docs/doc-4 - Session-supervisor-process-model.md
priority: medium
type: spike
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Evaluate whether nudge should retain one Python session worker per swarm or introduce one machine-wide supervisor that discovers and routes across swarms. Preserve the existing distinction between cheap per-pane C activity monitors and Python orchestration. Coordinate with TASK-67, which covers cross-swarm discovery, but focus this task on lifecycle, process ownership, startup automation, and failure domains.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Current process counts and resource use are measured for representative one-, two-, and many-swarm scenarios
- [ ] #2 Options compare the current per-swarm session worker, a machine-wide registry/control daemon with per-swarm workers, and a single machine-wide worker
- [ ] #3 The analysis covers startup/login integration, crash isolation, upgrades, stale runtime cleanup, routing identity, concurrent configuration changes, and observability
- [ ] #4 The recommendation states quantitative or operational thresholds that would justify consolidation
- [ ] #5 Any proposed change remains compatible with explicit per-project aiswarm commands and does not require infrastructure beyond the desktop without approval
<!-- AC:END -->
