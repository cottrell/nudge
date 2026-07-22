---
id: TASK-45
title: 'tasks: honor backlog dependencies for claim/chase (blocked + review)'
status: To Do
assignee: []
created_date: '2026-07-22 21:25'
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
- [ ] #1 Do not claim a task whose dependencies are not all Done (or configured complete statuses)
- [ ] #2 Do not chase an assigned task while any open dependency remains; treat as blocked (log once, not spam)
- [ ] #3 Document agent pattern: add dep (blocker or review task) via backlog to pause chase; clear/complete deps to resume
- [ ] #4 Define policy for pathological graphs: cycle detection; Done child with unfinished deps; missing dep ids
- [ ] #5 Minimal tests: blocked claim/chase; unblocked after dep Done
<!-- AC:END -->
