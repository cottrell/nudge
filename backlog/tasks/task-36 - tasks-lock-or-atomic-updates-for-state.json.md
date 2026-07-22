---
id: TASK-36
title: 'tasks: lock or atomic updates for state.json'
status: To Do
assignee: []
created_date: '2026-07-22 13:55'
labels: []
dependencies: []
priority: high
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Risk: /tmp/nudge-swarm/<session>/tasks/state.json has no file lock. Concurrent writers (double start, once+loop, crash mid-write) can corrupt assignments.

Fix: flock or atomic write (write temp + rename) on load/save_state.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 save_state is atomic
- [ ] #2 concurrent update does not truncate/corrupt JSON
<!-- AC:END -->
