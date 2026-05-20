#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys

import topology as swarm_topology
import babysitctl as swarm_babysit
import init as swarm_init
from common import load_config


MODEL_HELPERS = {
    "codex": {
        "command": "codex",
        "list": ["codex", "debug", "models"],
        "run": "codex -m <model>",
        "swarm": (
            "codex --dangerously-bypass-approvals-and-sandbox -m <model>"
        ),
    },
    "claude": {
        "command": "claude",
        "help": ["claude", "--help"],
        "run": "claude --model <model>",
        "swarm": "claude --dangerously-skip-permissions --model <model>",
    },
    "gemini": {
        "command": "gemini",
        "help": ["gemini", "--help"],
        "run": "gemini -m <model>",
        "swarm": "gemini -y -m <model>",
    },
    "qwen": {
        "command": "qwen",
        "help": ["qwen", "--help"],
        "run": "qwen -m <model>",
        "swarm": "qwen -y -m <model>",
    },
    "vibe": {
        "command": "vibe",
        "help": ["vibe", "--help"],
        "run": "VIBE_ACTIVE_MODEL=<model> vibe",
        "swarm": "VIBE_ACTIVE_MODEL=<model> vibe --agent auto-approve",
    },
}


def _run_capture(
    argv: list[str],
    timeout: float = 5.0,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
    )


def _codex_models() -> tuple[list[str], str | None]:
    proc = _run_capture(MODEL_HELPERS["codex"]["list"])
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or "command failed").strip()
        return [], msg
    try:
        data = json.loads(proc.stdout)
        models = [
            m["slug"]
            for m in data.get("models", [])
            if m.get("visibility") == "list" and m.get("slug")
        ]
    except (json.JSONDecodeError, TypeError, KeyError) as e:
        return [], f"could not parse codex debug models: {e}"
    return models, None


def _model_flag_status(helper: dict[str, object]) -> str:
    help_argv = helper.get("help")
    if not isinstance(help_argv, list):
        return ""
    proc = _run_capture(help_argv)
    text = f"{proc.stdout}\n{proc.stderr}"
    if "--model" in text or "-m," in text:
        return "model flag: detected in --help"
    if "VIBE_ACTIVE_MODEL" in text:
        return "model config: detected VIBE_ACTIVE_MODEL in --help"
    return "model flag: not found in --help"


def print_model_help() -> None:
    print("Model selection helpers")
    print()
    print("Use these in swarm YAML under pane shell_command.")
    print("Commands are probed from the CLIs installed on this machine.")
    print()

    for name, helper in MODEL_HELPERS.items():
        command = str(helper["command"])
        installed = shutil.which(command) is not None
        print(f"{name}:")
        if not installed:
            print(f"  installed: no ({command} not found)")
            print()
            continue

        print(f"  installed: yes ({shutil.which(command)})")
        if name == "codex":
            list_cmd = " ".join(str(p) for p in helper["list"])
            print(f"  list: {list_cmd}")
            models, error = _codex_models()
            if error:
                print(f"  models: unavailable ({error})")
            elif models:
                print("  models:")
                for model in models:
                    print(f"    {model}")
            else:
                print("  models: none returned")
        else:
            status = _model_flag_status(helper)
            if status:
                print(f"  {status}")
            print("  list: no list-models command exposed by --help")

        print(f"  run: {helper['run']}")
        print(f"  swarm YAML: shell_command: \"{helper['swarm']}\"")
        print()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Unified CLI for config-driven tmux swarm workflows.")
    sub = parser.add_subparsers(dest="command", required=True)

    init_p = sub.add_parser("init", help="Create a starter swarm config and AGENTS.md block")
    init_p.add_argument("name", help="Swarm/session name")
    init_p.add_argument("--root", default=".", help="Project root to initialize, default current directory")
    init_p.add_argument("--agents", default="codex,claude,gemini", help="Comma-separated list of agents (repeats allowed), default codex,claude,gemini")
    init_p.add_argument("-D", "--dry-run", action="store_true", help="Print planned files and AGENTS.md block without writing")

    apply_p = sub.add_parser("apply", help="Apply tmux topology, monitors, titles, and initial commands")
    apply_p.add_argument("config", help="Path to YAML config")
    apply_p.add_argument("-D", "--dry-run", action="store_true", help="Validate and print actions without changing tmux; still writes runtime notes")
    apply_p.add_argument("-a", "--attach", action="store_true", help="Attach to the tmux session after apply")
    apply_p.add_argument("--skip-grid", action="store_true", help="Skip session/pane creation (use after tmuxp load)")

    status_p = sub.add_parser("status", help="Report current swarm state")
    status_p.add_argument("config", help="Path to YAML config")
    status_p.add_argument("-b", "--brief", action="store_true", help="Print a compact per-pane state view")
    status_p.add_argument("-w", "--watch", action="store_true", help="Refresh the status in place until interrupted")
    status_p.add_argument("-i", "--interval", type=float, default=1.0, help="Watch refresh interval in seconds")

    broadcast_p = sub.add_parser("broadcast", help="Send an immediate message to swarm panes")
    broadcast_p.add_argument("config", help="Path to YAML config")
    broadcast_p.add_argument("message", nargs="+", help="Broadcast message text")
    broadcast_p.add_argument("-A", "--include-nonmonitored", action="store_true", help="Also send to panes with monitor=false")
    broadcast_p.add_argument("-D", "--dry-run", action="store_true", help="Print targets without sending")

    usage_p = sub.add_parser("usage", aliases=["probe"], help="Send stats command to all monitored panes to refresh usage info")
    usage_p.add_argument("config", help="Path to YAML config")
    usage_p.add_argument("-D", "--dry-run", action="store_true", help="Print targets without sending")

    sub.add_parser(
        "help",
        aliases=["models"],
        help="Show probed model selection commands for agent CLIs",
    )

    capture_p = sub.add_parser("capture", help="Dump and classify current pane content")
    capture_p.add_argument("config", help="Path to YAML config")
    capture_p.add_argument("pane", help="Pane index (e.g. 0.0)")

    babysit_p = sub.add_parser("babysit", help="Manage config-driven babysit workers")
    babysit_sub = babysit_p.add_subparsers(dest="babysit_command", required=True)
    for name in ("apply", "status", "stop"):
        sp = babysit_sub.add_parser(name, help=f"Babysit {name}")
        sp.add_argument("config", help="Path to YAML config")
        if name != "status":
            sp.add_argument("-D", "--dry-run", action="store_true", help="Validate and print actions without changing workers; apply still writes runtime notes")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "init":
            agents = [a.strip() for a in args.agents.split(",") if a.strip()]
            swarm_init.init(args.name, args.root, args.dry_run, agents)
            return 0

        if args.command == "apply":
            cfg = load_config(args.config)
            swarm_topology.apply(cfg, args.dry_run, skip_grid=args.skip_grid)
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

        if args.command in ("help", "models"):
            print_model_help()
            return 0

        if args.command == "capture":
            cfg = load_config(args.config)
            swarm_topology.capture_and_classify(cfg, args.pane)
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
