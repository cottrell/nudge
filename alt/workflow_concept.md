# Alternative Workflow: Persistent Subagents with ClawTeam & Bifrost

## Goal
Transition from a "single long-running agent with periodic `/clear`" model to a "persistent task-oriented swarm" using ClawTeam for orchestration and Bifrost/LiteLLM for infrastructure.

## Key Components

### 1. The Leader IO Loop (Orchestrator)
Instead of a long-running, token-burning Leader agent, we use a **Leader IO Loop**:
- **Event-Driven:** Uses an **Observer Pattern** (via `inotify` or polling) to monitor the `backlog/` directory for status changes or new implementation notes.
- **Stateless Planning:** When a change is detected, the loop triggers a brief, targeted LLM call (the "Planning Phase") to update the task board or re-assign workers.
- **Scaling:** Avoids "Infinite Context" issues by only loading relevant task snippets and session manifests into the LLM during planning events.

### 2. Worker Agents (Persistent & Protocol-Bound)
- **Session-Bound:** Workers stay alive for a task's duration but follow a **Strict Update Protocol**:
  - Only append to `implementationNotes` or `notesAppend`.
  - Update `status` to `blocked`, `in-progress`, or `done`.
- **Session Manifests:** Each worker maintains a `session_manifest.json` recording `session_id`, `last_worker`, `model_used`, `token_estimate`, and `key_artifacts`.

### 3. Bifrost / LiteLLM (The Gateway)
- **Rate Limit & Cost Management:** Monitor token creep via Bifrost's logging.
- **Semantic Caching:** Essential for minimizing re-planning costs during cyclical updates.

### 4. Workflow Shift
| Feature | Current (Nudge) | Alternative (Swarm + IO Loop) |
| :--- | :--- | :--- |
| **Lifecycle** | Long-running, periodic `/clear` | Task-bound persistent workers + IO Loop |
| **State** | Filesystem + context re-injection | **`backlog/` + Session Manifests** |
| **Communication** | Sequential nudges | Async, event-driven updates via `inotify` |
| **Efficiency** | Manual token management | Semantic caching + Per-task budgets |
| **Resumability** | Manual / Re-prime from `GEMINI.md` | **Session ID Persistence & Manifests** |

## Swarm Protocols & Best Practices

1. **Observer Pattern:** Formalize a "Monitor" subagent (or simple script) that scans for changed task files to trigger re-planning or handoffs.
2. **Coordination Overhead:** 
   - Workers: Strictly append-only to implementation notes.
   - Leader: Summarizes progress only at major milestones.
3. **Local Model Consistency:** 
   - Pin model versions (e.g., `llama-3.1:70b-instruct-q4_K_M`).
   - Use standardized "Worker Onboarding" prompts.
4. **Git Safety:** Use **Git Worktrees** for worker isolation to prevent merge conflicts on shared backlog files.

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
