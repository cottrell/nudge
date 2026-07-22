---
id: TASK-39
title: 'tasks: peer checkup when assigned pane is dead/quota/corrupt'
status: Done
assignee:
  - 'aiswarm:nudge:0.4'
created_date: '2026-07-22 13:55'
updated_date: '2026-07-22 21:16'
labels: []
dependencies: []
documentation:
  - doc-3
priority: high
type: spike
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Design: if an assignment stalls (pane not progressing: repeated chases with no Done, monitor rate_limited/working stuck, process dead, or agent unresponsive), ask another free pane to check up on that assignment/pane rather than only re-prompting the broken agent.

Note: monitor/babysit already know rate_limited in some paths (babysit waits on rate_limited). tasks dispatcher currently only uses idle/unknown/working via query_monitor_state — confirm and wire rate_limited if present.

Conditions TBD: N failed chases, age of claimed_at, pane PID dead, state rate_limited for T, etc. Checkup agent reads backlog task + maybe capture of stuck pane; may reassign, unblock, or mark blocked.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 design note: when to trigger peer checkup vs chase
- [x] #2 list usable signals (idle, rate_limited, pid, chase count)
- [x] #3 prototype or explicit non-goals if deferred
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Research current state of chase, monitor, and babysitter.
2. Define conditions for peer checkup vs chase.
3. List all usable signals.
4. Propose a prototype implementation design.
5. Write everything in a new Design Document under backlog/docs/ and link it to the task.
6. Finalize and review the task.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Claimed by aiswarm tasks dispatcher for pane 0.4 (session nudge).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Created Design Document doc-3 outlining when to trigger peer checkups vs chase, listing all usable signals, and proposing a prototype checkup workflow and non-goals. Document doc-3 has been linked to the task.
<!-- SECTION:FINAL_SUMMARY:END -->
