---
id: TASK-37
title: 'tasks: rebuild local assignments from backlog assignees on start'
status: To Do
assignee: []
created_date: '2026-07-22 13:55'
labels: []
dependencies: []
priority: high
type: enhancement
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Risk: local state.json is sole memory of pane↔task. Dispatcher restart or deleted state forgets claims; backlog still has aiswarm:session:pane assignees but chase/claim logic will not pick them up as open work (unassigned_only).

Fix: on start or each pass, scan In Progress (or ingest+assigned) for assignee matching claim prefix and rehydrate assignments.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 restart with empty state.json recovers aiswarm:session:pane claims from backlog
- [ ] #2 does not double-claim free To Do already owned by a pane
<!-- AC:END -->
