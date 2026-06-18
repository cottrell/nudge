---
id: TASK-11
title: Design temporary tmux wrapper for one-off provider quota queries
status: To Do
assignee: []
created_date: '2026-06-18 12:25'
labels: [orchestration, CLI, quota]
dependencies: []
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Design a lightweight, non-disruptive utility to query official provider-reported billing quotas (such as Claude Pro's daily hours or Codex's usage percentages) using temporary tmux sandboxes.

### Why
- The interactive agent CLIs do not support native, non-interactive one-off commands to print usage stats.
- Sending `/usage` or `/stats` directly to the user's active development pane is disruptive, shifts the terminal screen buffer, and risks getting the pane stuck in the stats sub-menu.
- Querying a local database (`agentsview`'s `sessions.db`) works for local token spend, but cannot fetch remote-side subscription limits (like remaining Claude Pro window hours).

### Proposed Execution Flow
Instead of modifying the active development window, spawn a temporary, hidden window in tmux, run the agent, scrape the stats, and immediately destroy the window:

1. **Spawn Hidden Window:**
   Create a new tmux window in the background and capture its unique identifier:
   ```bash
   TEMP_TARGET=$(tmux new-window -d -P -F "#{session_name}:#{window_index}.#{pane_index}" "claude")
   ```
   *(We run this in the background `-d` so it is completely invisible to the user).*

2. **Wait for Boot & Send Command:**
   Wait a brief interval (e.g. 1.0s) for the REPL to boot, then send the agent's interactive stats command using `tmux-send`:
    - Claude: `/usage`
    - Codex: `/status`
    - Antigravity (agy): `/usage`
    - Grok: (No stats command supported)

3. **Capture Pane & Parse:**
   Wait for the stats screen to render, capture the text buffer, and parse it:
   ```bash
   tmux capture-pane -t "$TEMP_TARGET" -p > /tmp/quota-probe.txt
   # Parse /tmp/quota-probe.txt for quota lines (e.g. "4.2 / 5.0 hours")
   ```

4. **Force Cleanup:**
   Immediately terminate the temporary window to release resources:
   ```bash
   tmux kill-window -t "$TEMP_TARGET"
   ```

### Tradeoffs
- **Pros:** Grabs the 100% accurate remote provider quota; does not touch or disrupt the developer's active chat session.
- **Cons:** Spawning the CLI agent consumes a few seconds and a small start-up token footprint, so this should be run infrequently (e.g., polled every 5–10 minutes).
<!-- SECTION:DESCRIPTION:END -->
