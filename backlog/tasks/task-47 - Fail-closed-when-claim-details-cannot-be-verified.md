---
id: TASK-47
title: Fail closed when claim details cannot be verified
status: Done
assignee:
  - 'aiswarm:nudge:0.1'
created_date: '2026-07-27 11:18'
updated_date: '2026-07-27 11:20'
labels: []
dependencies: []
priority: high
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The dispatcher must not claim a candidate when it cannot fetch the full Backlog task needed to enforce tasks.skip_assignees. An uncommitted implementation exists but its existing claim-path tests do not supply task details and fail. Complete the behavior and update focused tests; discard the unrelated untracked status-list change separately.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Claim skips and logs candidates whose task detail cannot be fetched
- [x] #2 Existing dry-run, claim-failure, and delivery-failure claim paths remain covered and pass with verified task detail
- [x] #3 make test-swarm passes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Keep the fail-closed claim path in tasksctl, but update claim-path tests to provide full task JSON so skip_assignees and dependency checks can run.\n2. Add a regression test that proves candidates are skipped and logged when task details cannot be fetched.\n3. Revert the unrelated backlog status-list edit, run make test-swarm, then record the results and close the task.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Claimed by aiswarm tasks dispatcher for pane 0.1 (session nudge).

Added a dedicated missing-detail regression and updated the claim-path tests to inject verified task JSON before skip_assignees/dependency checks run. Verified with pytest -q test_swarm.py -k claim-path coverage and make test-swarm (71 passed).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Made claim-path fetches fail closed when the full Backlog task cannot be loaded, so skip_assignees is never bypassed on partial data. Updated the claim-path tests to provide verified task details, added a regression for the missing-detail skip/log path, and verified everything with make test-swarm (71 passed).
<!-- SECTION:FINAL_SUMMARY:END -->
