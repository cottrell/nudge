# Alt: Persistent Swarm Workflow

This directory contains conceptual notes and initial setup for an alternative agent workflow that moves away from terminal-scraping and periodic clearing.

## Key Ideas
- **Persistence:** Subagents stay "alive" for the duration of a task.
- **Resumability:** Session IDs are persisted in task metadata to allow resuming work later.
- **Task Board:** Uses the existing **`backlog/`** directory. This is the source of truth for all agent activity.
- **Cyclical Comms:** Communication happens through `mcp-backlog` task updates (notes, status changes).
- **Infrastructure Gateway:** Use **Bifrost** (preferred for performance) or **LiteLLM** to unify **Local Models** (Ollama) and **Frontier APIs** (Claude, Gemini, Codex) while managing rate limits, semantic caching, and session states.

## Structure
- `config/`: Example configurations for Bifrost, LiteLLM, and ClawTeam.
- `backlog/` (Root): Shared state managed via `mcp-backlog` tools.

## Getting Started (Conceptual)
1. Start Bifrost using `config/bifrost_config.json.example`.
2. Initialize the ClawTeam Leader.
3. Leader creates or updates tasks in the root `backlog/` using `mcp_backlog_task_create`.
4. Workers are assigned to tasks, perform their work in persistent sessions, and update the task markdown files with progress and results.
