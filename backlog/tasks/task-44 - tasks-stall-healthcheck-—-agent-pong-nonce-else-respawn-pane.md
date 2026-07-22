---
id: TASK-44
title: 'tasks: stall healthcheck — agent pong nonce, else respawn pane'
status: Done
assignee:
  - 'aiswarm:nudge:0.0'
created_date: '2026-07-22 21:24'
updated_date: '2026-07-22 21:28'
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
- [x] #1 After N idle chases (or age) with open assignment, send durable-log HEALTHCHECK with nonce asking the agent to pong
- [x] #2 Only treat agent-originated reply containing nonce as alive; ignore consumer delivery acks (0.N:ack)
- [x] #3 On timeout with no pong: tmux respawn-pane -k for that pane only using configured shell_command; re-attach monitor if needed; chase again
- [x] #4 Restart budget per pane/assignment (e.g. 1-2); then stop or unassign/peer path
- [x] #5 Tests for probe state machine + no false dead from delivery-only ack
- [x] #6 Docs: stall→probe→respawn; not continuous heartbeat; not error-string scraping
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Add task-healthcheck configuration defaults and expose them in effective config.
2. Implement persisted per-assignment chase/probe/restart state: durable nonce probe, explicit pong check that excludes consumer acks, bounded pane-only respawn plus monitor rewire and queued chase.
3. Add a small healthcheck pong CLI endpoint for agents, focused state-machine tests, and concise task-dispatch documentation.
4. Run the swarm suite, record objective AC evidence, and finalize TASK-44.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Claimed by aiswarm tasks dispatcher for pane 0.0 (session nudge).

Implemented persisted stall healthchecks with nonce probes, explicit agent-pong events, bounded pane-only respawn plus monitor reattach and queued chase. Added state-machine tests, including consumer ack exclusion. Validation passed: make test-swarm (61 passed); rendered aiswarm instructions tasks reviewed.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Added nonce-based stalled-pane healthchecks: explicit agent pong only, bounded pane-local respawn with monitor rewire and chase, plus docs and tests. Verified with make test-swarm (61 passed) and rendered task instructions.
<!-- SECTION:FINAL_SUMMARY:END -->
