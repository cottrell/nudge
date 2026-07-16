---
id: TASK-25
title: >-
  Consider example workflow of how one agent can aiswarm send to another and
  perhaps ask for response in backlog and a ping via aiswarm send when done so
  that the sending agent doesn't just sit there tmux pane streaming the working
  agent.
status: Done
assignee:
  - grok
created_date: '2026-07-15 10:38'
updated_date: '2026-07-16 09:25'
labels: []
dependencies: []
documentation:
  - doc-2
modified_files:
  - README.md
  - backlog/docs/doc-2 - Agent-to-agent-handoff-via-send-backlog-and-ping.md
type: spike
---

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Document peer A→B handoff: send poke, backlog as response store, done-ping (no pane streaming)
- [x] #2 Call out anti-patterns (spectator attach, giant send payloads, chat-only status)
- [x] #3 Relate pattern to aiswarm tasks dispatcher
- [x] #4 Publish as backlog guide + discoverable pointer
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Document agent-to-agent handoff using aiswarm send + backlog as durable response + short completion ping.
2. Capture anti-pattern (don't stream/attach peer pane).
3. Note relationship to aiswarm tasks dispatcher.
4. Publish as backlog guide doc; link from task; mark Done.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Wrote backlog doc-2 (guide) with roles table, step-by-step A→B workflow, message templates, anti-patterns, and comparison to aiswarm tasks. Added short README pointer under Swarm-first workflow.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Documented the agent-to-agent handoff pattern (TASK-25): short aiswarm send pokes, backlog as durable request/response, short done-ping so requester does not stream the worker pane. Guide: backlog doc-2. README pointer added. No new runtime code — uses existing send + backlog + workers.
<!-- SECTION:FINAL_SUMMARY:END -->
