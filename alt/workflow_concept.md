# Alternative Workflow: Thing-Centric Task Sessions

## Goal
Transition from a "single long-running agent with periodic `/clear`" model to a modular architecture focused on **"The Thing" (Task Sessions)**. A "Thing" is a self-contained execution graph triggered by an external loop.

## Key Components

### 1. The Trigger Loop (Infrastructure)
The Trigger Loop is the stateless outer layer that initiates work.
- **Stateless Triggers:** A human, another agent, or an automated `inotify` loop (watching `backlog/`) triggers a "Thing".
- **Responsibility:** Its only job is to detect an event and launch a Task Session with the appropriate context and Session ID.

### 2. "The Thing" (Task Session / Execution Graph)
A "Thing" is a discrete unit of agent work with a defined start, execution, and end.
- **Hierarchy & Spawning:** A "Thing" can spawn sub-agents ("Sub-Things") to help with specialized sub-tasks.
- **The Graph:** This creates a Directed Acyclic Graph (DAG) of agent actions and outputs.
- **Roles:** Terms like "Leader" or "Worker" are simply roles within this hierarchical session graph, not distinct infrastructure requirements.
- **Persistence:** Each "Thing" is bound to a `session_id`. This allows any task or sub-task to be re-prompted or resumed later, either manually or by the Trigger Loop.

### 3. State & Persistence (The Task Board)
- **Unified Board:** The existing **`backlog/`** directory acts as the shared persistence layer for the entire graph.
- **Session Manifests:** Each "Thing" records its state, `session_id`, token usage, and artifacts in its assigned backlog task.
- **Resumability:** Because state lives in the `backlog/` and `session_id`s are tracked, a "Thing" can be "paused" (terminated) and later "re-prompted" by the Trigger Loop with full continuity.

### 4. Hybrid Infrastructure (Gateway)
- **Gateway Unification:** **Bifrost** or **LiteLLM** unifies **Local Models** (Ollama) and **Frontier APIs** (Claude, Gemini, Codex).
- **Semantic Caching:** Essential for making re-prompting and cyclical communication token-efficient across the session graph.

## Workflow Shift
| Feature | Current (Nudge) | Alternative (Thing-Centric) |
| :--- | :--- | :--- |
| **Execution** | Continuous Process | **Discrete "Things" (Task Sessions)** |
| **Trigger** | Manual / Sequential Nudges | **Event-Driven IO Loop / Human** |
| **State** | Filesystem + Context Re-injection | **`backlog/` + Session ID Persistence** |
| **Hierarchy** | Single Agent | **DAG of Spawning Agents** |
| **Lifecycle** | Forever (until `/clear`) | **Defined Start -> Execution -> End** |

## Swarm Protocols

1. **Task Spawning:** When a "Thing" needs help, it creates a new task in `backlog/` which the Trigger Loop detects and launches as a "Sub-Thing".
2. **Resumption Protocol:** To resume a "Thing", the Trigger Loop retrieves the `session_id` from the backlog and re-primes the agent session.
3. **Protocol-Bound Updates:** Agents strictly append implementation notes to the task board, allowing the Trigger Loop (or other agents in the graph) to observe progress.

## Termination & Cleanup

A "Thing" must have a clear exit condition to prevent resource leakage:
1. **Completion Signal:** Upon finishing its goal, the "Thing" emits a `TASK_DONE` token and updates the `backlog/` status to `Done`.
2. **Resource Release:** The Trigger Loop detects the `Done` status and shuts down any persistent sessions (e.g., `tmux` panes or background processes) associated with that `session_id`.
3. **Artifact Archival:** Before terminating, the "Thing" ensures all key artifacts and the final `session_manifest.json` are committed to the `backlog/` or the repository.
4. **Cleanup Trigger:** An automated cleanup script can periodically prune orphans—`session_id`s in `./alt/state/` that no longer have an active task in the `backlog/`.

## Comparison of Persistent Workflows

| Tool | State Storage | Best For | Ubuntu Fit | Persistence Strength | Drawbacks |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **ClawTeam** | Filesystem / Backlog | Parallel feature work | Excellent | High | Coordination tuning needed |
| **MetaSwarm** | BEADS (Git-Native) | TDD, SDLC, Refactoring | Excellent | Very High | Heavier on git ops |
| **Hermes** | SQLite / FTS5 | Personal Partner | Good | Highest | Single-agent focus |
| **Nudge (Current)** | Terminal / `GEMINI.md` | Interactive coding | Good | Medium | Manual resets |

## Hybrid Infrastructure Strategy (Local + Frontier)

To balance performance, cost, and intelligence, the workflow uses a **Hybrid Infrastructure** that unifies local models with frontier APIs (Claude, Gemini, Codex):

1. **Gateway Unification:** Use **Bifrost** (preferred for high performance) or **LiteLLM** as the central proxy. It provides a single OpenAI-compatible endpoint for all agents.
2. **Provider Mix:**
   - **Frontier Models:** Route "Leader" planning calls or complex refactoring tasks to **Claude 3.5 Sonnet**, **Gemini 1.5 Pro**, or **GPT-4o/Codex**.
   - **Local Models:** Route repetitive or low-complexity tasks (e.g., unit test generation, linting fixes) to local **Ollama** or **vLLM** instances running Llama 3 or Qwen 2.5.
3. **Smart Routing:** Use Bifrost/LiteLLM's routing rules to automatically swap models based on task labels in the `backlog/`.
4. **Efficiency:** Enable **Semantic Caching** at the gateway level to ensure that if a frontier model (expensive) has already seen a large context block, a local model (cheap) can reuse that "understanding" via the cache.

## Setup on Ubuntu

1. **Local Gateway:** Start **Ollama** or **vLLM** for local inference.
2. **API Proxy:** Configure **Bifrost** or **LiteLLM** with keys for Anthropic (Claude), Google (Gemini), and OpenAI.
3. **Orchestration:** Deploy **ClawTeam** or **MetaSwarm** pointing to the unified local proxy port (e.g., `:::8080`).
4. **Persistence:** Use the existing root **`backlog/`** as the unified source of truth.
