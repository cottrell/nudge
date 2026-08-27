---
id: TASK-68.1
title: Trial a phone-first web chat over existing nudge tmux sessions
status: In Progress
assignee:
  - '@codex'
created_date: '2026-08-27 11:30'
updated_date: '2026-08-27 11:36'
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

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Inspect upstream source, dependencies, authentication, tmux command construction, file upload and bind behavior before execution.\n2. Install in a separate ~/dev checkout and configure an explicit IPv6 port plus mandatory token without exposing secrets in git.\n3. Start it without disturbing existing tmux/nudge processes and verify HTTP auth plus discovery of existing sessions.\n4. Record access instructions, security boundary, observed gaps and phone validation still required.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-08-27 trial: cloned Agent Tmux Web v0.1.26 at aa13d56 into ~/dev/agent-tmux-web after source/security inspection. Built production bundle and ran tests (269/270; only source-registry manifest assertion fails after patched ws update). Updated runtime ws to 8.21.3 due high-severity memory-exhaustion advisory. Started transient user service agent-tmux-web-trial.service on [::]:16174 with required token and Codex app-server autostart disabled. Verified unauthenticated API=401, authenticated API=200, and discovery of 12 existing tmux sessions including nudge-created sessions. Phone UX remains unverified. Security: token grants control over all user tmux sessions, not only nudge; HTTP permits keyboard dictation but trusted HTTPS is required before browser microphone/VAD testing.
<!-- SECTION:NOTES:END -->
