# Alternative Workflow: Persistent Subagents with ClawTeam & Bifrost

## Goal
Transition from a "single long-running agent with periodic `/clear`" model to a "persistent task-oriented swarm" using ClawTeam for orchestration and Bifrost/LiteLLM for infrastructure.

## Key Components

### 1. ClawTeam (The Orchestrator)
- **Leader Agent:** Persists for the duration of the project or high-level milestone. Responsible for task decomposition using the existing `backlog/` system.
- **Worker Agents:** Spawned as subagents for specific tasks. They use the `mcp-backlog` tools to read requirements and update progress.
- **Persistence:** Instead of relying on agent memory, state is maintained in the shared **`backlog/`** structure.
- **Cyclical Communication:** Workers update the `implementationNotes` and `notesAppend` sections of their assigned tasks. Other workers or the Leader can monitor these files for updates, facilitating feedback loops.

### 2. Bifrost / LiteLLM (The Gateway)
- **Rate Limit Management:** Bifrost acts as a high-performance proxy to manage multiple subagents hitting API limits.
- **Semantic Caching:** Reduces token costs when multiple subagents share large parts of the codebase context.
- **Centralized Logging:** All subagent interactions are logged through the gateway for audit and debugging.

### 3. Workflow Shift
| Feature | Current (Nudge) | Alternative (ClawTeam/Bifrost/Backlog) |
| :--- | :--- | :--- |
| **Lifecycle** | Long-running, periodic `/clear` | Task-bound, persistent workers |
| **State** | Filesystem + brief context re-injection | **`backlog/` (Task Board)** |
| **Communication** | Sequential nudges | Async, cyclical updates via `mcp-backlog` |
| **Efficiency** | Manual token management | Semantic caching + granular tasks |

## Alternatives & Open Ecosystem

For Ubuntu-based environments where open-source/free-tier tools are preferred, several alternatives provide robust persistence:

### 1. MetaSwarm (The SDLC Specialist)
- **Philosophy:** Software Development Life Cycle (SDLC) as a first-class citizen.
- **Persistence:** Uses the **BEADS** (Git-Native Persistence) system. State, plans, and review cycles are committed to git-native metadata, ensuring the agent's memory lives with the code.
- **Why Ubuntu?** Runs as a set of CLI tools and background processes that integrate seamlessly with `tmux` and local git repos.
- **Cost:** Open-source core; cost is tied purely to your chosen LLM (works well with local models via LiteLLM/Ollama).

### 2. ClawTeam (The Swarm Orchestrator)
- **Philosophy:** Self-organizing teams of specialized workers.
- **Persistence:** Relies on **Git Worktrees** and filesystem-based Task Boards (like the root `backlog/`).
- **Ubuntu Advantage:** Leverages standard Linux primitives (filesystem, symlinks, git) without requiring complex container orchestration.

### 3. Hermes Agent (The Long-term Partner)
- **Philosophy:** Building a deepening model of the user and their projects over months.
- **Persistence:** Uses **FTS5 (SQLite)** for full-text session search and trajectory compression. It "remembers" how you solved a bug 3 months ago.

## Comparison of Persistent Workflows

| Tool | State Storage | Best For | Licensing |
| :--- | :--- | :--- | :--- |
| **ClawTeam** | Filesystem / Backlog | Parallelized feature work | Open Source |
| **MetaSwarm** | Git Metadata (BEADS) | TDD, complex refactoring | Open Source |
| **Hermes** | SQLite / Knowledge Graph | Personal assistant, long-running projects | Open Source |
| **Nudge (Current)** | Terminal State / `GEMINI.md` | Single-agent interactive coding | Open Source |

## Strategy for "Free-ish" Ubuntu Setup

1. **Gateway:** Run **Ollama** or **vLLM** on Ubuntu for local inference (Llama 3, Qwen 2.5).
2. **Proxy:** Use **Bifrost** (Go-native) or **LiteLLM** to wrap local models with an OpenAI-compatible API.
3. **Orchestration:** Deploy **ClawTeam** or **MetaSwarm** pointing to the local proxy.
4. **Persistence:** Use the existing root **`backlog/`** (managed by `mcp-backlog`) as the unified Task Board.
