---
id: TASK-79
title: Pane categories (heavy/light/...) as send and task targets
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-01 09:01'
updated_date: '2026-10-01 09:04'
labels:
  - routing
  - config
  - dispatcher
dependencies: []
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Today a message goes to one named pane, to 'any' (TASK-66), or to all (broadcast); tasks go to any free pane or a preassigned one (TASK-61). Panes are not equal (e.g. 'codex heavy' vs 'codex light' vs 'claude heavy' in .aiswarm/config.yaml, where the class lives only in the free-text title). Want named categories declared per pane in config so a producer can target a class of pane instead of a specific pane or any pane. A pane may carry several categories.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Pane config accepts a list of categories (nudge.categories) validated at load; names may not be 'any', 'mcp', or collide with a pane id
- [ ] #2 aiswarm send <category> MSG queues durably and is delivered to exactly one idle pane in that category with no active task assignment
- [ ] #3 A message for a category with no live panes stays queued and the CLI warns
- [ ] #4 Backlog tasks can request a category and the dispatcher only offers them to panes carrying it; preassigned, dependency, idle and max-inflight gates still apply
- [ ] #5 aiswarm status and log show categories and per-category pending queue
- [ ] #6 Tests cover multi-category panes, single delivery, empty category, and name collisions; README and instructions updated
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented: PaneSpec.categories (validated), log_any/claim_any category filter via meta.category (same __any__ queue), CLI send <category>, runtime.json + babysit spec carry categories, dispatcher cat:<name> task labels (all required), status shows categories, README/instructions, 4 tests. Not done: explicit warn for category with no live panes (queues silently); per-category pending view in log/status.
<!-- SECTION:NOTES:END -->
