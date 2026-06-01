# Shared vs Per-Project Infrastructure

To maintain efficiency on Ubuntu, resources are split between shared global services and per-project session graphs.

## Shared Infrastructure (Run Once)
These services run globally and provide a unified API for all project swarms.
- **LLM Gateway (Bifrost/LiteLLM):** Manages API keys, global rate limits, and cross-project **Semantic Caching**.
- **Local Inference (Ollama/vLLM):** Hosts models like Llama 3 or Qwen 2.5 on a single GPU/CPU pool.
- **Global Logs:** Centralized audit trail for all agent interactions.

## Per-Project Infrastructure (Run in `./alt`)
These components are unique to the `nudge` project.
- **Task Board (`backlog/`):** Project-specific goals and task states.
- **Trigger Loop (`alt/scripts/trigger_loop.sh`):** Monitors this project's backlog to launch specific "Things".
- **Session Manifests (`alt/state/`):** Persistent logs and `session_id` mapping for this project's DAG.
- **Smug Config (`alt/ops.yaml`):** Defines the local 3x2 grid for this project's agent roles.

## Running the Swarm
1.  Ensure Shared Infra is up (Ollama + Bifrost).
2.  Run `smug start -f alt/ops.yaml`.
3.  The **Trigger Loop** pane will automatically start watching the local backlog.
