---
id: TASK-23
title: Document aiswarm PATH prerequisite in swarm docs
status: Done
assignee: []
created_date: '2026-07-13 15:27'
updated_date: '2026-07-13 15:27'
labels: []
dependencies: []
references:
  - swarm/init.py
  - AGENTS.md
  - README.md
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Make the generated swarm note and README say that aiswarm must already be on PATH, and point users to the standard install target. This keeps agents from assuming the command works before the packaging step has been run.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Generated swarm note says aiswarm must be on PATH.
- [x] #2 README says to run make install-aiswarm from a checkout.
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Added a PATH prerequisite to the generated swarm note and README, and locked the generated text into the swarm regression test.
<!-- SECTION:FINAL_SUMMARY:END -->
