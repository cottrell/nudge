---
id: TASK-9
title: Design DAG management revival and non-interactive session safety
status: To Do
assignee: []
created_date: '2026-06-18 11:20'
labels: [dag, execution-safety, orchestration]
dependencies: []
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Design the orchestration and safety layer for the agent DAG, specifically covering parent-to-child mappings, revival history, and preventing headless/non-tmux sessions from entering infinite loops or hanging.

### 1. DAG State Mapping (`graph.json`)
We need a centralized, lightweight record (`alt/state/graph.json`) that stores:
- **Edges:** Parent-to-child relationships.
- **Node Metadata:** Initialized timestamp (`started_at`), last active timestamp (`updated_at`), status, and `session_ref`.
- **Revival History:** Record of child session restarts when a node fails or is revived by its parent.

### 2. The Headless / Non-Tmux Safety Problem
If agent sessions are run outside of tmux (e.g., in a headless Docker/shell environment), we lose the ability to attach to the terminal pane to inspect or recover stuck sessions manually.
- If a child agent hits an error, auth prompt, or enters an infinite loop, it can run wild, consuming massive tokens and CPU.
- **Uphill Battle:** We must design safeguards so that agents cannot hang indefinitely or enter infinite prompt loops.

### 3. Mitigation Strategies

#### A. Run-Once / Non-Interactive CLI Mode
Where possible, execute the agent CLIs with flags that execute a single prompt and exit immediately, rather than launching an interactive REPL shell:
- **Claude Code:** Run `claude -p "prompt"` or `--non-interactive` (or equivalent flags) to execute a single instruction and terminate.
- **Codex / Gemini:** Standardize on run-once scripts that exit on completion or failure.
- This ensures the agent is a discrete transaction rather than a long-lived stateful shell session.

#### B. Heartbeat and Timeout Policies
The Pulse orchestrator should enforce:
- **Maximum Execution Time:** Auto-terminate any session (`kill -9`) that runs longer than a specified timeout (e.g., 5 minutes).
- **Stale Check:** If a session's log file or process has not updated its timestamp in `sessions.db` or `updatedAt` for N seconds, mark it as stuck and terminate it.

#### C. Tmux as a Default Harness
For interactive nodes (like primary planners or workers that need manual oversight), continue using `tmux` so that human operators can attach, inspect the terminal buffers, and recover state.
<!-- SECTION:DESCRIPTION:END -->
