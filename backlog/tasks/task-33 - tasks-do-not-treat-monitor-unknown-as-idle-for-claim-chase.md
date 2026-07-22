---
id: TASK-33
title: 'tasks: do not treat monitor unknown as idle for claim/chase'
status: To Do
assignee: []
created_date: '2026-07-22 13:55'
labels: []
dependencies: []
priority: high
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Risk: pane_ready_for_prompt / is_pane_free treat monitor state unknown like idle. If socket missing or probe fails, dispatcher may claim or chase when the pane is not actually free.

Fix: only treat idle as ready for new claim and chase (or require explicit policy). Log unknown separately. Tests for unknown → no claim/chase when require_idle.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 unknown is not treated as idle when require_idle true
- [ ] #2 unit/integration coverage for missing socket
<!-- AC:END -->
