# Shared vs Per-Project Infrastructure

## Shared (optional)
- Local models via Ollama/vLLM.
- (optional) LiteLLM (preferred over Bifrost here) only when mixing real paid APIs for caching/routing. Not for pure sub CLIs.
- Keep simple — not required.

Quotas: observed from monitor sockets (see README).

## Per-Project (in `./alt`)
- `backlog/`: Tasks.
- `alt/state/`: Graphs + session data.
- Trigger/Pulse logic.
- Your ops config.

Run harnesses directly with subscriptions for workers. Use per-pane monitors + `swarm/cli.py usage` for quota signals into Pulse. Add gateway only for API unification.
