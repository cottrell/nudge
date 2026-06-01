# Alt: Thing-Centric Task Sessions

This directory contains conceptual notes and initial setup for an alternative agent workflow focused on **"The Thing" (Task Sessions)**. It moves away from terminal-scraping and periodic clearing in favor of a modular, graph-based architecture.

## Key Ideas
- **"The Thing" (Task Session):** A discrete unit of agent work (an execution graph) with a defined start and end. It can spawn sub-tasks ("Sub-Things") as needed.
- **Trigger Loop:** A stateless infrastructure layer (human or IO Loop) that initiates "Things" based on events.
- **Hybrid Persistence:**
  - **Interface:** **`backlog/`** (Markdown) for transparency and git-native versioning.
  - **Index:** **`alt/state/`** (SQLite/JSONL) for efficient session resumption and log searching.
- **Infrastructure Gateway:** Use **Bifrost** or **LiteLLM** to unify **Local Models** (Ollama) and **Frontier APIs** (Claude, Gemini, Codex).

## Structure
- `config/`: Example configurations for Bifrost, LiteLLM, and ClawTeam.
- `scripts/`: Implementation of the Trigger Loop and Prompt Dispatcher.
- `backlog/` (Root): Shared state managed via `mcp-backlog` tools.

## Getting Started (Conceptual)
1. Start the **Trigger Loop** (an `inotify` watcher or human-in-the-loop).
2. The Trigger Loop detects a new task in `backlog/` and launches a **"Thing" (Task Session)**.
3. If the "Thing" needs help, it spawns a "Sub-Thing" by creating a dependency task in the backlog.
4. All interactions are routed through the **Bifrost** gateway for rate limiting and semantic caching.
