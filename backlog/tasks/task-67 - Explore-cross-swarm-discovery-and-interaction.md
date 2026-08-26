---
id: TASK-67
title: Explore cross-swarm discovery and interaction
status: To Do
assignee: []
created_date: '2026-08-26 09:57'
labels: []
dependencies: []
priority: low
type: spike
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Assess whether nudge should provide a durable way to know about and interact with other swarms. Today ~/dev/janus-data is an informal record; possible directions include a machine-global registry of active swarms, an aiswarm list-swarms command, or a separate aiswarmctl-style control surface. This is exploratory and does not commit the project to implementing cross-swarm discovery now.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The current janus-data convention and existing swarm runtime/config discovery mechanisms are documented
- [ ] #2 Options include retaining the informal convention, adding a machine-global active-swarm registry, and introducing an aiswarm or separate control CLI
- [ ] #3 Registry lifecycle concerns are assessed, including registration, stale entries, cleanup, identity, and concurrent swarms
- [ ] #4 Potential cross-swarm interactions and their safety or isolation boundaries are described
- [ ] #5 A recommendation is recorded, including an explicit no-change or defer option
<!-- AC:END -->
