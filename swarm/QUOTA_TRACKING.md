# Quota Tracking & EMA Forecasting

This module provides quota status monitoring and EMA-based exhaustion forecasting across all agent providers (Claude, Codex, Antigravity/Gemini).

## Quick Start

### View Current Quota Status
```bash
python3 swarm/cli-quota.py status
```

Shows all quota windows with:
- Percentage remaining (color-coded: 🟢 >30%, 🟡 10-30%, 🔴 <10% or exhausted)
- Reset time for each quota

### View EMA Forecast
```bash
python3 swarm/cli-quota.py forecast
```

Shows:
- Current remaining % per quota
- EMA-based consumption rate (% per hour)
- Hours until exhaustion (ETA)
- Bottleneck quotas (already exhausted or will exhaust first)

### Sample Quotas (Record History)
```bash
python3 swarm/cli-quota.py sample
```

Polls all providers and records current quota state to history database at `/tmp/nudge-quota-history.db`.

### Continuous Monitoring
```bash
python3 swarm/cli-quota.py watch [--interval SECONDS]
```

Monitors quotas continuously (default: 300s interval).

## How It Works

### 1. **All Quota Windows Tracked**

The system tracks distinct quota windows per provider:

| Provider | Windows | Reset Period |
|----------|---------|--------------|
| **Claude** | session, weekly | ~9h session, ~7d weekly |
| **Codex** | 5h, weekly | ~5h, ~7d |
| **Antigravity** | claude_gpt_5h, claude_gpt_weekly, gemini_5h, gemini_weekly | ~5h, ~7d |

### 2. **Remaining % Normalization**

The parser normalizes quota display formats to "% remaining" for consistency:

- **Claude**: Shows "% used" → inverted to "% remaining"
- **Codex**: Shows "% left" directly
- **Antigravity**: Shows "% used" for filled bar → inverted; explicit "% remaining" when available
- **Exhausted quotas** (e.g., "Quota available" with 100% bar) → normalized to 0% remaining

### 3. **EMA Consumption Rate Estimation**

Once historical samples are collected, the system computes:

```
consumption_rate = EMA(samples of % decrease per hour)
hours_until_exhausted = current_remaining / consumption_rate
```

- **EMA factor α = 0.30** — 30% weight on new sample, 70% on history (smooths volatility)
- Reads 24h of history from `/tmp/nudge-quota-history.db`
- Handles irregular sampling intervals

### 4. **Bottleneck Identification**

Flags quotas as **CRITICAL** (worst-case) if:
- Already exhausted (0% remaining)
- Will exhaust in < 30 minutes before reset

Sorted by ETA to show which quota blocks you first.

## Integration Points

### Babysit Loop
Add to your `nudgeswarm/config.yaml` to periodically sample quotas:

```bash
# In nudgeswarm/config.yaml
# (future: add cron or babysit hook to call `python3 swarm/cli-quota.py sample`)
```

### Status Line Integration
Read `/tmp/nudge-quota-forecast.json` in your tmux status line:

```json
{
  "claude": {"session": {"current_pct": 51.0, ...}, "weekly": {...}},
  "codex": {"5h": {...}, "weekly": {...}},
  "agy": {"claude_gpt_five_hour": {...}, ...}
}
```

### Alert System
Bottleneck quotas appear in `format_forecast_report()` and can trigger warnings.

## Files

- **`swarm/usage/quota_tracker.py`** — Core EMA forecasting logic
- **`swarm/cli-quota.py`** — CLI for status/forecast/sampling
- **`/tmp/nudge-quota-history.db`** — SQLite history database
- **`/tmp/nudge-quota-forecast.json`** — Latest forecast (JSON export)
- **`/tmp/nudge-usage-cache.json`** — Cached raw quota scrapes (TTL: 120s)

## Example Output

### Status
```
╭─ Current Quota Status ─────────────────────────────────
  CLAUDE
    🟢 session                         51.0% remaining  Resets: 10:49
    🟢 weekly                          86.0% remaining  Resets: 05:59

  CODEX
    🟢 5h                              98.0% remaining  Resets: 12:52
    🟢 weekly                          54.0% remaining  Resets: 12:14

  AGY
    🔴 claude_gpt_five hour             0.0% remaining  Resets: Exhausted
    🔴 claude_gpt_weekly                0.0% remaining  Resets: Exhausted
    🟢 gemini_five hour               100.0% remaining  Resets: unknown
    🟢 gemini_weekly                   67.0% remaining  Resets: 23:34
╰───────────────────────────────────────────────────────────
```

### Forecast (with Historical Data)
```
╭─ Quota Forecast (EMA-based) ─────────────────────────────

  AGY
    claude_gpt_weekly              45.0% remaining  2.15%/h        21.0h         ✓ OK
    gemini_five hour               80.0% remaining  3.50%/h        22.9h         ✓ OK

  🚨 BOTTLENECK QUOTAS (already exhausted):
    agy/claude_gpt_five hour: EXHAUSTED, resets in 1.0h
    agy/claude_gpt_weekly: EXHAUSTED, resets in 168.0h
```

## Configuration

Tweak EMA parameters in `quota_tracker.py`:

```python
EMA_ALPHA = 0.30        # Sensitivity to new samples (0–1)
```

- **Lower α** (e.g., 0.10) → smoother, less responsive
- **Higher α** (e.g., 0.50) → more responsive, noisier

## Future Enhancements

1. **Babysit Hook** — Integrate sampling into the nudge babysit loop (call `sample` every 5 min)
2. **Alerting** — Warn when quota ETA < reset time
3. **Dashboard** — HTTP endpoint to view forecasts
4. **Multi-machine Aggregation** — Combine quotas across multiple hosts
5. **Pacer Integration** — Adjust nudge frequency based on bottleneck quota
