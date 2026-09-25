---
id: TASK-78
title: Convenience command to resume swarm from recorded session-ids.json
status: To Do
assignee: []
created_date: '2026-09-25 19:11'
labels: []
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
aiswarm start always mints fresh session IDs for claude/grok panes, even when .aiswarm/session-ids.json has a prior resume record for that pane. Resuming today means either manually running tmux send-keys with each recorded resume command, or hand-editing config.yaml pane commands to embed the resume flag. Add a convenience path so aiswarm start (or a new aiswarm resume/start --resume) can look up an existing pane's recorded session id and swap it into the launch command live, instead of minting a new one, when the operator wants to reattach a prior swarm rather than start clean.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Decide the trigger: a start --resume flag, a separate aiswarm resume subcommand, or config.yaml opt-in per pane
- [ ] #2 On trigger, look up each pane's existing record in session-ids.json/runtime records and substitute the resume form (claude -r <id> / grok -r <id> / agy --conversation <id> / codex resume <id>) for that pane's command instead of pane.command from config
- [ ] #3 Skip/no-op cleanly for panes with no recorded id (e.g. codex/agy panes that were never captured) — fall back to pane.command
- [ ] #4 Document behavior and interaction with mint_launch_command in AGENTS.md/README
- [ ] #5 Unit tests covering: resume-flag substitution, no-record fallback, and no double-mint when a resume id is injected
<!-- AC:END -->
