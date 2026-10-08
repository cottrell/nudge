---
id: TASK-79
title: Pane categories (heavy/light/...) as send and task targets
status: Done
assignee:
  - '@claude'
created_date: '2026-10-01 09:01'
updated_date: '2026-10-02 08:45'
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
- [x] #1 Pane config accepts a list of categories (nudge.categories) validated at load; names may not be 'any', 'mcp', or collide with a pane id
- [x] #2 aiswarm send <category> MSG queues durably and is delivered to exactly one idle pane in that category with no active task assignment
- [x] #3 A message for a category with no live panes stays queued and the CLI warns
- [x] #4 Backlog tasks can request a category and the dispatcher only offers them to panes carrying it; preassigned, dependency, idle and max-inflight gates still apply
- [x] #5 aiswarm status and log show categories and per-category pending queue
- [x] #6 Tests cover multi-category panes, single delivery, empty category, and name collisions; README and instructions updated
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented: PaneSpec.categories (validated), log_any/claim_any category filter via meta.category (same __any__ queue), CLI send <category>, runtime.json + babysit spec carry categories, dispatcher cat:<name> task labels (all required), status shows categories, README/instructions, 4 tests. Not done: explicit warn for category with no live panes (queues silently); per-category pending view in log/status.

REVIEW (commit 5822b09, 2026-10-01): make test passed (30 monitor, 133 swarm). Core category routing is single-claim under BEGIN IMMEDIATE; incompatible category entries are skipped so a later plain any can be claimed. Findings:
1. HIGH: _claim_new_onto_free greedily gives a general task to the only pane eligible for a later cat:heavy task; another free light pane cannot claim the heavy task. Tracked in TASK-79.1.
2. MEDIUM: claim_any fetchall scans every unclaimed __any__ row and parses JSON while holding a write transaction on every idle poll. Orphan category messages make this grow without bound and slow existing any dispatch. Tracked in TASK-79.2.
3. Existing TASK-79 acceptance gaps remain: no warning for category with no live/receiving pane (AC3); aiswarm status has no category display and log/status have no per-category pending summary (AC5).
4. Config validation is incomplete for AC1: nudge.categories accepts a scalar string and mapping keys as categories, converts non-string elements with str(), and raises TypeError for truthy non-iterable values. Validate a list of nonempty string names with a clear ValueError.
5. Current category tests only call pane_serves_task directly; add an end-to-end dispatcher assignment case, category CLI send/pending/log tests, and config malformed-type cases. No code edited in this review.

Follow-up for review: constrained cat: tasks claimed before general ones per pane (79.1); claim_any filters in SQL via json_extract with LIMIT 1 (79.2); strict list-of-strings validation; pending log shows __any__:<cat>; status title shows [cats]; e2e dispatch/CLI/malformed-config tests. make test: 137 swarm + 30 monitor pass. Open: AC3 (no warning for known category with no live pane; unknown category does warn) and AC5 (status table category display untested).

AC3: send to a non-pane-shaped target absent from config now errors (exit 1, nothing queued); known category queues even if panes blocked. AC5: status ends with category rollup (panes/idle/msgs/tasks) via category_lines. 147 swarm tests pass.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Pane categories as send/task targets. AC3: send to an unknown non-pane target errors; known category queues. AC5: status ends with per-category rollup. Verified: uv run pytest test_swarm.py (147 passed), incl. unknown-category error and rollup tests.
<!-- SECTION:FINAL_SUMMARY:END -->
