---
id: TASK-49
title: >-
  session_worker must port pane_worker babysit/comms semantics (not thin
  rewrite)
status: Done
assignee:
  - 'aiswarm:nudge:0.0'
created_date: '2026-07-27 12:50'
updated_date: '2026-07-27 12:54'
labels:
  - swarm
  - babysit
  - process-model
dependencies: []
priority: high
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Follow-up to TASK-48 b077450. Process model OK (one session_worker per swarm). session_worker.py thin-rewrote the per-pane loop and dropped EMA/quota/pacing and other pane_worker fidelity. Fix by porting/sharing pane_worker tick path; multiplexer only at session_worker layer. Old live swarms out of scope. Human/grok feedback sent via aiswarm send 0.0 id=52. When done: aiswarm send 0.5 for review.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Per-pane tick shares pane_worker code path (extract if needed); no divergent thin loop semantics
- [x] #2 EMA/quota fields from YAML/spec actually affect scheduling in session_worker
- [x] #3 Still one Python PID per swarm; tasks group unchanged
- [x] #4 make test-swarm passes
- [x] #5 aiswarm send 0.5 when done for review
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Extract PaneWorker.tick from pane_worker.py with full comms, startup, clear/force, quota and EMA behavior. 2. Make session_worker a thin multiplexer of those shared objects while retaining task scheduling. 3. Verify EMA spec affects wait, run make test, update docs, and notify pane 0.5.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented shared PaneWorker state machine and changed session_worker to load specs then call it; retained one process and enabled.json task scheduling. Restoring quota cache refresh and adding EMA scheduling coverage.

Verification: session_worker imports and invokes pane_worker.PaneWorker directly; test asserts identity and proves EMA min/max spec values change the next wait. make test passed: 28 monitor + 73 swarm tests. The supervisor retains one PID and enabled.json tasks scheduling.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Replaced the thin supervisor loop with shared PaneWorker.tick semantics: comms startup drain, dynamic specs, clear/force handling, quota cache refresh/probes, and EMA pacing. session_worker now only multiplexes PaneWorker objects and tasks. Verified by make test (28 monitor + 73 swarm tests), including shared-code identity and EMA wait wiring.
<!-- SECTION:FINAL_SUMMARY:END -->
