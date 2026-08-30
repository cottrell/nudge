---
id: TASK-71
title: Timed run period for babysit and tasks loops
status: Done
assignee: []
created_date: '2026-08-30 12:30'
updated_date: '2026-08-30 12:36'
labels: []
dependencies: []
priority: medium
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Run babysit or tasks for a wall-clock period, e.g. an hour, then stop the group automatically.

Pipe the deadline into the existing session_worker loop (do not spawn a separate timer process). Manual stop must drop the timed state.

Not the same as TASK-64 (schedule a backlog item for later).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 aiswarm tasks start --for 1h (and 30m/90s/seconds) enables the group only until that deadline
- [x] #2 aiswarm babysit start --for <duration> enables prompts only until that deadline
- [x] #3 session_worker loop auto-disables the timed group when the deadline passes
- [x] #4 aiswarm tasks stop / babysit stop (and aiswarm stop) clear the timed state so a later start is untimed unless --for is passed again
- [x] #5 start without --for overwrites any previous timer and runs until manual stop
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
`--for` on `aiswarm babysit start` / `aiswarm tasks start` stores a unix `until` deadline. session_worker expires both groups each loop tick. Manual stop (and untimed start) unlinks the timer.

- tasks: `until` key in `tasks/enabled.json`
- babysit: `babysit_until.json` (underscore so it is not eaten by the `babysit-*.json` spec glob)
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Added `--for <duration>` to babysit and tasks start (1h, 30m, 90s, or seconds). The session worker auto-disables the group at the deadline. Stop or a later untimed start clears the timed state.
<!-- SECTION:FINAL_SUMMARY:END -->
