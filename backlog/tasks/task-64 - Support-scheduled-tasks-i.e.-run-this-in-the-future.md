---
id: TASK-64
title: Schedule backlog tasks (not-before ready filter in tasks dispatcher)
status: To Do
assignee: []
created_date: '2026-08-07 09:35'
updated_date: '2026-10-02 09:44'
labels:
  - parked
dependencies: []
references:
  - TASK-82
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Scheduling is a ready-filter in the tasks dispatcher, not a babysit feature. A task carries a not-before time; the dispatcher skips it until the clock passes it, on top of all existing filters (deps, labels, assignee, category, max_inflight). Backlog stays the log. Recurring work (e.g. Friday heavy review) = a task that is created/re-created with the next not-before.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Task can declare a not-before timestamp (mechanism TBD: label like 'after-2026-10-09T09' vs description/frontmatter field; pick whichever backlog CLI can read in --json)
- [ ] #2 Dispatcher candidate filter skips tasks whose not-before is in the future; applies identically in dry-run (tasks once -D) and live
- [ ] #3 Not-before tasks do not consume max_inflight and are not chased or treated as stuck
- [ ] #4 Dry-run output lists deferred tasks with their ready time
- [ ] #5 Tests: future task skipped, past task claimed, composes with deps/category filters; docs in instructions tasks
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-02: Parked. Backlog has no custom fields (dueDate is date-only deadline). Revisit if Backlog gains a start-time/custom field, or decide on a label convention. Scheduled messages are tracked separately (see send --at task).

Scope: this is about scheduling BACKLOG TASKS in the 'aiswarm tasks' dispatcher. It is NOT the comms-message scheduler: that is TASK-82 (aiswarm send --at), done. Use TASK-82 for timed reminders/nudges; use this only for deferring real backlog work. Reference: TASK-82.
<!-- SECTION:NOTES:END -->
