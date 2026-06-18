# Alt: Thing-Centric Task Sessions

Simple graph-based sessions for agent work. Discrete "Things" (task graphs) with sub-Things, persistence, and a thin Pulse for orchestration. Uses existing CLI harnesses (Claude Code, Codex, Grok, etc.) under subscriptions or local models.

## Core
- **Thing**: Execution graph for a task. Has start/end, can spawn children.
- **Persistence**: `backlog/` (human-visible tasks) + `alt/state/` (fast index, graphs, sessions).
- **Trigger/Pulse**: Stateless loop that launches or nudges Things based on backlog/events. Checks quotas before work.
- **Harness**: Run subscription CLIs (or local) directly where possible. Use base_url overrides only when needed for unification.

## Gateway (optional)
Bifrost or LiteLLM only for:
- Unifying local (Ollama) + selective real APIs (planners/high-value).
- Caching and quotas when using paid models.
- Not required (and often a mismatch) for pure subscription CLI work.

Quotas for subs come from the monitor: each pane's monitor (monitor.c) reports state + usage_pct scraped from terminal (spinners for working, "% left", "X / Y hours" for limits). Pulse queries the unix sockets or /status. `swarm/cli.py usage` can force richer probes.

See bifrost-opinions.md (section 8) for why gateways fit customer API-key systems better than sub-only local tmux swarms. LiteLLM is lighter if you do use real keys.

## Files
- `backlog/`: Tasks.
- `alt/state/`: Graphs, manifests.
- `scripts/`: Dispatch/trigger.
- `config/`: Examples (adapt for gateway or skip).

Start simple: use backlog + state + Pulse. Query monitors for quota headroom before dispatch. Add gateway only if mixing paid APIs.
