---
id: TASK-8
title: Figure out better ways to manage agent status detection
status: To Do
assignee: []
created_date: '2026-06-18 11:15'
updated_date: '2026-07-16 13:10'
labels:
  - status-detection
  - monitoring
dependencies: []
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Explore, design, and implement a robust agent status detection framework (idle vs. working) that does not rely on scraping terminal output in `monitor.c`.

### Why
- Parsing the stdout of a tmux pane is highly fragile. Any spinner updates, terminal redraws, or minor prompt changes in upstream tools break classification.
- We are moving away from prompting agents programmatically based on idle state detection, but we still need basic status visibility (e.g. for monitoring dashboards or pulse loops).

### Alternatives to Evaluate

1. **First-Party Session JSONs (Claude Code):**
   - Claude Code writes active process state to `~/.claude/sessions/{PID}.json`.
   - Fields include: `status: "idle" | "busy"`, `updatedAt`, `cwd`.
   - Write a python helper to read this directly using the PID of the shell/agent in the pane.

2. **Process Tree Walking (General CLI Agents):**
   - For black-box CLIs that do not output status files (e.g. Gemini, Codex), check the process tree under the agent's parent process.
   - If the agent is actively executing a command (e.g., has child processes like `git`, `make`, `python`, or a compiler), class it as `working`.
   - If it has no children and is waiting on socket read or terminal stdin, class it as `idle`.

3. **Log Modification Watching:**
   - Watch the agent's session log/transcript directories.
   - If a file is being modified (updates to SQLite or JSONL), transition to `working`. 
   - Apply a cooldown window (e.g., no updates for 10 seconds -> transition back to `idle`).
<!-- SECTION:DESCRIPTION:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-07-16 hygiene: monitor is intentionally content-agnostic (any output=working, quiet=idle). Semantic idle/working redesign conflicts with that product decision. Archiving.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Archived: conflicts with deliberate monitor design (activity-only, not agent-UI scraping).
<!-- SECTION:FINAL_SUMMARY:END -->
