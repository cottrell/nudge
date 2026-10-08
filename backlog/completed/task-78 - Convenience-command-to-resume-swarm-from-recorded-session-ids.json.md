---
id: TASK-78
title: Convenience command to resume swarm from recorded session-ids.json
status: Done
assignee:
  - '@grok'
created_date: '2026-09-25 19:11'
updated_date: '2026-10-02 09:27'
labels: []
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
aiswarm start always mints fresh session IDs for claude/grok panes, even when .aiswarm/session-ids.json has a prior resume record for that pane. Resuming today means either manually running tmux send-keys with each recorded resume command, or hand-editing config.yaml pane commands to embed the resume flag. Add a convenience path so aiswarm start (or a new aiswarm resume/start --resume) can look up an existing pane's recorded session id and swap it into the launch command live, instead of minting a new one, when the operator wants to reattach a prior swarm rather than start clean.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Decide the trigger: a start --resume flag, a separate aiswarm resume subcommand, or config.yaml opt-in per pane
- [x] #2 On trigger, look up each pane's existing record in session-ids.json/runtime records and substitute the resume form (claude -r <id> / grok -r <id> / agy --conversation <id> / codex resume <id>) for that pane's command instead of pane.command from config
- [x] #3 Skip/no-op cleanly for panes with no recorded id (e.g. codex/agy panes that were never captured) — fall back to pane.command
- [x] #4 Document behavior and interaction with mint_launch_command in AGENTS.md/README
- [x] #5 Unit tests covering: resume-flag substitution, no-record fallback, and no double-mint when a resume id is injected
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Trigger is `aiswarm start --resume` only. Plain start still mints fresh Claude/Grok ids. No new subcommand and no per-pane YAML switch.
2. Add resume_launch_command(agent, record): if the pane has a session id in session-ids.json, return the short resume form (claude -r / grok -r / agy --conversation / codex resume). Otherwise None.
3. setup_monitors(resume=True) swaps that command in before mint_launch_command. Missing id keeps pane.command. mint sees the resume flag and does not append a second --session-id.
4. Document the flag and the mint interaction in AGENTS.md, README, and aiswarm instructions overview.
5. Tests: recorded-id substitution, no-record fallback (still mints), resumed claude/grok command is not double-minted.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Trigger is aiswarm start --resume only. Plain start still mints. No new subcommand and no per-pane YAML switch.
resume_launch_command returns the short form (claude -r / grok -r / agy --conversation / codex resume) or None. setup_monitors substitutes that command before mint_launch_command. The resume flag is session control, so mint does not append a second --session-id. Panes with no recorded id keep pane.command.
Validation: make test → test_c/test_monitor.py 30 passed, test_swarm.py 154 passed. New tests: test_resume_launch_command_forms_and_no_double_mint, test_start_resume_substitutes_recorded_ids_and_falls_back (claude/codex/agy substituted, grok with no record minted once), test_cli_start_resume_flag.
Commit: 1a69abc
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
aiswarm start --resume relaunches each pane that has a session-ids.json id with the short resume command instead of the config command. Panes with no id keep pane.command and Claude/Grok still mint. mint_launch_command sees the resume flag and does not append a second id. Verified with make test (30 monitor + 154 swarm), including substitution, no-record fallback, and no double-mint. Commit 1a69abc.
<!-- SECTION:FINAL_SUMMARY:END -->
