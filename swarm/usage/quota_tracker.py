#!/usr/bin/env python3
"""
EMA-based quota tracking and forecasting.

Stores quota samples over time and predicts when each quota window will be exhausted
using exponential moving average (EMA) for consumption rate estimation.
"""
from __future__ import annotations

import sqlite3 as _sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
import json
from typing import Optional
import time

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from common import get_cached_provider_usage, parse_provider_usage


DB_PATH = Path("/tmp/nudge-quota-history.db")
EMA_ALPHA = 0.30  # Exponential moving average factor (30% weight on new sample, 70% on history)


@dataclass
class QuotaSample:
    """A point-in-time quota observation."""
    provider: str
    quota_label: str
    pct_remaining: float
    reset_ts: int
    reset_iso: str
    sampled_at: int  # unix timestamp


@dataclass
class QuotaForecast:
    """Prediction of when a quota will exhaust."""
    provider: str
    quota_label: str
    current_pct: float
    consumption_rate_pct_per_hour: float
    hours_until_exhausted: Optional[float]  # None if already exhausted or rate is 0
    reset_ts: int
    reset_iso: str
    is_critical: bool  # True if will exhaust before reset
    sampled_at_iso: str


def init_quota_db() -> Path:
    """Initialize the quota history database."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _sqlite3.connect(str(DB_PATH)) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS quota_samples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider TEXT NOT NULL,
                quota_label TEXT NOT NULL,
                pct_remaining REAL NOT NULL,
                reset_ts INTEGER NOT NULL,
                reset_iso TEXT,
                sampled_at INTEGER NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_provider_label_time
            ON quota_samples(provider, quota_label, sampled_at)
        """)
    return DB_PATH


