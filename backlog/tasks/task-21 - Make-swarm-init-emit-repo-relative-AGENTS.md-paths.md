---
id: TASK-21
title: Make swarm init emit repo-relative AGENTS.md paths
status: Done
assignee: []
created_date: '2026-07-13 14:56'
updated_date: '2026-07-13 14:58'
labels: []
dependencies: []
references:
  - swarm/init.py
  - AGENTS.md
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Stop hardcoding user-specific paths in the swarm block appended to repo AGENTS.md. Keep runtime/session paths under /tmp/nudge-swarm/<session>/, but make CLI examples and local helper paths repo-relative so a committed AGENTS.md stays portable.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Generated swarm block does not contain /home/cottrell or any user-specific home path.
- [x] #2 README/AGENTS examples use relative or tilde-neutral paths where possible.
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Swarm init and repo AGENTS now emit relative CLI/helper paths instead of /home/cottrell-specific paths. Added regression coverage for the generated block and init output.
<!-- SECTION:FINAL_SUMMARY:END -->
