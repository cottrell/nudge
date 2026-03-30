# Agent Usage & Rate Limit Monitoring

The current monitor (C/Python) reactively detects `rate_limited` based on error output (429/529). This note outlines a strategy for proactive usage tracking (e.g., "100% left", "4.5/5.0 hours").

## Research Findings

| Agent | CLI / Tool | Usage Command | Observed UI Pattern |
|-------|------------|---------------|---------------------|
| Claude| Claude Code| `/stats`, `/context` | (usually via interactive session) |
| Codex | aicodex    | `/status`, `/stats` | `gpt-5.4 medium · 100% left` |
| Gemini| Gemini CLI | `/stats model` | `Thinking (0s, 100% left)` |
| Qwen  | Qwen CLI   | `/stats` | ? |
| Vibe  | Mistral Vibe| `vibe stats` | ? |

## Proposal: Global Usage Poller

Since rate limits are often global for an account/plan, we can occasionally poll the status using a separate, non-interactive CLI call.

### 1. New script: `usage-poll.sh`
This script would run in the background (or via a cron/loop) and update a shared JSON file.

```bash
#!/usr/bin/env bash
# Usage: ./usage-poll.sh [interval_secs]
# Updates /tmp/nudge-usage.json with global agent status

while true; do
  # Example: extract '100% left' from aicodex non-interactive status if possible
  # Or use specific subcommands that support JSON output
  # claude stats --json > /tmp/nudge-usage.claude.json
  # aicodex stats --json > /tmp/nudge-usage.codex.json
  # ... combine into /tmp/nudge-usage.json
  sleep 300
done
```

### 2. Monitor Extension (UI Parsing)
The monitor already ingest lines. We can add patterns to `monitor.py` (and `monitor.c`) to extract usage percentage/hours directly from the UI redraws.

```python
# monitor.py extension
USAGE_PATTERNS = {
    'codex': r'(\d+)% left',
    'claude': r'(\d+\.?\d*)/(\d+\.?\d*) hours',
}
```

### 3. CLI Integration
`swarm/cli.py status --brief` can be extended to read the usage info and display it:
`0.0 claude [working] (4.2/5.0h)`
`0.5 codex [idle] (98% left)`

## Next Steps

1. **Verify non-interactive usage commands**: Confirm which CLIs support `stats` or `usage` without entering an interactive loop.
2. **Add `usage` key to monitor state**: Update the `query` method in `monitor.py` and `monitor.c` to return the last parsed usage value.
3. **Update `swarm/cli.py`**: Display usage next to the state if available.
4. **Implement `usage-poll.sh`**: For agents that don't redraw usage in the UI but have a global stats command.
