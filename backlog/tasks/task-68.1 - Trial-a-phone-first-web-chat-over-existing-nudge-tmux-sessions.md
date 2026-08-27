---
id: TASK-68.1
title: Trial a phone-first web chat over existing nudge tmux sessions
status: To Do
assignee: []
created_date: '2026-08-27 11:30'
labels:
  - mobile-web
  - voice
  - tmux
dependencies: []
references:
  - 'https://github.com/antonlobanovskiy/agent-tmux-web'
  - 'https://github.com/AliceLJY/agentdeck'
documentation:
  - >-
    backlog/docs/architecture/voice-agent-comms/doc-5 -
    Voice-subscription-and-agent-communications-research.md
parent_task_id: TASK-68
priority: high
type: spike
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Test whether an existing browser UI can provide usable text and voice-dictated chat from a phone while attaching to nudge-created tmux sessions running official subscription CLIs. Try Agent Tmux Web unchanged first, then AgentDeck if needed. Build a minimal custom interface only if existing tools fail a concrete requirement. First cut is turn-based rather than full-duplex hands-free voice.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Agent Tmux Web is run against a disposable existing nudge swarm without requiring it to own or recreate the tmux sessions
- [ ] #2 On the actual phone, the user can select a session, dictate through the phone keyboard or browser input, review/edit the text, send it, and read the response
- [ ] #3 Raw terminal access remains available for permissions, pickers, and malformed chat rendering
- [ ] #4 Two optional voice input modes are assessed: review-before-send and silence/VAD-triggered auto-send; neither is required for the initial success criterion
- [ ] #5 The auth path is private and explicit, the UI is not exposed directly to the public internet, and no model API or third-party subscription auth is introduced
- [ ] #6 If Agent Tmux Web fails, the failure is recorded before trying AgentDeck; custom implementation is scoped only from demonstrated gaps
<!-- AC:END -->
