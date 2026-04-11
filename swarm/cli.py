#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys

import topology as swarm_topology
import babysitctl as swarm_babysit
import init as swarm_init
from common import load_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Unified CLI for config-driven tmux swarm workflows.")
    sub = parser.add_subparsers(dest="command", required=True)

    init_p = sub.add_parser("init", help="Create a starter swarm config and AGENTS.md block")
    init_p.add_argument("name", help="Swarm/session name")
    init_p.add_argument("--root", default=".", help="Project root to initialize, default current directory")
    init_p.add_argument("-n", "--dry-run", action="store_true", help="Print planned files and AGENTS.md block without writing")

    apply_p = sub.add_parser("apply", help="Apply tmux topology, monitors, titles, and initial commands")
    apply_p.add_argument("config", help="Path to YAML config")
    apply_p.add_argument("-n", "--dry-run", action="store_true", help="Validate and print actions without changing tmux")
    apply_p.add_argument("-a", "--attach", action="store_true", help="Attach to the tmux session after apply")

    status_p = sub.add_parser("status", help="Report current swarm state")
    status_p.add_argument("config", help="Path to YAML config")
    status_p.add_argument("-b", "--brief", action="store_true", help="Print a compact per-pane state view")
    status_p.add_argument("-w", "--watch", action="store_true", help="Refresh the status in place until interrupted")
    status_p.add_argument("-i", "--interval", type=float, default=1.0, help="Watch refresh interval in seconds")

    broadcast_p = sub.add_parser("broadcast", help="Send an immediate message to swarm panes")
    broadcast_p.add_argument("config", help="Path to YAML config")
    broadcast_p.add_argument("message", nargs="+", help="Broadcast message text")
    broadcast_p.add_argument("-A", "--include-nonmonitored", action="store_true", help="Also send to panes with monitor=false")
    broadcast_p.add_argument("-n", "--dry-run", action="store_true", help="Print targets without sending")

    usage_p = sub.add_parser("usage", help="Send stats command to all monitored panes to refresh usage info")
    usage_p.add_argument("config", help="Path to YAML config")
    usage_p.add_argument("-n", "--dry-run", action="store_true", help="Print targets without sending")

    babysit_p = sub.add_parser("babysit", help="Manage config-driven babysit workers")
    babysit_sub = babysit_p.add_subparsers(dest="babysit_command", required=True)
    for name in ("apply", "status", "stop"):
        sp = babysit_sub.add_parser(name, help=f"Babysit {name}")
        sp.add_argument("config", help="Path to YAML config")
        if name != "status":
            sp.add_argument("-n", "--dry-run", action="store_true", help="Validate and print actions without changing workers")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "init":
            swarm_init.init(args.name, args.root, args.dry_run)
            return 0

        if args.command == "apply":
            cfg = load_config(args.config)
            swarm_topology.apply(cfg, args.dry_run)
            if args.attach and not args.dry_run:
                subprocess.run(["tmux", "attach", "-t", cfg.session_name], check=True, text=True)
            return 0

        if args.command == "status":
            cfg = load_config(args.config)
            if args.interval <= 0:
                raise ValueError("--interval must be > 0")
            if args.watch:
                swarm_topology.watch_status(cfg, args.brief, args.interval)
            else:
                swarm_topology.print_status(cfg, args.brief)
            return 0

        if args.command == "usage":
            cfg = load_config(args.config)
            swarm_topology.probe_usage(cfg, args.dry_run)
            return 0

        if args.command == "broadcast":
            cfg = load_config(args.config)
            swarm_topology.broadcast(cfg, " ".join(args.message), args.include_nonmonitored, args.dry_run)
            return 0

        cfg = load_config(args.config)
        if args.babysit_command == "apply":
            swarm_babysit.apply(cfg, args.dry_run)
        elif args.babysit_command == "stop":
            swarm_babysit.stop(cfg, args.dry_run)
        else:
            swarm_babysit.status(cfg)
        return 0
    except Exception as e:
        print(str(e), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
