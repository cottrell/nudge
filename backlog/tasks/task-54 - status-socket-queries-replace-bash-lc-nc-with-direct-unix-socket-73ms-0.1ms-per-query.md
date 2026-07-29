---
id: TASK-54
title: >-
  status/socket queries: replace bash -lc + nc with direct unix socket (73ms ->
  0.1ms per query)
status: Done
assignee:
  - '@aiswarm:nudge:0.1'
created_date: '2026-07-29 15:48'
updated_date: '2026-07-29 15:55'
labels: []
dependencies: []
priority: high
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
topology._query_monitor and topology.socket_ready shell out to `bash -lc "printf status | nc -U <sock>"` per monitored pane. Measured (Fable 5 review 2026-07-29): 73.6ms per query vs 0.1ms for a direct Python AF_UNIX socket — ~700x slower, and -l loads the login profile every call. `aiswarm status -w` at the default 1s interval with N monitored panes burns N*74ms of subprocess+login-shell churn per refresh, plus this also runs during start (ensure_monitor -> socket_ready). The codebase already has two correct direct-socket implementations: tasksctl.query_monitor_state and pane_worker._query_socket. Consolidate on one shared helper in swarm/common.py (monitor_socket_path already lives there) and delete the nc path. Also removes the runtime dependency on nc.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 topology no longer invokes bash or nc for monitor queries; status and socket_ready use a shared python socket helper
- [x] #2 one shared query helper used by topology, tasksctl and pane_worker (no duplicated socket code / hardcoded /tmp path f-strings)
- [x] #3 existing status tests pass; a test covers the unreachable-socket fallback state
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Add a shared Unix socket query helper in swarm/common.py built on AF_UNIX sockets and JSON parsing.\n2. Switch topology.socket_ready and topology._query_monitor to the shared helper and remove bash/nc subprocess calls.\n3. Update tasksctl and pane_worker to use the same helper and run status tests, including unreachable-socket fallback coverage.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Claimed by aiswarm tasks dispatcher for pane 0.1 (session nudge).

Implemented shared AF_UNIX monitor query helpers in swarm/common.py and redirected topology, tasksctl, and pane_worker to them. Replaced topology bash/nc subprocess queries with direct socket calls. Added a status fallback test for unreachable sockets and verified the affected status tests with pytest -p no:lazy-fixture.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Replaced topology's bash -lc + nc monitor queries with a shared AF_UNIX helper in swarm/common.py, and updated topology, tasksctl, and pane_worker to use it. Verified with pytest -q -p no:lazy-fixture test_swarm.py -k status (17 passed) plus focused monitor-state tests including the new unreachable-socket fallback check.
<!-- SECTION:FINAL_SUMMARY:END -->
