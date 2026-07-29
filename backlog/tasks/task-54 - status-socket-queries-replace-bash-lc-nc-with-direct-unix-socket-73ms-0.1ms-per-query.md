---
id: TASK-54
title: >-
  status/socket queries: replace bash -lc + nc with direct unix socket (73ms ->
  0.1ms per query)
status: To Do
assignee: []
created_date: '2026-07-29 15:48'
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
- [ ] #1 topology no longer invokes bash or nc for monitor queries; status and socket_ready use a shared python socket helper
- [ ] #2 one shared query helper used by topology, tasksctl and pane_worker (no duplicated socket code / hardcoded /tmp path f-strings)
- [ ] #3 existing status tests pass; a test covers the unreachable-socket fallback state
<!-- AC:END -->
