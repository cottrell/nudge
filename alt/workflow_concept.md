# Alt: Thing-Centric Task Sessions

## Goal
Transition from long-running agents to modular **"Things" (Task Sessions)**—discrete execution graphs triggered by a stateless outer loop.

## Key Components

### 1. Trigger Loop (Infrastructure)
Stateless outer layer (human, agent, or `inotify` on `backlog/`) that initiates a "Thing". It is the *observer* that calls the Dispatcher when an event occurs.

### 2. The Prompt Dispatcher (Unified Interface)
The single entry point for all interactions with "The Thing".
- **Function:** `dispatch(prompt, session_id=None)`
- **Behavior:** 
  - If `session_id` exists: Resumes the specific Task Session via Bifrost/LiteLLM.
  - If `session_id` is None: Creates a new unique ID, registers it in the `backlog/`, and initializes the session.
- **Universal Access:** Can be called by a **Human** (CLI), another **Agent** (Tool Call), or a **Script/IO Loop**.

### 3. "The Thing" (Task Session / Execution Graph)
Discrete unit of work with a defined start, execution DAG, and end. 
- **Hierarchy:** Can spawn "Sub-Things" (child nodes in the DAG) by calling the Dispatcher.
- **Persistence:** Bound to the `session_id` stored in `backlog/` metadata for seamless resumption.

### 4. State & Persistence (The Task Board)
Unified source of truth: root **`backlog/`** directory. Agents strictly append to `implementationNotes` and update status to `blocked|in-progress|done`.

### 5. Hybrid Infrastructure (Gateway)
**Bifrost** or **LiteLLM** unifies local (Ollama) and frontier (Claude, Gemini, Codex) models. Uses **Semantic Caching** for efficient re-prompting and cyclical comms.

## Workflow Comparison
| Feature | Current (Nudge) | Alternative (Thing-Centric) |
| :--- | :--- | :--- |
| **Execution** | Continuous Process | **Discrete Task Sessions** |
| **Interface** | Direct Terminal Input | **Unified Prompt Dispatcher** |
| **Trigger** | Manual / Sequential | **Event-Driven / Human / Agent** |
| **State** | Filesystem + Context | **`backlog/` + Session ID** |
| **Lifecycle** | Forever (until `/clear`) | **Start -> Execution -> End** |

## Protocols

1. **Dispatching:** All prompts (manual or automated) go through the Dispatcher to ensure `session_id` continuity.
2. **Spawning:** "Things" create dependency tasks in `backlog/` which the Trigger Loop (via Dispatcher) launches as "Sub-Things".
3. **Resumption:** Dispatcher retrieves `session_id` to re-prime sessions.
4. **Termination:** Upon goal completion, emit `TASK_DONE`, update status to `Done`, and archive `session_manifest.json`.

## Ecosystem Comparison
| Tool | State Storage | Best For | Ubuntu Fit |
| :--- | :--- | :--- | :--- |
| **ClawTeam** | Filesystem / Backlog | Parallel feature work | Excellent |
| **MetaSwarm** | BEADS (Git-Native) | TDD, SDLC, Refactoring | Excellent |
| **Hermes** | SQLite / FTS5 | Long-term memory/recall | Good |
| **Nudge** | Terminal / `GEMINI.md` | Interactive coding | Good |
