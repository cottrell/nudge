# Agent Usage & Rate Limit Monitoring

The current monitor (C/Python) reactively detects `rate_limited` based on error output (429/529). This note outlines a strategy for proactive usage tracking (e.g., "100% left", "4.5/5.0 hours").

## Research Findings

| Agent | CLI / Tool | Usage Command | Non-Interactive | Observed UI Pattern |
|-------|------------|---------------|-----------------|---------------------|
| Claude| Claude Code| `/stats`, `/context` | `claude --usage --output-format json` | (in-session: `/stats`) |
| Codex | codex      | `/status`, `/stats` | `codex stats --json`? | `gpt-5.4 medium · 100% left` |
| Gemini| Gemini CLI | `/stats model` | `gemini stats --json`? | `Thinking (0s, 100% left)` |
| Qwen  | Qwen CLI   | `/stats` | ? | ? |
| Vibe  | Mistral Vibe| `vibe stats` | ? | ? |

## Proposal: Global Usage Poller

Since rate limits are often global for an account/plan, we can occasionally poll the status using a separate, non-interactive CLI call. This avoids interfering with active agent panes.

### 1. New script: `usage-poll.sh`
This script runs in the background and updates a shared JSON file.

```bash
#!/usr/bin/env bash
# Usage: ./usage-poll.sh [interval_secs]
# Updates /tmp/nudge-usage.json with global agent status

while true; do
  # 1. Non-interactive path (Preferred)
  # claude --usage --output-format json > /tmp/nudge-usage.claude.json

  # 2. Interactive Scrape (Fallback)
  # If an agent only supports stats via a 'screen' (like Claude's /stats REPL mode),
  # we must be careful not to leave the agent in that screen.
  # 
  # Strategy:
  #   tmux send-keys -t $TARGET "/stats" C-m
  #   sleep 2
  #   tmux capture-pane -t $TARGET -p > /tmp/scrape.txt
  #   tmux send-keys -t $TARGET Escape
  #   (parse /tmp/scrape.txt for usage)

  # 3. Combine into /tmp/nudge-usage.json
  # jq -s 'add' /tmp/nudge-usage.*.json > /tmp/nudge-usage.json

  sleep 300
done
```

### 2. Monitor Extension (UI Parsing)
The monitor (C/Python) can also extract usage from existing UI redraws to provide real-time updates without polling.

```python
# monitor.py extension
USAGE_PATTERNS = {
    'codex': r'(\d+)% left',
    'claude': r'(\d+\.?\d*)/(\d+\.?\d*) hours',
}
```

### 3. CLI Integration
`swarm/cli.py status --brief` will read `/tmp/nudge-usage.json` (or query the monitor socket) and display:
`0.0 claude [working] (4.2/5.0h)`
`0.5 codex [idle] (98% left)`

## Safety Considerations: The "Sticky Screen" Problem

As noted, interactive commands like `/usage` or `/stats` often enter a separate UI buffer. 

- **Avoid in-session polling if possible.** The `claude --usage` non-interactive flag is much safer as it doesn't touch the tmux pane.
- **Escape is mandatory.** If an interactive scrape is used, always send `Escape` (or the agent's "back" key) to return the monitor to a recognizable `idle` or `working` state.
- **Monitor State Awareness.** While the scrape is happening, the monitor will likely report `working` or `unknown`. The babysitter should be configured to ignore these short "admin" bursts.

