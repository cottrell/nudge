---
id: TASK-10
title: Design session launch metadata schema and agent non-interactive commands
status: To Do
assignee: []
created_date: '2026-06-18 11:58'
labels: [orchestration, CLI, schema]
dependencies: []
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Define how session launch metadata (who launched, session ID mapping) is stored in the resumable "Thing" execution graph, and establish the exact non-interactive (`-p` / print mode) CLI commands for all supported agents.

### 1. Session Launch Metadata Schema
To enable the parent (or human) to query, revive, or debug child executions, we must persist who launched each session. This can be stored in the project's `graph.json` or a local `run.db` SQLite table:

```sql
CREATE TABLE agent_sessions (
    session_id  TEXT PRIMARY KEY,       -- The agent CLI's native session ID
    node_id     TEXT NOT NULL,          -- Node name in the DAG (e.g. "impl-2")
    launcher_id TEXT NOT NULL,          -- Parent node ID (e.g. "planner-1") or "human"
    agent_type  TEXT NOT NULL,          -- "claude", "codex", "grok", "vibe", "agy"
    status      TEXT NOT NULL DEFAULT 'running', -- 'running', 'completed', 'failed'
    started_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 2. Programmatic CLI Reference (-p / Non-Interactive Modes)
To run these sessions safely under automation, we must launch them in non-interactive print mode (executing a single prompt and exiting) and auto-approve tool execution permissions.

#### A. Claude Code (`claude`)
- **New Session:**
  ```bash
  claude --always-approve -p "<prompt>"
  ```
- **Resume Session:**
  ```bash
  claude --resume <session_id> --always-approve -p "<prompt>"
  ```

#### B. Codex CLI (`codex`)
- **New Session:**
  ```bash
  codex exec --dangerously-bypass-approvals-and-sandbox "<prompt>"
  ```
- **Resume Session:**
  ```bash
  codex exec resume <session_id> --dangerously-bypass-approvals-and-sandbox "<prompt>"
  ```

#### C. Grok Build (`grok`)
- **New Session:**
  ```bash
  grok --always-approve -p "<prompt>"
  ```
- **Resume Session:**
  ```bash
  grok -r <session_id> --always-approve -p "<prompt>"
  ```

#### D. Mistral Vibe (`vibe`)
- **New Session:**
  ```bash
  vibe --auto-approve --trust -p "<prompt>"
  ```
- **Resume Session:**
  ```bash
  vibe --resume <session_id> --auto-approve --trust -p "<prompt>"
  ```

#### E. Antigravity CLI (`agy`)
- **New Session:**
  ```bash
  agy --dangerously-skip-permissions -p "<prompt>"
  ```
- **Resume Session:**
  ```bash
  agy --conversation <session_id> --dangerously-skip-permissions -p "<prompt>"
  ```
<!-- SECTION:DESCRIPTION:END -->
