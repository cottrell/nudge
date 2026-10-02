---
id: TASK-67
title: Explore cross-swarm discovery and interaction
status: Done
assignee: []
created_date: '2026-08-26 09:57'
updated_date: '2026-10-02 09:09'
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
- [x] #1 The current janus-data convention and existing swarm runtime/config discovery mechanisms are documented
- [x] #2 Options include retaining the informal convention, adding a machine-global active-swarm registry, and introducing an aiswarm or separate control CLI
- [x] #3 Registry lifecycle concerns are assessed, including registration, stale entries, cleanup, identity, and concurrent swarms
- [x] #4 Potential cross-swarm interactions and their safety or isolation boundaries are described
- [x] #5 A recommendation is recorded, including an explicit no-change or defer option
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Assessed cross-swarm discovery and desktop-mcp architecture. desktop-mcp already acts as the cross-project coordinator via ~/dev/janus-data, creating tasks and bridging comms using aiswarm send and comms.db polling. Nudge already supports point-to-point cross-swarm messaging via 'aiswarm send -s <swarm> <target>'. Explicitly reject adding a machine-global supervisor daemon or central registry in nudge to preserve simplicity, isolation, and avoid failure modes.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Explored cross-swarm discovery options. Explicitly rejected adding a machine-wide supervisor daemon, aiswarmctl, or persistent registry daemon to nudge. Project-level registry and cross-project routing are already cleanly handled externally by desktop-mcp and ~/dev/janus-data. Nudge retains lightweight point-to-point comms ('aiswarm send -s <swarm>') and will implement simple inspection ('aiswarm swarms') and sender provenance in follow-up work.
<!-- SECTION:FINAL_SUMMARY:END -->
