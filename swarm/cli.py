#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys

# Relative imports (for `python -m swarm.cli`) with bare fallback for direct
# `python swarm/cli.py` / aiswarm (avoids "relative import with no known parent").
try:
    from . import topology as swarm_topology
    from . import babysitctl as swarm_babysit
    from . import init as swarm_init
    from .common import load_config
except ImportError:
    # direct script fallback (python swarm/cli.py or aiswarm alias)
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
    "grok": {
        "command": "grok",
        "help": ["grok", "--help"],
        "list": ["grok", "models"],
        "run": "grok -m <model>",
        "swarm": "grok --always-approve -m <model>",
    },
    "antigravity": {
        "command": "agy",
        "help": ["agy", "--help"],
        "run": "agy -m <model>",
        "swarm": "agy --dangerously-skip-permissions -m <model>",
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


def _stop_tmux_session(session_name: str, dry_run: bool) -> None:
    if dry_run:
        print(f"would stop tmux session {session_name}")
        return
    proc = subprocess.run(
        ["tmux", "has-session", "-t", f"={session_name}"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    if proc.returncode == 0:
        subprocess.run(["tmux", "kill-session", "-t", session_name], check=False, text=True)


def _grok_models() -> tuple[list[str], str | None]:
    proc = _run_capture(MODEL_HELPERS["grok"]["list"])
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or "command failed").strip()
        return [], msg
    models: list[str] = []
    for line in proc.stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith(("- ", "* ")):
            model = stripped.lstrip("-* ").split()[0]
            if model:
                models.append(model)
    if not models:
        return [], "could not parse grok models output"
    return models, None


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
        if name in {"codex", "grok"}:
            list_cmd = " ".join(str(p) for p in helper["list"])
            print(f"  list: {list_cmd}")
            models_fn = _codex_models if name == "codex" else _grok_models
            models, error = models_fn()
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
    init_p.add_argument("--agents", default="codex,claude,antigravity,grok", help="Comma-separated list of agents (repeats allowed), default codex,claude,antigravity,grok")
    init_p.add_argument("--flavour", default="3x2", choices=["2x2", "3x2"], help="Pane flavour: NxM where N=agents, M=instances (heavy+light). Default: 1 pane per agent")
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

    broadcast_p = sub.add_parser("broadcast", help="Send an immediate message to swarm agent panes (flavours: tmux or log)")
    broadcast_p.add_argument("config", help="Path to YAML config")
    broadcast_p.add_argument("message", nargs="+", help="Broadcast message text")
    broadcast_p.add_argument("-A", "--include-nonmonitored", action="store_true", help="Also send to agent panes with monitor=false")
    broadcast_p.add_argument("-D", "--dry-run", action="store_true", help="Print targets without sending")
    broadcast_p.add_argument("--via-log", action="store_true", help="Write to event log instead of direct tmux-send (consumer will deliver)")

    stop_p = sub.add_parser("stop", help="Stop babysit workers and the tmux session")
    stop_p.add_argument("config", help="Path to YAML config")
    stop_p.add_argument("-D", "--dry-run", action="store_true", help="Print planned stop actions without changing tmux or workers")

    clear_p = sub.add_parser("clear-comms", help="Clear the event log for a session (destructive)")
    clear_p.add_argument("config", help="Path to YAML config")
    clear_p.add_argument("-y", "--yes", action="store_true", help="Skip 'y' confirmation")

    log_p = sub.add_parser("log", help="Inspect the comms event log (events + cursors)")
    log_p.add_argument("config", help="Path to YAML config")
    log_p.add_argument("--pane", help="Filter to a specific pane e.g. 0.2")
    log_p.add_argument("-n", "--limit", type=int, default=50)
    log_p.add_argument("--pending", action="store_true", help="Only show unread events for the given --pane (or summarize)")

    send_p = sub.add_parser("send", help="Send a message to a single target via the event log (instead of direct tmux-send)", description="Send a message to a single target via the event log (instead of direct tmux-send)")
    send_p.add_argument("config", help="Path to YAML config")
    send_p.add_argument("target", help="Recipient pane id e.g. 0.2 or __broadcast__")
    send_p.add_argument("message", nargs="+", help="Message text")
    send_p.add_argument("-D", "--dry-run", action="store_true", help="Print action without sending")

    avu_p = sub.add_parser("av-usage", help="Agentsview usage (global by default; provide a swarm config to limit to its agents)")
    avu_p.add_argument("config", nargs="?", default=None, help="Optional path to YAML config (limits report to the agents declared in it)")
    avu_p.add_argument("--json", action="store_true", help="Emit JSON")
    avu_p.add_argument("--recent", type=int, default=0, metavar="MIN", help="Include rolling tokens for last N minutes (in addition)")
    avu_p.add_argument("-w", "--watch", action="store_true", help="Refresh the report in place until interrupted")
    avu_p.add_argument("-i", "--interval", type=float, default=30.0, help="Watch refresh interval in seconds (default: 30)")

    quota_p = sub.add_parser("quota", help="Get cached/live provider account quotas")
    quota_p.add_argument("config", nargs="?", default=None, help="Optional path to YAML config (limits report to the agents declared in it)")
    quota_p.add_argument("--ttl", type=int, default=600, help="Cache TTL in seconds")
    quota_p.add_argument("--force", action="store_true", help="Force refresh")
    quota_p.add_argument("-w", "--watch", action="store_true", help="Refresh in place until interrupted")
    quota_p.add_argument("-i", "--interval", type=float, default=2.0, help="Watch refresh interval in seconds")

    quota_debug_p = sub.add_parser("quota-debug", aliases=["quota-debug", "quota_debug"], help="Show raw and parsed usage details for a chosen agent")
    quota_debug_p.add_argument("agent", choices=["claude", "codex", "agy"], help="Agent to debug")
    quota_debug_p.add_argument("--ttl", type=int, default=120, help="Cache TTL in seconds")
    quota_debug_p.add_argument("--force", action="store_true", help="Force refresh")

    sub.add_parser(
        "help",
        aliases=["models"],
        help="Show probed model selection commands for agent CLIs",
    )

    capture_p = sub.add_parser("capture", help="Dump current pane content")
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
            swarm_init.init(args.name, args.root, args.dry_run, agents, flavour=args.flavour)
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

        if args.command == "quota":
            try:
                from .common import get_cached_provider_usage, get_agents_from_config, QUOTA_AGENT_MAP
            except ImportError:
                from common import get_cached_provider_usage, get_agents_from_config, QUOTA_AGENT_MAP
            import time
            if args.config:
                cfg = load_config(args.config)
                agents = get_agents_from_config(cfg)
            else:
                agents = ["claude", "codex", "agy"]
            agents = [QUOTA_AGENT_MAP.get(a, a) for a in agents]
            agents = [a for a in agents if a in {"claude", "codex", "agy"}]
            if not agents:
                print("No supported quota agents (claude, codex, agy) found.")
                return 0

            def render_all_quotas():
                out_lines = []
                for agent in agents:
                    res = get_cached_provider_usage(agent, ttl=args.ttl, force=args.force)
                    out_lines.append(f"=== {agent.upper()} ===")
                    if "error" in res:
                        out_lines.append(f"  Error: {res['error']}")
                    else:
                        fetched_at_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(res.get("fetched_at", 0)))
                        out_lines.append(f"  Fetched at: {fetched_at_str}")
                        if "warning" in res:
                            out_lines.append(f"  Warning: {res['warning']}")
                        parsed = res.get("parsed") or {}
                        if agent == "claude" and parsed.get("cost") is not None:
                            out_lines.append(f"  Cost: ${parsed['cost']:.4f}")
                        if agent == "codex" and parsed.get("model"):
                            out_lines.append(f"  Model: {parsed['model']}")
                        limits = res.get("limits", [])
                        if limits:
                            for lim in limits:
                                lbl = f"{lim['label']}: " if lim['label'] else ""
                                reset_str = f" (resets {lim['reset']})" if lim['reset'] else ""
                                out_lines.append(f"  - {lbl}{lim['pct']}%{reset_str}")
                        else:
                            out_lines.append("  - No active limits found.")
                    out_lines.append("")
                return "\n".join(out_lines)

            if args.watch:
                if args.interval <= 0:
                    raise ValueError("--interval must be > 0")
                try:
                    while True:
                        output_text = render_all_quotas()
                        sys.stdout.write("\x1b[H\x1b[2J")
                        sys.stdout.write(f"watch quota ttl={args.ttl}s updated={time.strftime('%H:%M:%S')}\n\n")
                        sys.stdout.write(output_text)
                        sys.stdout.flush()
                        time.sleep(args.interval)
                except KeyboardInterrupt:
                    return 0
            else:
                print(render_all_quotas())
                return 0

        if args.command == "quota-debug":
            try:
                from .common import get_cached_provider_usage
            except ImportError:
                from common import get_cached_provider_usage
            import json as _json
            res = get_cached_provider_usage(args.agent, ttl=args.ttl, force=args.force)
            print("=== RAW SCRAPER OUTPUT ===")
            print(res.get("raw_text", ""))
            print("\n=== PARSED STRUCTURED JSON ===")
            print(_json.dumps(res.get("parsed", {}), indent=2))
            return 0


        if args.command == "av-usage":
            try:
                from .common import get_agents_from_config, get_swarm_agentsview_report
            except ImportError:
                from common import get_agents_from_config, get_swarm_agentsview_report
            import json as _json

            if args.config:
                cfg = load_config(args.config)
                agents = get_agents_from_config(cfg)
            else:
                agents = None

            report = get_swarm_agentsview_report(agents)

            if args.json:
                if args.watch:
                    print("error: --json cannot be used with --watch", file=sys.stderr)
                    return 1
                print(_json.dumps(report, indent=2, default=str))
                return 0

            effective = report.get("agents") or []
            if args.watch:
                swarm_topology.watch_av_usage(agents, args.recent, args.interval)
                return 0

            title = f"agentsview usage limited to swarm agents: {effective}" if args.config else "agentsview global usage (all agents)"
            lines = swarm_topology.av_usage_lines(report, recent_minutes=args.recent, title=title)
            print("\n".join(lines))
            return 0

        if args.command in ("help", "models"):
            print_model_help()
            return 0

        if args.command == "capture":
            cfg = load_config(args.config)
            swarm_topology.capture_pane(cfg, args.pane)
            return 0

        if args.command == "broadcast":
            cfg = load_config(args.config)
            swarm_topology.broadcast(cfg, " ".join(args.message), args.include_nonmonitored, args.dry_run, via_log=args.via_log)
            return 0

        if args.command == "log":
            cfg = load_config(args.config)
            try:
                from .common import get_cursors, get_events, get_pending_events
            except ImportError:
                from common import get_cursors, get_events, get_pending_events
            curs = get_cursors(cfg.session_name)
            if curs:
                print("cursors:")
                for rec, lid in sorted(curs.items()):
                    print(f"  {rec}: {lid}")
            else:
                print("cursors: (none)")
            print()
            if args.pending:
                if args.pane:
                    pend = get_pending_events(cfg.session_name, args.pane)
                    for eid, ts, snd, typ, pay, meta in pend:
                        from_ = snd or "-"
                        to = args.pane
                        print(f"from: {from_}")
                        print(f"to: {to}")
                        print(f"ts: {ts} id:{eid} type:{typ}")
                        print(f"payload: {pay}")
                        print()
                    # also show pending broadcasts for this pane
                    try:
                        from .common import get_pending_broadcasts
                    except ImportError:
                        from common import get_pending_broadcasts
                    bpend = get_pending_broadcasts(cfg.session_name, args.pane)
                    for eid, ts, snd, typ, pay, meta in bpend:
                        from_ = snd or "-"
                        print(f"from: {from_}")
                        print(f"to: {args.pane} (via broadcast)")
                        print(f"ts: {ts} id:{eid} type:{typ}")
                        print(f"payload: {pay}")
                        print()

                else:
                    print("pending summary (use --pane for details):")
                    try:
                        bcasts = get_pending_events(cfg.session_name, "__broadcast__")
                        print(f"  __broadcast__ pending: {len(bcasts)}")
                    except Exception:
                        pass
                    print("  Run with --pane X.Y for per-pane pending")
            else:
                evs = get_events(cfg.session_name, args.pane, args.limit)
                if not evs:
                    print("(no events)")
                for eid, ts, rec, snd, typ, pay, meta in evs:
                    from_ = snd or "-"
                    to = rec
                    print(f"from: {from_}")
                    print(f"to: {to}")
                    print(f"ts: {ts} id:{eid} type:{typ}")
                    print(f"payload: {pay}")
                    print()
            return 0

        if args.command == "send":
            cfg = load_config(args.config)
            msg = " ".join(args.message)
            try:
                from .common import log_send
            except ImportError:
                from common import log_send
            if args.dry_run:
                print(f"would log-send session={cfg.session_name} target={args.target} msg={msg}")
            else:
                eid = log_send(cfg.session_name, args.target, msg, sender="cli send")
                print(f"log-sent id={eid} session={cfg.session_name} target={args.target}")
            return 0

        if args.command == "stop":
            cfg = load_config(args.config)
            swarm_babysit.stop(cfg, args.dry_run)
            _stop_tmux_session(cfg.session_name, args.dry_run)
            return 0

        if args.command == "clear-comms":
            cfg = load_config(args.config)
            if not args.yes:
                resp = input(f"Clear comms log for {cfg.session_name}? [y/N] ")
                if resp.lower() != "y":
                    print("aborted")
                    return 0
            try:
                from .common import clear_comms
            except ImportError:
                from common import clear_comms
            clear_comms(cfg.session_name, confirm=True)
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
