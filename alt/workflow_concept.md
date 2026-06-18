# Alt: Minimal Session-Based Swarm

Core: Run subscription CLI agents (Claude Code, Codex, etc.) or local models as nodes in resumable "Thing" graphs. Use backlog + state for persistence. Thin Pulse for trigger/revive/dispatch based on events and quotas.

No mandatory gateway for pure-sub work — the CLIs already handle auth/limits. Add LiteLLM (or Bifrost if using real keys) only for unifying when mixing in paid APIs or for caching.

See README.md for the architecture. Workflow and ClawTeam are optional experiments.
