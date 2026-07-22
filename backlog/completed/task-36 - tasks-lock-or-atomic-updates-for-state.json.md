---
id: TASK-36
title: 'tasks: lock or atomic updates for state.json'
status: Done
assignee:
  - 'aiswarm:nudge:0.2'
created_date: '2026-07-22 13:55'
updated_date: '2026-07-22 13:59'
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
- [x] #1 save_state is atomic
- [x] #2 concurrent update does not truncate/corrupt JSON
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
save_state now writes to a pid-suffixed temp file in the same dir and os.replace()s it into place, so a crash mid-write leaves the old state.json intact (no truncation/corruption). Rename is atomic on POSIX for same-filesystem temp+target. Added test_save_state_atomic_rename_no_partial_writes in test_swarm.py.
<!-- SECTION:NOTES:END -->
