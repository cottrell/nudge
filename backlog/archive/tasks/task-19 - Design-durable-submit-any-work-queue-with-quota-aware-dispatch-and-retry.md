---
id: TASK-19
title: Design durable submit-any work queue with quota-aware dispatch and retry
status: To Do
assignee: []
created_date: '2026-07-11 10:43'
updated_date: '2026-07-16 13:10'
labels:
  - swarm
  - comms
  - quota
  - design
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Parked design for reliably submitting a prompt from any device without choosing a specific agent. Submission must be committed before agent selection, then dispatched to an eligible configured pane using cached quota as a best-effort exclusion signal. Preserve jobs across crashes and make delivery/completion state inspectable.

Keep this separate from ordinary comms events: events deliver messages; jobs are durable work units. A thin remote shortcut or standalone wrapper may call the swarm CLI later, but no HTTP service or new infrastructure is part of the initial scope.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A submit command atomically persists the full prompt and returns a stable job ID before attempting dispatch.
- [ ] #2 Duplicate client retries can use an idempotency key without creating duplicate jobs.
- [ ] #3 A dispatcher transactionally claims pending or retryable jobs, prefers eligible panes, and excludes only providers explicitly known exhausted from cached quota data.
- [ ] #4 Assignments use leases and retry with bounded backoff after dispatcher or delivery failure; terminal failures remain inspectable and are never silently discarded.
- [ ] #5 Job state distinguishes submitted, assigned, delivered, acknowledged/completed, and failed; delivery is not treated as completion.
- [ ] #6 Completion uses explicit acknowledgement tied to the job ID because terminal activity cannot reliably prove task completion.
- [ ] #7 CLI commands support submit, list/status, acknowledge, and manual retry; no remote HTTP endpoint is required initially.
- [ ] #8 SQLite durability and concurrency settings are documented and tested, including WAL mode, synchronous policy, busy timeout, atomic claims, and crash recovery.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Prefer integrating with the existing SQLite comms database and worker loop while using separate jobs/attempts state. Do not introduce a competing-consumer __any__ event unless atomic claim semantics are implemented. Start with a persistent small swarm as the execution pool; a standalone nudge-any wrapper can remain a thin caller of the same CLI.

2026-07-16 hygiene: durable submit-any queue is effectively the backlog + aiswarm tasks (or aiswarm send) path. Outside-world entry (custom MCP, voice, desktop) can create backlog tasks or send to a swarm without building a job queue inside nudge. Archiving.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Archived: not needed in-nudge. External entry points use backlog and/or aiswarm send/tasks; no separate submit-any service.
<!-- SECTION:FINAL_SUMMARY:END -->
