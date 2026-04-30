---
id: TASK-1
title: Use Claude Code session JSON for state detection instead of terminal scraping
status: To Do
assignee: []
created_date: '2026-04-30 09:11'
labels: []
dependencies: []
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Claude Code writes live state to ~/.claude/sessions/{PID}.json. Verified fields: pid, status (idle/busy), cwd, updatedAt (ms), version.

Example observed:
  PID 2347159, status: busy, cwd: /home/cottrell/dev/nudge
  PID 1384688, status: idle, cwd: /home/cottrell/dev/planistan

Why: current monitor.c detects Claude state by regex-scraping terminal paint output -- fragile, breaks on UI redraws/format changes, requires recompile for pattern updates. Session JSON is ground truth.

Approach:
1. Get shell PID for a pane: tmux display-message -t <target> -p #{pane_pid}
2. Walk process tree to find claude child PID
3. Read ~/.claude/sessions/{PID}.json, check status field
4. idle->idle, busy->working; fall back to socket/monitor for rate_limited/error (unknown if JSON covers those)

Caveats:
- Does JSON capture rate_limited/error states? Needs testing.
- PID->pane mapping requires process tree walk
- Only helps Claude; Codex/Gemini/Qwen still need C monitor (see below)

See gavraz/recon (https://github.com/gavraz/recon) which reportedly uses this same approach -- read their implementation before building.

## State file landscape (researched 2026-04-30)

Claude Code is the only agent CLI that writes a real-time process state file.
All other agents write retrospective JSONL session logs, not live state.

| Agent  | Real-time state file                        | Notes                          |
|--------|---------------------------------------------|--------------------------------|
| Claude | ~/.claude/sessions/{PID}.json               | status: idle/busy, verified    |
| Codex  | none known                                  | writes ~/.codex/sessions/ JSONL|
| Gemini | none known                                  | writes ~/.gemini/ JSONL        |
| Qwen   | none known                                  | writes ~/.qwen/sessions/ JSONL |

agentsview (https://github.com/wesm/agentsview) was evaluated as a potential source
of unified agent state. It reads session files from 20+ agents but is retrospective
(session analytics/cost tracking), not a real-time process monitor. Not useful for
nudge's idle-detection purpose.
<!-- SECTION:DESCRIPTION:END -->
