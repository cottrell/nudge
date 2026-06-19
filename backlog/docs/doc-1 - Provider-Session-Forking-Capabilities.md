---
id: doc-1
title: Provider Session Forking Capabilities
type: guide
created_date: '2026-06-19 12:19'
---
## Summary of Session Forking Support in Nudge Swarms

When developing orchestrations (like `alt/` prompt-driven Things), branching an agent's context natively is preferred over recreating a session externally to avoid state discrepancies.

### 1. Provider Capabilities Matrix

| Provider / CLI | Native Fork Command / Flag | Native Resume Command | Session Storage Location |
| :--- | :--- | :--- | :--- |
| **Claude Code** (`claude`) | `claude -r <sid> --fork-session` | `claude -r <sid>` | `~/.claude/sessions/` |
| **Codex** (`codex`) | `codex fork <sid>` | `codex exec resume <sid>` | `~/.codex/sessions/` |
| **Grok** (`grok`) | *None* | `grok -r <sid>` | `~/.grok/sessions/` |
| **Agy** (`agy`) | *None* | `agy --conversation <sid>` | `~/.gemini/tmp/` / `~/.cache/` |

---

### 2. State & "Non-Linear Effects"

Managing conversation history externally (e.g. starting a fresh session and appending previous turns) misses several local environment and CLI states:

#### Workspace & Code Versioning
* **Git Commit Synchronization**: Grok supports `--restore-code` when resuming, checking out the exact repository commit active during that turn. External session recreation leaves the files out of sync.
* **Git Worktrees**: CLIs (e.g., Claude `--worktree`) link sessions to isolated git worktrees. Native resume/fork respects this mapping.

#### Runtime & Settings
* **Approved Commands (Permissions)**: Previously approved command prefixes are stored in session state. External sessions require re-prompting the user for tool executions.
* **Local Cache & Memory**: Tools maintain session-specific key-value memory, skills caches, or `CLAUDE.md` context parameters.
* **Token Compaction**: CLIs condense old turns (e.g., Grok's `--compaction-mode`). Native forks keep the compacted state, whereas external reconstruction triggers re-compaction, changing the prompt shape and model behavior.
