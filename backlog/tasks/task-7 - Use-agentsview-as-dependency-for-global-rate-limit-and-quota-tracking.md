---
id: TASK-7
title: Use agentsview as dependency for global rate limit and quota tracking
status: To Do
assignee: []
created_date: '2026-06-18 10:45'
labels: []
dependencies: []
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Transition from fragile terminal screen-scraping (`monitor.c`) to structured, global token/rate-limit tracking using `agentsview` as a dependency. 

### Why
- Screen-scraping inside `monitor.c` to extract `g_usage_pct` is fragile, requires frequent pattern adjustments when agent CLIs update their spinners/UIs, and only tracks the local pane's context (missing concurrent panes).
- We are moving away from prompting agents based on idle state detection, which renders `monitor.c`'s real-time state classification redundant.
- We need robust, global (machine-wide) tracking of rolling rate limits (TPM/RPM) and daily/monthly credit budgets (e.g., Claude Pro hours/USD).

### Approach
1. **Leverage `agentsview` Syncing:** Use `agentsview` to watch the filesystem (via `fsnotify` / `inotify`) and automatically ingest all agent transcripts/SQLite files into `/home/cottrell/.agentsview/sessions.db`.
2. **Central DB Querying:** Implement a lightweight poller/daemon that periodically queries the `usage_events` table in `sessions.db` to compute:
   - **Rolling Rate Limit Proximity:** Sum of tokens consumed in the last 60 seconds per provider/model across all concurrent sessions (e.g. `SELECT SUM(input_tokens + output_tokens + cache_read_input_tokens) FROM usage_events WHERE model LIKE '%claude%' AND occurred_at >= datetime('now', '-60 seconds')`).
   - **Daily / Budget Quota:** Sum of USD cost spent today (e.g. `SELECT SUM(cost_usd) FROM usage_events WHERE occurred_at >= date('now', 'start of day')`).
3. **State Broadcast:** Write the computed proximities to a global JSON status file `/tmp/nudge-usage.json` (e.g. `{"claude": {"tpm_used_pct": 12, "daily_budget_pct": 54}}`) for consumption by other tools or the tmux status line.
<!-- SECTION:DESCRIPTION:END -->
