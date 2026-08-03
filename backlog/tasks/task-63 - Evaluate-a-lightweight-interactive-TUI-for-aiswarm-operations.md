---
id: TASK-63
title: Evaluate a lightweight interactive TUI for aiswarm operations
status: To Do
assignee: []
created_date: '2026-08-03 15:34'
labels: []
dependencies: []
priority: low
type: spike
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Assess whether an existing, low-complexity terminal UI could make routine aiswarm monitoring easier without replacing or degrading the CLI. The candidate experience would open on a live view comparable to `aiswarm status -w` and allow switching to useful views or actions such as tasks and babysit. This is explicitly a go/no-go investigation: avoid implementation if available approaches add disproportionate dependencies, code, or maintenance busywork.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The investigation identifies and compares plausible lightweight existing TUI tools or libraries, including dependency footprint and maintenance cost.
- [ ] #2 The proposed interaction, if worthwhile, keeps every existing CLI workflow available and describes a live status default plus navigation to tasks and babysit-related views.
- [ ] #3 A written go/no-go recommendation explains whether the usability benefit justifies the implementation and ongoing complexity.
- [ ] #4 If the recommendation is go, the task records a small bounded follow-up scope; if no-go, no TUI implementation is required.
<!-- AC:END -->
