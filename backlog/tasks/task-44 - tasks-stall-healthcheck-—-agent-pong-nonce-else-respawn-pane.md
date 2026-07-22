---
id: TASK-44
title: 'tasks: stall healthcheck — agent pong nonce, else respawn pane'
status: To Do
assignee: []
created_date: '2026-07-22 21:24'
labels: []
dependencies: []
priority: high
type: enhancement
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
When an assigned pane stays idle and is chased but never progresses (e.g. agent TUI shows fatal error but process still up, monitor still idle), dispatcher currently only re-chases forever.

Design (agreed):
1. Do NOT scrape provider-specific error strings.
2. After stall (N idle chases / time with open assignment), send a rare durable-log probe asking the **agent** to ack with a nonce (e.g. aiswarm send / log reply "pong <nonce>").
3. Existing consumer log_ack after tmux-send only proves injection — insufficient for liveness (observed on dead agy pane).
4. No pong within timeout → restart **that pane only** via `tmux respawn-pane -k -t session:pane -- <shell_command from config>`, re-wire monitor, then chase. Cap restarts.
5. Optional later: unassign / peer checkup after budget exhausted (TASK-39 related).

Out of scope v1: provider session resume/fork; continuous heartbeat (token cost); full peer agent diagnosis.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 After N idle chases (or age) with open assignment, send durable-log HEALTHCHECK with nonce asking the agent to pong
- [ ] #2 Only treat agent-originated reply containing nonce as alive; ignore consumer delivery acks (0.N:ack)
- [ ] #3 On timeout with no pong: tmux respawn-pane -k for that pane only using configured shell_command; re-attach monitor if needed; chase again
- [ ] #4 Restart budget per pane/assignment (e.g. 1-2); then stop or unassign/peer path
- [ ] #5 Tests for probe state machine + no false dead from delivery-only ack
- [ ] #6 Docs: stall→probe→respawn; not continuous heartbeat; not error-string scraping
<!-- AC:END -->
