---
id: TASK-17
title: Consider installable swarm self-awareness skill (protocol vs session note)
status: To Do
assignee: []
created_date: '2026-07-10 21:33'
labels:
  - design
  - docs
  - agents
dependencies: []
references:
  - swarm/common.py (build_self_awareness_text)
  - AGENTS.md (self-awareness read guidance)
  - /tmp/nudge-swarm/<session>/self-awareness.txt
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Think later: should swarm self-awareness be (partly) an installable agent skill?

## Context

Today self-awareness is a generated session artifact:
- `/tmp/nudge-swarm/<session>/self-awareness.txt` written on start/babysit
- session-specific paths (runtime map, CLI, config)
- short ops manual (status/watch, log send, comms vs babysit, no raw send-keys)
- agents only benefit if AGENTS/long-prompt/habit tells them to read it

## Split to consider

Not either/or — protocol vs instance state:

1. **Installable skill** (portable behavior): how to coordinate in a nudge swarm; when to re-read after /clear; prefer log send over raw tmux send-keys; comms worker ≠ babysit; resolve pane IDs from runtime map; do not bake absolute session/config paths into the skill body.
2. **Keep generated note + runtime.json** (session identity): session name, exact paths, this cfg, optional later: this pane id.

## Why attractive

- Survives context wipe better than hoping agents remember a /tmp tip
- Shared across agents that support skills / AGENTS includes
- Single place for the rules; note stays thin

## Risks

- Two sources of truth if skill re-documents CLI flags that change
- Skill systems differ (Claude skills ≠ Codex ≠ raw bash agents)
- Skills cannot know which of N live sessions the agent is in

## Out of scope for first think-through

- Auto-install into every agent vendor
- Generating the skill from YAML (nice-to-have later)

## Suggested direction if pursued

Skill = invariants + "read note/map"; keep self-awareness.txt as runtime coordinates; long prompt/init point at skill + note rather than pasting the full manual every time.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Design note or decision: skill vs note split (or reject skill approach)
- [ ] #2 If accepted: outline skill contents (protocol only) and what stays in self-awareness.txt / runtime.json
- [ ] #3 If accepted: note how agents discover the skill (AGENTS, long_prompt, vendor skill install paths)
- [ ] #4 No requirement to implement in this task — thinking/design only is fine
<!-- AC:END -->
