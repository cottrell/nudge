---
id: TASK-57
title: >-
  broadcast --via-log: reported recipients do not match actual cursor fan-out
  delivery
status: To Do
assignee: []
created_date: '2026-07-29 15:49'
labels: []
dependencies: []
priority: medium
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
topology.broadcast with via_log prints "log-broadcast to <target>" for agent panes (filtered by pane.agent and monitor unless -A), but log_broadcast writes ONE __broadcast__ event and actual delivery is per-pane broadcast-cursor fan-out in pane_worker._drain_comms, which runs for every pane the session worker services (all comms-enabled panes, including shell/log panes with comms on). So: (a) the printed recipient list can both under- and over-state real delivery; (b) --include-nonmonitored has no effect on the log path. Decide the intended semantics: either make _drain_comms filter broadcasts by pane agent/monitor flags recorded in the spec, or make the CLI print the true fan-out set. Also log_send/log_broadcast do not validate the recipient pane exists in the config — a typo like `aiswarm send 0.9 msg` queues an event nobody will ever drain, silently.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 printed broadcast recipients equal the panes that will actually receive the event via cursor fan-out
- [ ] #2 documented (or implemented) behaviour for --include-nonmonitored under --via-log
- [ ] #3 aiswarm send to a pane not present in the config warns (event may still be logged)
<!-- AC:END -->
