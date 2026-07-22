---
id: TASK-45
title: 'tasks: honor backlog dependencies for claim/chase (blocked + review)'
status: Done
assignee:
  - 'aiswarm:nudge:0.1'
created_date: '2026-07-22 21:25'
updated_date: '2026-07-22 21:35'
labels: []
dependencies: []
priority: medium
type: enhancement
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Backlog already supports --depends-on / dependencies. Use them so agents can pause work without fighting chase.

Goals:
- **Block claim/chase** while any dependency is not Done (configurable complete set).
- **Agent protocol:** if stuck waiting, create/link a blocker or review task as a dependency of the current task; dispatcher stops chasing the parent until deps complete. Same pattern for peer review: parent depends on review task.
- **Resume:** when all deps Done, claim/chase as normal (or re-chase assigned owner).

Non-goals v1:
- Full DAG scheduler / critical path.
- Auto-creating review tasks (agent or human does that).

Pathologies to decide explicitly:
1. **Cycles** — refuse claim/chase; log; do not infinite-loop.
2. **Child Done but parent deps incomplete** — parent stays blocked (Done of unrelated tasks irrelevant).
3. **Dep Done but parent still In Progress idle** — normal chase again.
4. **Missing/deleted dep id** — treat as blocking error or ignore? Prefer block + note once.
5. **Self-dep** — reject.

Implementation sketch: view_task_json already has dependencies[]; list/view deps status; gate _claim_new_onto_free and chase_assigned. Optional status field or local reason blocked_on=[...].
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Do not claim a task whose dependencies are not all Done (or configured complete statuses)
- [x] #2 Do not chase an assigned task while any open dependency remains; treat as blocked (log once, not spam)
- [x] #3 Document agent pattern: add dep (blocker or review task) via backlog to pause chase; clear/complete deps to resume
- [x] #4 Define policy for pathological graphs: cycle detection; Done child with unfinished deps; missing dep ids
- [x] #5 Minimal tests: blocked claim/chase; unblocked after dep Done
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Add a dependency gate in tasksctl that fetches task dependency statuses, detects cycles/self-deps/missing ids, and treats only complete statuses as runnable.\n2. Use the gate to skip claim candidates and block chase prompts once per assignment while dependencies are open.\n3. Update agent-facing instructions to describe the blocker/review dependency pattern and the unblock/resume rule.\n4. Add regression tests for blocked claim/chase and the unblock-after-Done case, then verify with pytest.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Claimed by aiswarm tasks dispatcher for pane 0.1 (session nudge).

Implemented dependency gating in tasksctl: tasks are runnable only when their dependencies are complete (default set: Done; helper also respects a tasks.complete_statuses attribute if present). Claiming now skips blocked candidates; chase writes one blocked record per assignment and suppresses repeat warnings until the dependency state changes. Policy: self-deps, cycles, and missing dependency ids are treated as blocked errors. Documented the backlog dependency pattern in README and aiswarm instructions/tasks. Verified with pytest -q test_swarm.py (63 passed).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Added dependency-aware dispatch gating for tasks claim/chase. Blocked tasks now stay out of claim rotation until dependencies are complete, chase logs once per blocked state, and cycle/missing/self-dependency cases are treated as blocked errors. Documented the backlog dependency pause/resume pattern in README and aiswarm instructions, and verified the behavior with pytest -q test_swarm.py (63 passed).
<!-- SECTION:FINAL_SUMMARY:END -->
