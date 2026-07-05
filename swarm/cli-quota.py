#!/usr/bin/env python3
"""
CLI for quota status and forecasting.

Usage:
    python cli-quota.py sample          # Sample all providers (saves to history DB)
    python cli-quota.py status          # Show current quota status
    python cli-quota.py forecast        # Show EMA-based exhaustion forecast
    python cli-quota.py watch [interval] # Continuously monitor quotas
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Add swarm to path
SWARM_DIR = Path(__file__).parent
sys.path.insert(0, str(SWARM_DIR))

from usage.quota_tracker import (
    sample_all_providers, format_forecast_report, get_recent_samples,
    init_quota_db
)
from common import get_cached_provider_usage


def cmd_sample() -> None:
    """Sample all providers and record to history DB."""
    print("Sampling quota status from all providers...")
    forecasts = sample_all_providers(force_refresh=True)
    if not forecasts:
        print("No quota data available.")
        return
    print(f"Sampled {sum(len(f) for f in forecasts.values())} quota windows.")


def cmd_status() -> None:
    """Show current quota status."""
    print("\n╭─ Current Quota Status ─────────────────────────────────")
    providers = ["claude", "codex", "agy"]

    for provider in providers:
        data = get_cached_provider_usage(provider, force=False)
        limits = data.get("limits", [])
        if not limits:
            continue

        print(f"\n  {provider.upper()}")
        for limit in sorted(limits, key=lambda l: l.get("label")):
            label = limit.get("label", "?")
            pct = limit.get("pct", 0)
            reset = limit.get("reset", "")
            reset_ts = limit.get("reset_ts", 0)

            if reset_ts > int(time.time()):
                from datetime import datetime
                reset_display = datetime.fromtimestamp(reset_ts).strftime("%H:%M")
            else:
                reset_display = reset or "unknown"

            status = "🔴" if pct < 10 else "🟡" if pct < 30 else "🟢"
            print(f"    {status} {label:30} {pct:5.1f}% remaining  Resets: {reset_display}")

    print("\n╰───────────────────────────────────────────────────────────")


def cmd_forecast() -> None:
    """Show EMA-based exhaustion forecast."""
    print("\nRunning quota forecast...")
    init_quota_db()
    forecasts = sample_all_providers(force_refresh=False)

    if not forecasts:
        print("No historical quota data yet. Run 'sample' first.")
        return

    report = format_forecast_report(forecasts)
    print(report)


def cmd_watch(interval: int = 300) -> None:
    """Continuously monitor quotas."""
    print(f"Watching quotas every {interval}s (Ctrl+C to exit)...\n")
    try:
        while True:
            cmd_status()
            print(f"\nNext sample in {interval}s...")
            time.sleep(interval)
            cmd_sample()
    except KeyboardInterrupt:
        print("\n\nQuota watch stopped.")
        sys.exit(0)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Quota status and forecasting CLI"
    )
    subparsers = parser.add_subparsers(dest="cmd", help="Command to run")

    subparsers.add_parser("sample", help="Sample all providers and record to history")
    subparsers.add_parser("status", help="Show current quota status")
    subparsers.add_parser("forecast", help="Show EMA-based exhaustion forecast")

    watch_parser = subparsers.add_parser(
        "watch",
        help="Continuously monitor quotas"
    )
    watch_parser.add_argument(
        "--interval", type=int, default=300,
        help="Sample interval in seconds (default: 300)"
    )

    args = parser.parse_args()

    if args.cmd == "sample":
        cmd_sample()
    elif args.cmd == "status":
        cmd_status()
    elif args.cmd == "forecast":
        cmd_forecast()
    elif args.cmd == "watch":
        cmd_watch(args.interval)
    else:
        # Default to status if no command given
        cmd_status()


if __name__ == "__main__":
    main()
