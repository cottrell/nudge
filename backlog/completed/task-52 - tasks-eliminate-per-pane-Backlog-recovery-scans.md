---
id: TASK-52
title: 'tasks: eliminate per-pane Backlog recovery scans'
status: Done
assignee:
  - '@codex'
created_date: '2026-07-29 15:35'
updated_date: '2026-07-29 15:39'
labels: []
dependencies: []
modified_files:
  - swarm/tasksctl.py
  - test_swarm.py
priority: high
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Assignment recovery currently nests Backlog status/detail queries inside the pane loop, multiplying identical subprocess work and making aiswarm tasks once take roughly 20 seconds on a six-pane swarm. Query each ingest status once, load each returned task detail at most once, and map assignments to panes in memory. Dry-run recovery must not persist recovered state.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Recovery runs each configured ingest status list query once per dispatcher pass, independent of pane count
- [x] #2 Each listed task detail is fetched at most once during recovery
- [x] #3 Recovered assignments retain existing precedence and assignee matching behavior
- [x] #4 Dry-run does not write recovered assignment state
- [x] #5 Real dag-patterns dry-run benchmark is materially faster than the approximately 20-second baseline
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Invert recovery to scan statuses/tasks once and build an assignee index. 2. Thread dry-run into recovery so reconstructed state remains in memory only. 3. Replace the existing recovery tests with query-count, precedence, and no-write regression coverage. 4. Run the full suite and benchmark dag-patterns before finalizing and committing.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Inverted recovery into a single ingest scan and shared task-detail cache, then reused that same snapshot for candidate selection in both normal and dry-run dispatch. Real dag-patterns dry-run improved from 18.96s/20 Backlog calls (14 list calls) to 4.42s; profiling now shows exactly two list calls, one per ingest status. Full make test passes: 28 monitor tests and 81 swarm tests.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Replaced per-pane Backlog recovery scans with one shared per-pass task snapshot and detail cache used by recovery and candidate selection in normal and dry-run dispatch. Dry-run recovery no longer persists reconstructed state. Verified by query-count and lifecycle regression tests, make test (28 monitor, 81 swarm), and a dag-patterns benchmark improving 18.96s to 4.42s.
<!-- SECTION:FINAL_SUMMARY:END -->
