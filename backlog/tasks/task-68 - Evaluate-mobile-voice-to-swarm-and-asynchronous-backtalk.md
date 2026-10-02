---
id: TASK-68
title: Evaluate mobile voice-to-swarm and asynchronous backtalk
status: Done
assignee: []
created_date: '2026-08-27 10:10'
updated_date: '2026-10-02 09:10'
labels:
  - voice
  - mcp
  - mobile
dependencies: []
references:
  - 'https://help.openai.com/en/articles/11487775-connectors-in'
  - 'https://docs.x.ai/grok/connectors'
  - 'https://openclaw.ai/'
  - 'https://docs.ntfy.sh/'
documentation:
  - >-
    backlog/docs/architecture/voice-agent-comms/doc-5 -
    Voice-subscription-and-agent-communications-research.md
priority: high
type: spike
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Research and prototype the lowest-friction conversational round trip for capturing notes or tasks by voice on a phone, dispatching them to desktop work, and later pulling replies into a user-initiated Grok or ChatGPT conversation. Compare the existing subscription connector path with OpenClaw and other self-hosted conversational inbox approaches. Treat submission, durable asynchronous processing, and explicit in-conversation reply retrieval as separate capabilities. Do not use unsolicited push notifications or automatic TTS, and do not assume pay-as-you-go model APIs.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Current Grok and ChatGPT voice support for custom MCP/connectors is verified from primary documentation and tested where practical
- [x] #2 The design defines durable correlation between submitted work, completion replies, conversation or task identity, acknowledgement, and replay without requiring the original voice session to remain open
- [x] #3 A minimal end-to-end experiment submits one phone-originated task and later pulls the correlated result into a user-initiated Grok or ChatGPT conversation
- [x] #4 The design does not emit unsolicited mobile notifications or speech; the user explicitly asks to check, continue, or retrieve replies
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Dropped scope (user decision 2026-10-02): OpenClaw/inbox comparison, auth audit, phone tmux UI evals (muxpod already in use). Simple comms.db mailbox chosen.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Voice-to-swarm round trip delivered in ~/dev/desktop-mcp: Grok/ChatGPT connectors -> send_swarm_message -> aiswarm comms.db; replies pulled via poll-only check_messages (cursor/ack/replay, no push). Grok->desktop confirmed working by user. Comparison, auth-audit and phone-UI criteria dropped.
<!-- SECTION:FINAL_SUMMARY:END -->
