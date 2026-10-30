# Babysit quota pacing

When `babysit.enabled: true` and `agent` is `claude`, `codex`, or `agy`, the babysitter samples remaining quota every `quota_probe_secs` seconds (default 300) and uses an exponential moving average (EMA) to pace nudge intervals so quota is spread until the provider reset. YAML `agent: antigravity` is paced as `agy`. agy has three separate quota families (gemini, claude_gpt, argon); a pane is paced by the family its model belongs to, not by the lowest of all three.

This EMA paces nudges. Exhaustion forecasts from sampled history are a different EMA. See `swarm/QUOTA_TRACKING.md`.

- After each nudge the babysitter measures how much quota was consumed (`C = pct_before - pct_after`)
- EMA tracks the mean (`μ`) and variance (`σ`) of consumption per nudge
- Nudge interval: `τ = (time_to_reset × (μ + k_var × σ)) / (quota_remaining × safety)`
- For the first `ema_warmup` nudges the fixed `interval_secs` is used while the EMA warms up
- The quota cache is pre-warmed in a background thread so probes never block the main loop

YAML knobs (all optional, defaults shown):

```yaml
babysit:
  quota_probe_secs: 300   # how often to sample quota
  ema_alpha: 0.30         # smoothing factor (higher = reacts faster)
  ema_safety: 0.92        # target fraction of quota (leaves ~8% buffer)
  ema_k_var: 0.0          # variance weight; raise to 0.5–1.0 for conservative pacing
  ema_warmup: 3           # nudges before EMA replaces fixed interval
  ema_min_wait: 30        # hard floor (seconds)
  ema_max_wait: 1200      # hard ceiling (seconds)
```

The EMA is noisy when multiple swarms share the same provider quota. Each instance estimates its own consumption rate. Overestimation biases toward slower nudging, which is the safer direction when quota is shared.