def record_quota_sample(sample: QuotaSample) -> None:
    """Store a quota observation in the database."""
    with _sqlite3.connect(str(DB_PATH)) as conn:
        conn.execute(
            """INSERT INTO quota_samples
               (provider, quota_label, pct_remaining, reset_ts, reset_iso, sampled_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (sample.provider, sample.quota_label, sample.pct_remaining,
             sample.reset_ts, sample.reset_iso, sample.sampled_at)
        )


def get_recent_samples(provider: str, quota_label: str, hours: int = 24) -> list[QuotaSample]:
    """Get the last N hours of samples for a quota."""
    cutoff = int(time.time()) - (hours * 3600)
    with _sqlite3.connect(str(DB_PATH)) as conn:
        cur = conn.execute(
            """SELECT provider, quota_label, pct_remaining, reset_ts, reset_iso, sampled_at
               FROM quota_samples
               WHERE provider = ? AND quota_label = ? AND sampled_at >= ?
               ORDER BY sampled_at ASC""",
            (provider, quota_label, cutoff)
        )
        return [
            QuotaSample(provider=row[0], quota_label=row[1], pct_remaining=row[2],
                       reset_ts=row[3], reset_iso=row[4], sampled_at=row[5])
            for row in cur.fetchall()
        ]


def compute_ema_rate(samples: list[QuotaSample]) -> Optional[float]:
    """
    Compute EMA-based consumption rate (% per hour).
    Returns None if insufficient data or no consumption.

    Assumes pct_remaining decreases over time (higher % remaining = less consumed).
    Returns negative rate if consumption is increasing (quota getting used up).
    """
    if len(samples) < 2:
        return None

    # Compute consumption deltas between consecutive samples
    deltas_per_hour = []
    for i in range(1, len(samples)):
        prev, curr = samples[i-1], samples[i]
        time_delta_hours = (curr.sampled_at - prev.sampled_at) / 3600.0
        if time_delta_hours < 0.01:  # Skip if too close in time
            continue

        # Consumption = decrease in remaining (negative value means quota is being used)
        pct_consumption = prev.pct_remaining - curr.pct_remaining
        rate = pct_consumption / time_delta_hours
        deltas_per_hour.append(rate)

    if not deltas_per_hour:
        return None

    # Compute EMA of the rates
    ema = deltas_per_hour[0]
    for rate in deltas_per_hour[1:]:
        ema = EMA_ALPHA * rate + (1 - EMA_ALPHA) * ema

    return ema


def _infer_reset_time(quota_label: str, reset_ts: int) -> int:
    """
    If reset_ts is 0 or missing, infer based on quota label patterns.
    """
    if reset_ts > 0:
        return reset_ts

    now = int(time.time())
    # Heuristics for standard windows
    if "five_hour" in quota_label.lower() or "5h" in quota_label.lower():
        return now + (5 * 3600)
    elif "weekly" in quota_label.lower():
        return now + (7 * 24 * 3600)
    elif "daily" in quota_label.lower():
        return now + (24 * 3600)
    # Default: assume it's a session quota that resets soon
    return now + 3600


def forecast_quota_exhaustion(provider: str, quota_label: str,
                              current_pct: float, reset_ts: int,
                              reset_iso: str) -> QuotaForecast:
    """
    Forecast when a quota will be exhausted based on EMA consumption rate.
    """
    now = int(time.time())
    reset_ts = _infer_reset_time(quota_label, reset_ts)
    hours_until_reset = max(0, (reset_ts - now) / 3600.0)

    # Fetch recent samples to compute consumption rate
    samples = get_recent_samples(provider, quota_label, hours=24)
    consumption_rate = compute_ema_rate(samples) or 0.0

    hours_until_exhausted = None
    if consumption_rate > 0:  # Quota is being consumed
        hours_until_exhausted = current_pct / consumption_rate

    # Critical if: already exhausted, or will exhaust in < 0.5h before reset
    is_critical = (
        current_pct <= 0 or
        (hours_until_exhausted is not None and
         hours_until_exhausted < hours_until_reset and
         hours_until_exhausted < 0.5)
    )

    return QuotaForecast(
        provider=provider,
        quota_label=quota_label,
        current_pct=current_pct,
        consumption_rate_pct_per_hour=consumption_rate,
        hours_until_exhausted=hours_until_exhausted,
        reset_ts=reset_ts,
        reset_iso=reset_iso,
        is_critical=is_critical,
        sampled_at_iso=datetime.now().isoformat()
    )


def sample_all_providers(force_refresh: bool = False) -> dict:
    """
    Poll all available providers for current quota state and record samples.
    Returns a dict of {provider: {quota_label: forecast}}.
    """
    init_quota_db()

    providers_to_check = ["claude", "codex", "agy"]
    results = {}
    now = int(time.time())

    for provider in providers_to_check:
        usage_data = get_cached_provider_usage(provider, force=force_refresh)
        if "error" in usage_data and "raw_text" not in usage_data:
            continue

        limits = usage_data.get("limits", [])
        forecasts = {}

        for limit in limits:
            label = limit.get("label", "unknown")
            pct = limit.get("pct", 0)
            reset = limit.get("reset_iso", "")
            reset_ts = limit.get("reset_ts", 0)

            # Record the sample
            sample = QuotaSample(
                provider=provider,
                quota_label=label,
                pct_remaining=pct,
                reset_ts=reset_ts,
                reset_iso=reset,
                sampled_at=now
            )
            record_quota_sample(sample)

            # Forecast exhaustion
            forecast = forecast_quota_exhaustion(provider, label, pct, reset_ts, reset)
            forecasts[label] = forecast

        if forecasts:
            results[provider] = forecasts

    return results


def format_forecast_report(forecasts_by_provider: dict) -> str:
    """Format forecast data as human-readable report."""
    lines = [
        "╭─ Quota Forecast (EMA-based) ─────────────────────────────",
        "",
    ]

    critical_quotas = []

    for provider in sorted(forecasts_by_provider.keys()):
        lines.append(f"  {provider.upper()}")
        forecasts = forecasts_by_provider[provider]

        for label in sorted(forecasts.keys()):
            f = forecasts[label]

            # Build status line
            status = "⚠ CRITICAL" if f.is_critical else "✓ OK"

            rate_str = f"{f.consumption_rate_pct_per_hour:.2f}%/h" if f.consumption_rate_pct_per_hour > 0 else "—"

            if f.hours_until_exhausted is not None:
                eta_str = f"{f.hours_until_exhausted:.1f}h"
            else:
                eta_str = "—" if f.consumption_rate_pct_per_hour <= 0 else "∞"

            lines.append(
                f"    {label:30} {f.current_pct:5.1f}% remaining  {rate_str:10}  ETA: {eta_str:8}  {status}"
            )

            if f.is_critical:
                critical_quotas.append(f)

        lines.append("")

    if critical_quotas:
        lines.append("  🚨 BOTTLENECK QUOTAS (already exhausted or will exhaust before reset):")
        for f in sorted(critical_quotas, key=lambda x: x.hours_until_exhausted or float('inf')):
            reset_in = f"{(f.reset_ts - int(time.time())) / 3600:.1f}h"
            if f.current_pct <= 0:
                status_line = f"    {f.provider}/{f.quota_label}: EXHAUSTED, resets in {reset_in}"
            elif f.hours_until_exhausted is not None:
                status_line = (
                    f"    {f.provider}/{f.quota_label}: {f.hours_until_exhausted:.1f}h until empty, "
                    f"resets in {reset_in}"
                )
            else:
                status_line = f"    {f.provider}/{f.quota_label}: unknown ETA, resets in {reset_in}"
            lines.append(status_line)

    lines.append("╰───────────────────────────────────────────────────────────")
    return "\n".join(lines)


if __name__ == "__main__":
    init_quota_db()
    forecasts = sample_all_providers(force_refresh=True)
    report = format_forecast_report(forecasts)
    print(report)

    # Also output raw forecast data as JSON
    export = {}
    for provider, fcast_dict in forecasts.items():
        export[provider] = {
            label: {
                "current_pct": f.current_pct,
                "consumption_rate_pct_per_hour": f.consumption_rate_pct_per_hour,
                "hours_until_exhausted": f.hours_until_exhausted,
                "is_critical": f.is_critical,
                "reset_iso": f.reset_iso,
            }
            for label, f in fcast_dict.items()
        }

    with open("/tmp/nudge-quota-forecast.json", "w") as f:
        json.dump(export, f, indent=2)

    print(f"\nForecast saved to /tmp/nudge-quota-forecast.json")
