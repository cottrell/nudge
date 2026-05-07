---
id: TASK-3
title: >-
  Create some trivial way to capture from existing tmux pane to fix bugs
  observed IRL
status: Done
assignee: []
created_date: '2026-05-07 10:25'
updated_date: '2026-05-07 10:33'
labels: []
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
i.e. notice codex is rate limited but status -w -b shows not/idle etc ... how to tell nudge ai or capture bot to just get the pane / interact (/status etc) and fix in real time?
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Monitor detects codex rate limiting from /status output (0% left).
- [x] #2 Monitor detects "hit your usage limit" messages.
- [x] #3 CLI has 'capture' command to dump and analyze pane state.
- [x] #4 CLI has 'probe' alias for 'usage' to force state refresh.
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
I fixed the monitor (both C and Python versions) to correctly detect rate limiting for Codex and other agents. Specifically, I improved ANSI stripping to avoid corrupted matching and added logic to transition to 'rate_limited' when usage percentage hits 0. I also added a 'capture' command to the swarm CLI to allow manual inspection and classification of any pane, and added a 'probe' alias to the 'usage' command to make it easy to force a state refresh in a monitored session.
<!-- SECTION:FINAL_SUMMARY:END -->
