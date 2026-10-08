---
id: TASK-51
title: 'status: show tasks group and heartbeat countdown'
status: Done
assignee:
  - '@codex'
created_date: '2026-07-29 14:58'
updated_date: '2026-07-29 15:01'
labels: []
dependencies: []
modified_files:
  - session_worker.py
  - swarm/common.py
  - swarm/tasksctl.py
  - swarm/topology.py
  - test_swarm.py
priority: medium
type: enhancement
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Add task-dispatch visibility to aiswarm status and watch output alongside the existing babysit fields. Nudge HB remains the babysit idle-nudge countdown. Tasks should report per-pane participation and global group liveness; Tasks HB should show time until the next dispatcher pass, which performs claims and due task chases.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Full status and watch output include Tasks and Tasks HB columns
- [x] #2 Tasks distinguishes on, off, stopped, and stale states consistently with worker/group state
- [x] #3 Tasks HB counts down to the next dispatcher pass and is separate from babysit's Nudge HB
- [x] #4 Tests cover enabled and disabled task panes plus heartbeat rendering
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Persist the session worker's next task-dispatch timestamp atomically. 2. Read global task-group enablement, worker liveness, per-pane opt-in, and the timestamp in topology status. 3. Add Tasks and Tasks HB to the full/watch table while retaining Nudge HB exclusively for babysit. 4. Add state/countdown tests, run the full suite, finalize, and commit.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Added atomic worker_state.json heartbeat timestamps, per-pane Tasks state, and Tasks HB countdown columns to full/watch status. Nudge HB remains explicitly babysit-only. Full make test passes (28 monitor, 80 swarm); live dag-patterns rendering shows Tasks=on and Tasks HB=? until its old worker is restarted on the new code.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Added Tasks and Tasks HB to full aiswarm status/watch output. The session worker atomically publishes its next dispatcher pass; status distinguishes per-pane on/off and worker stopped/stale states while keeping Nudge HB babysit-only. Verified with state/countdown regression tests, live dag-patterns rendering, and make test (28 monitor, 80 swarm).
<!-- SECTION:FINAL_SUMMARY:END -->
