---
id: TASK-91
title: Add --timing flag to aiswarm status for stage breakdowns
status: Done
assignee:
  - '@antigravity'
created_date: '2026-10-26 12:00'
updated_date: '2026-10-26 12:04'
labels: []
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Running aiswarm status can take non-trivial time, especially with many panes, backlog candidate queries, or rate limit capture. Operators cannot see what stages are taking time.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 aiswarm status accepts --timing flag
- [x] #2 When --timing is passed, stage names and durations (in ms or s) are displayed along with total time
- [x] #3 Works with brief and normal status output
- [x] #4 Existing tests pass and new unit test covers --timing
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Add --timing flag to status parser in swarm/cli.py. 2. Support timing parameter in swarm/topology.py (status_lines, print_status, watch_status) recording time.perf_counter() for each stage (session check, tasks supervisor, per-pane monitor/capture/spec checks, categories/backlog scan, scheduled events, table formatting). 3. Format and output timing table when timing is True. 4. Add test in test_swarm.py. 5. Run make test.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented --timing flag in swarm/cli.py and swarm/topology.py. Verified live on swarm with and without --brief, and verified test suite passing (31 monitor, 181 swarm/presence tests).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Added --timing flag to aiswarm status to display a breakdown of stage names, durations in ms/s, percentage of time, and total duration. Verified with pytest and live CLI test.
<!-- SECTION:FINAL_SUMMARY:END -->
