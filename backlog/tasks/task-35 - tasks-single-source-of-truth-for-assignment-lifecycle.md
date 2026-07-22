---
id: TASK-35
title: 'tasks: single source of truth for assignment lifecycle'
status: To Do
assignee: []
created_date: '2026-07-22 13:55'
labels: []
dependencies: []
priority: medium
type: enhancement
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Risk: reconcile_assignments and chase_assigned both view backlog, detect Done/not found, and clear state. Easy to diverge.

Refactor: one helper e.g. assignment_status(cfg, pane, task_id) → open|done|missing|unassigned used by both paths.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 one function owns Done/missing/unassigned clearing
- [ ] #2 reconcile and chase call it; no duplicated JSON status parsing
<!-- AC:END -->
