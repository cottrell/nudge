#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys

# Relative imports (for `python -m swarm.cli`) with bare fallback for direct
# script execution or the installed `aiswarm` entrypoint.
try:
    from . import topology as swarm_topology
    from . import babysitctl as swarm_babysit
    from . import tasksctl as swarm_tasks
    from . import init as swarm_init
    from .common import load_config, looks_like_config_path
except ImportError:
    # direct script fallback (python swarm/cli.py or installed aiswarm)
    import topology as swarm_topology
    import babysitctl as swarm_babysit
    import tasksctl as swarm_tasks
    import init as swarm_init
    from common import load_config, looks_like_config_path

CONFIG_ARG_HELP = (
    "YAML config path (optional). Default: $AISWARM_CONFIG or walk-up "
    ".aiswarm/config.yaml from cwd"
)


def _cfg_from_args(args) -> object:
    """Load SwarmConfig from optional args.config / args.config_file."""
    explicit = getattr(args, "config_file", None) or getattr(args, "config", None)
    return load_config(explicit)


def _add_optional_config(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("config", nargs="?", default=None, help=CONFIG_ARG_HELP)
    parser.add_argument(
        "-c",
        "--config-file",
        dest="config_file",
        default=None,
        help="Config path (same as optional positional; flag form)",
    )


MODEL_HELPERS = {
    "codex": {
        "command": "codex",
        "list": ["codex", "debug", "models", "--bundled"],
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
    cmds = [
        MODEL_HELPERS["codex"]["list"],
        ["codex", "debug", "models"],
    ]
    last_error: str | None = None
    for argv in cmds:
        proc = _run_capture(argv)
        if proc.returncode != 0:
            last_error = (proc.stderr or proc.stdout or "command failed").strip()
            continue
        try:
            data = json.loads(proc.stdout)
            models = [
                m["slug"]
                for m in data.get("models", [])
                if m.get("visibility") == "list" and m.get("slug")
            ]
        except (json.JSONDecodeError, TypeError, KeyError) as e:
            last_error = f"could not parse codex debug models: {e}"
            continue
        return models, None
    return [], last_error or "could not query codex debug models"


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
            suffix = " (stable local catalog)" if name == "codex" else ""
            print(f"  list: {list_cmd}{suffix}")
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

    start_p = sub.add_parser("start", help="Start the swarm (tmux session, monitors, titles, commands, and comms workers)")
    _add_optional_config(start_p)
    start_p.add_argument("-D", "--dry-run", action="store_true", help="Validate and print actions without changing tmux; still writes runtime notes")
    start_p.add_argument("-a", "--attach", action="store_true", help="Attach to the tmux session after start")
    start_p.add_argument("--skip-grid", action="store_true", help="Skip session/pane creation (use after tmuxp load)")

    status_p = sub.add_parser("status", help="Report current swarm state")
    _add_optional_config(status_p)
    status_p.add_argument("-b", "--brief", action="store_true", help="Print a compact per-pane state view")
    status_p.add_argument("-w", "--watch", action="store_true", help="Refresh the status in place until interrupted")
    status_p.add_argument("-i", "--interval", type=float, default=1.0, help="Watch refresh interval in seconds")

    broadcast_p = sub.add_parser("broadcast", help="Send an immediate message to swarm agent panes (flavours: tmux or log)")
    broadcast_p.add_argument(
        "-c",
        "--config-file",
        dest="config_file",
        default=None,
        help=CONFIG_ARG_HELP,
    )
    broadcast_p.add_argument(
        "words",
        nargs="+",
        help="Message text; optional leading config path for BC: broadcast [cfg] msg...",
    )
    broadcast_p.add_argument("-A", "--include-nonmonitored", action="store_true", help="Also send to agent panes with monitor=false")
    broadcast_p.add_argument("-D", "--dry-run", action="store_true", help="Print targets without sending")
    broadcast_p.add_argument("--via-log", action="store_true", help="Write to event log instead of direct tmux-send (consumer will deliver)")

    stop_p = sub.add_parser("stop", help="Stop tasks dispatcher, worker loops (comms + babysit), and the tmux session")
    _add_optional_config(stop_p)
    stop_p.add_argument("-D", "--dry-run", action="store_true", help="Print planned stop actions without changing tmux or workers")

    clear_p = sub.add_parser("clear-comms", help="Clear the event log for a session (destructive)")
    _add_optional_config(clear_p)
    clear_p.add_argument("-y", "--yes", action="store_true", help="Skip 'y' confirmation")

    log_p = sub.add_parser("log", help="Inspect the comms event log (events + cursors)")
    _add_optional_config(log_p)
    log_p.add_argument("--pane", help="Filter to a specific pane e.g. 0.2")
    log_p.add_argument("-n", "--limit", type=int, default=50)
    log_p.add_argument("--pending", action="store_true", help="Only show unread events for the given --pane (or summarize)")
    log_p.add_argument("-w", "--watch", action="store_true", help="Refresh the log in place until interrupted")
    log_p.add_argument("-i", "--interval", type=float, default=1.0, help="Watch refresh interval in seconds (default: 1)")

    send_p = sub.add_parser("send", help="Send a message to a single target via the event log (instead of direct tmux-send)", description="Send a message to a single target via the event log (instead of direct tmux-send)")
    send_p.add_argument(
        "-c",
        "--config-file",
        dest="config_file",
        default=None,
        help=CONFIG_ARG_HELP,
    )
    send_p.add_argument(
        "tokens",
        nargs="+",
        help="target message... or legacy: config target message...",
    )
    send_p.add_argument("-D", "--dry-run", action="store_true", help="Print action without sending")

    avu_p = sub.add_parser("av-usage", help="Agentsview usage (global by default; provide a swarm config to limit to its agents)")
    avu_p.add_argument("config", nargs="?", default=None, help=CONFIG_ARG_HELP + " (limits report to its agents when given)")
    avu_p.add_argument(
        "-c",
        "--config-file",
        dest="config_file",
        default=None,
        help="Config path (flag form)",
    )
    avu_p.add_argument("--json", action="store_true", help="Emit JSON")
    avu_p.add_argument("--recent", type=int, default=0, metavar="MIN", help="Include rolling tokens for last N minutes (in addition)")
    avu_p.add_argument("-w", "--watch", action="store_true", help="Refresh the report in place until interrupted")
    avu_p.add_argument("-i", "--interval", type=float, default=30.0, help="Watch refresh interval in seconds (default: 30)")

    quota_p = sub.add_parser("quota", help="Get cached/live provider account quotas")
    quota_p.add_argument("config", nargs="?", default=None, help=CONFIG_ARG_HELP + " (limits report to its agents when given)")
    quota_p.add_argument(
        "-c",
        "--config-file",
        dest="config_file",
        default=None,
        help="Config path (flag form)",
    )
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
    capture_p.add_argument(
        "-c",
        "--config-file",
        dest="config_file",
        default=None,
        help=CONFIG_ARG_HELP,
    )
    capture_p.add_argument(
        "tokens",
        nargs="+",
        help="pane id, or legacy: config pane",
    )

    babysit_p = sub.add_parser("babysit", help="Toggle the babysit prompt group on top of the base worker loop (comms always-on)")
    babysit_sub = babysit_p.add_subparsers(dest="babysit_command", required=True)
    for name in ("start", "status", "stop"):
        if name == "start":
            help_text = "Enable babysit prompt loops for configured panes"
        elif name == "stop":
            help_text = "Disable babysit prompt loops (keep comms worker for messaging)"
        else:
            help_text = "Show babysit + worker status"
        sp = babysit_sub.add_parser(name, help=help_text)
        _add_optional_config(sp)
        if name != "status":
            sp.add_argument("-D", "--dry-run", action="store_true", help="Validate and print actions without changing workers; start still writes runtime notes")
            if name == "start":
                sp.add_argument("--no-action", action="store_true", help="Start the worker loops but do not deliver any prompts (simulate loops)")

    tasks_p = sub.add_parser(
        "tasks",
        help="Session task dispatcher: pull work from a source (v1: backlog) and assign to free panes (separate from babysit)",
    )
    tasks_sub = tasks_p.add_subparsers(dest="tasks_command", required=True)
    for name, help_text in (
        ("start", "Start the tasks dispatcher process for this swarm"),
        ("stop", "Stop the tasks dispatcher process"),
        ("status", "Show dispatcher status, assignments, and candidate tasks"),
        ("once", "Run a single claim/dispatch pass (no long-running process)"),
    ):
        sp = tasks_sub.add_parser(name, help=help_text)
        _add_optional_config(sp)
        if name != "status":
            sp.add_argument(
                "-D",
                "--dry-run",
                action="store_true",
                help="Print planned claims/dispatches without editing backlog or sending",
            )

    return parser


def _split_send_tokens(tokens: list[str], config_file: str | None) -> tuple[str | None, str, list[str]]:
    """Return (explicit_config, target, message_parts)."""
    if config_file:
        if len(tokens) < 2:
            raise ValueError("send requires TARGET and MESSAGE")
        return config_file, tokens[0], tokens[1:]
    if len(tokens) >= 3 and looks_like_config_path(tokens[0]):
        return tokens[0], tokens[1], tokens[2:]
    if len(tokens) < 2:
        raise ValueError("send requires TARGET and MESSAGE (optional leading CONFIG)")
    return None, tokens[0], tokens[1:]


def _split_broadcast_words(words: list[str], config_file: str | None) -> tuple[str | None, str]:
    if config_file:
        return config_file, " ".join(words)
    if len(words) >= 2 and looks_like_config_path(words[0]):
        return words[0], " ".join(words[1:])
    return None, " ".join(words)


def _split_capture_tokens(tokens: list[str], config_file: str | None) -> tuple[str | None, str]:
    if config_file:
        if len(tokens) != 1:
            raise ValueError("capture requires a single PANE when -c is set")
        return config_file, tokens[0]
    if len(tokens) == 1:
        return None, tokens[0]
    if len(tokens) == 2 and looks_like_config_path(tokens[0]):
        return tokens[0], tokens[1]
    raise ValueError("capture requires PANE or CONFIG PANE")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "init":
            agents = [a.strip() for a in args.agents.split(",") if a.strip()]
            swarm_init.init(args.name, args.root, args.dry_run, agents, flavour=args.flavour)
            return 0

        if args.command == "start":
            cfg = _cfg_from_args(args)
            swarm_topology.start(cfg, args.dry_run, skip_grid=args.skip_grid)
            if args.attach and not args.dry_run:
                subprocess.run(["tmux", "attach", "-t", cfg.session_name], check=True, text=True)
            return 0

        if args.command == "status":
            cfg = _cfg_from_args(args)
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
            # Optional config: only limit agents when path/env/default is available.
            cfg_explicit = getattr(args, "config_file", None) or getattr(args, "config", None)
            agents = ["claude", "codex", "agy"]
            if cfg_explicit:
                cfg = load_config(cfg_explicit)
                agents = get_agents_from_config(cfg)
            else:
                try:
                    cfg = load_config(None)
                    agents = get_agents_from_config(cfg)
                except FileNotFoundError:
                    pass
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

            cfg_explicit = getattr(args, "config_file", None) or getattr(args, "config", None)
            agents = None
            limited = False
            if cfg_explicit:
                cfg = load_config(cfg_explicit)
                agents = get_agents_from_config(cfg)
                limited = True
            else:
                try:
                    cfg = load_config(None)
                    agents = get_agents_from_config(cfg)
                    limited = True
                except FileNotFoundError:
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

            title = (
                f"agentsview usage limited to swarm agents: {effective}"
                if limited
                else "agentsview global usage (all agents)"
            )
            lines = swarm_topology.av_usage_lines(report, recent_minutes=args.recent, title=title)
            print("\n".join(lines))
            return 0

        if args.command in ("help", "models"):
            print_model_help()
            return 0

        if args.command == "capture":
            explicit, pane = _split_capture_tokens(args.tokens, getattr(args, "config_file", None))
            cfg = load_config(explicit)
            swarm_topology.capture_pane(cfg, pane)
            return 0

        if args.command == "broadcast":
            explicit, msg = _split_broadcast_words(args.words, getattr(args, "config_file", None))
            cfg = load_config(explicit)
            swarm_topology.broadcast(cfg, msg, args.include_nonmonitored, args.dry_run, via_log=args.via_log)
            return 0

        if args.command == "log":
            cfg = _cfg_from_args(args)
            if args.watch:
                swarm_topology.watch_log(cfg, args.pane, args.limit, args.pending, args.interval)
                return 0
            swarm_topology.print_log(cfg, args.pane, args.limit, args.pending)
            return 0

        if args.command == "send":
            explicit, target, msg_parts = _split_send_tokens(
                args.tokens, getattr(args, "config_file", None)
            )
            cfg = load_config(explicit)
            msg = " ".join(msg_parts)
            try:
                from .common import log_send
            except ImportError:
                from common import log_send
            if args.dry_run:
                print(f"would log-send session={cfg.session_name} target={target} msg={msg}")
            else:
                eid = log_send(cfg.session_name, target, msg, sender="cli send")
                print(f"log-sent id={eid} session={cfg.session_name} target={target}")
            return 0

        if args.command == "stop":
            cfg = _cfg_from_args(args)
            swarm_tasks.stop_dispatcher(cfg, args.dry_run)
            swarm_babysit.stop_workers(cfg, args.dry_run)
            _stop_tmux_session(cfg.session_name, args.dry_run)
            return 0

        if args.command == "clear-comms":
            cfg = _cfg_from_args(args)
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

        if args.command == "tasks":
            cfg = _cfg_from_args(args)
            if args.tasks_command == "start":
                swarm_tasks.start_dispatcher(cfg, getattr(args, "dry_run", False))
            elif args.tasks_command == "stop":
                swarm_tasks.stop_dispatcher(cfg, getattr(args, "dry_run", False))
            elif args.tasks_command == "once":
                actions = swarm_tasks.dispatch_once(cfg, dry_run=getattr(args, "dry_run", False))
                if not actions:
                    print("no dispatch (no free pane or no candidates)")
            else:
                swarm_tasks.status(cfg)
            return 0

        cfg = _cfg_from_args(args)
        if args.babysit_command == "start":
            if getattr(args, "no_action", False):
                import os
                os.environ["BABYSIT_DRY_RUN"] = "1"
            swarm_babysit.apply_babysit(cfg, args.dry_run)
        elif args.babysit_command == "stop":
            swarm_babysit.disable_babysit(cfg, args.dry_run)
        else:
            swarm_babysit.status(cfg)
        return 0
    except Exception as e:
        print(str(e), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
