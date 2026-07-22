---
id: TASK-39
title: 'tasks: peer checkup when assigned pane is dead/quota/corrupt'
status: To Do
assignee: []
created_date: '2026-07-22 13:55'
labels: []
dependencies: []
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
- [ ] #1 design note: when to trigger peer checkup vs chase
- [ ] #2 list usable signals (idle, rate_limited, pid, chase count)
- [ ] #3 prototype or explicit non-goals if deferred
<!-- AC:END -->
