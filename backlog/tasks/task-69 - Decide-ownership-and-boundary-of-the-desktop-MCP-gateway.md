---
id: TASK-69
title: Decide ownership and boundary of the desktop MCP gateway
status: To Do
assignee: []
created_date: '2026-08-27 10:10'
updated_date: '2026-08-27 10:43'
labels:
  - architecture
  - mcp
dependencies: []
references:
  - ~/dev/local-mcp/README.md
  - ~/dev/local-mcp/server.py
documentation:
  - >-
    backlog/docs/architecture/voice-agent-comms/doc-5 -
    Voice-subscription-and-agent-communications-research.md
priority: medium
type: spike
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Decide whether the current local-mcp connector gateway belongs inside nudge, remains a separate small service, or becomes a separately packaged machine-facing adapter. Define the stable contract between an internet-facing authenticated ingress, durable mailbox/task operations, and nudge swarm routing so connector-specific concerns do not leak throughout the orchestrator.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The current local-mcp tools, authentication, Cloudflare tunnel, project mapping, and nudge integration points are inventoried
- [ ] #2 Options compare keeping the repository separate, merging it into nudge, and extracting a thin machine gateway package
- [ ] #3 The decision evaluates security boundary, release cadence, failure isolation, discoverability, configuration duplication, and reuse without nudge
- [ ] #4 A recommended API boundary covers submit, query status, list/read replies, acknowledge, and routing without committing to a particular chat provider
- [ ] #5 The outcome is recorded as a Backlog decision or architecture document with explicit migration and no-change paths
<!-- AC:END -->
