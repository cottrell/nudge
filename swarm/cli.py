#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

# Relative imports (for `python -m swarm.cli`) with bare fallback for direct
# script execution or the installed `aiswarm` entrypoint.
try:
    from . import topology as swarm_topology
    from . import babysitctl as swarm_babysit
    from . import tasksctl as swarm_tasks
    from . import init as swarm_init
    from . import instructions as swarm_instructions
    from . import presence as swarm_presence
    from .common import (
        build_this_text,
        load_config,
        load_model_aliases,
        looks_like_config_path,
        parse_duration,
    )
except ImportError:
    # direct script fallback (python swarm/cli.py or installed aiswarm)
    import topology as swarm_topology
    import babysitctl as swarm_babysit
    import tasksctl as swarm_tasks
    import init as swarm_init
    import instructions as swarm_instructions
    import presence as swarm_presence
    from common import (
        build_this_text,
        load_config,
        load_model_aliases,
        looks_like_config_path,
        parse_duration,
    )

CONFIG_ARG_HELP = (
    "YAML config path (optional). Default: $AISWARM_CONFIG or walk-up "
    ".aiswarm/config.yaml from cwd"
)


def _cfg_from_args(args) -> object:
    """Load SwarmConfig from optional args.config / args.config_file."""
    explicit = getattr(args, "config_file", None) or getattr(args, "config", None)
    return load_config(explicit)


def _duration_arg(text: str) -> int:
    try:
        return parse_duration(text)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e)) from e


def _until_from_args(args) -> float | None:
    duration = getattr(args, "for_duration", None)
    if duration is None:
        return None
    return time.time() + duration


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
    print("Use a provider:role token from swarm/models.yaml as pane shell_command.")
    print("Commands below are probed from the CLIs installed on this machine.")
    print()
    try:
        aliases = load_model_aliases()
    except (OSError, ValueError) as exc:
        aliases = {}
        print(f"alias table: unavailable ({exc})")
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
        tokens = [key for key in aliases if key.startswith(f"{name}:")]
        if tokens:
            print("  swarm YAML:")
            for key in tokens:
                print(f'    shell_command: "{key}"')
        else:
            print(f"  swarm YAML: shell_command: \"{helper['swarm']}\"")
        print()


# Display order for `aiswarm -h`. Groups: lifecycle, messaging, pane, usage.
# Bare `aiswarm` is handwritten in instructions.bare_help() and must list these
# commands in this order. Nothing else is a command index.
_HELP_ORDER = (
    "init start stop status this sessions swarms worker "
    "send unsend broadcast clear log clear-comms healthcheck "
    "capture wait babysit tasks "
    "quota quota-debug av-usage help instructions"
).split()


def _order_subcommands(sub: argparse._SubParsersAction) -> None:
    """Display-only: group related commands in `aiswarm -h`. Unlisted ones go last."""
    rank = {n: i for i, n in enumerate(_HELP_ORDER)}
    last = len(rank)
    sub._choices_actions.sort(key=lambda a: rank.get(a.dest, last))
    sub.choices = dict(sorted(sub.choices.items(), key=lambda kv: rank.get(kv[0], last)))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Unified CLI for config-driven tmux swarm workflows.",
        epilog="Run bare `aiswarm` for a workflow cheat sheet; `aiswarm instructions` for agent guides.",
    )
    sub = parser.add_subparsers(dest="command", required=False)

    inst_p = sub.add_parser(
        "instructions",
        help="Print agent-facing workflow guides (not flag help)",
    )
    inst_p.add_argument(
        "guide",
        nargs="?",
        default=None,
        help="Guide name (omit to list). overview | tasks",
    )

    this_p = sub.add_parser(
        "this",
        help="Print resolved session identity and runtime.json path",
    )
    _add_optional_config(this_p)

    sessions_p = sub.add_parser(
        "sessions",
        help="Show provider session IDs for this swarm (for resume after a crash)",
    )
    _add_optional_config(sessions_p)
    sessions_p.add_argument(
        "--json",
        action="store_true",
        help="Print records as JSON",
    )
    sessions_p.add_argument(
        "--no-refresh",
        action="store_true",
        help="Do not re-discover from live pane PIDs",
    )

    swarms_p = sub.add_parser(
        "swarms",
        help="List swarms discovered in /tmp/nudge-swarm with status and pane counts",
        description="Inspect /tmp/nudge-swarm to list active and inactive swarms on this machine.",
        epilog=(
            "examples:\n"
            "  aiswarm swarms           # table of discovered swarms\n"
            "  aiswarm swarms --brief   # one-line summaries\n"
            "  aiswarm swarms --json    # JSON output\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    swarms_p.add_argument("--brief", "-b", action="store_true", help="One-line summary per swarm")
    swarms_p.add_argument("--json", action="store_true", help="Output JSON")
    swarms_p.add_argument("--runtime-dir", dest="runtime_dir", default=None, help=argparse.SUPPRESS)

    init_p = sub.add_parser("init", help="Create a starter swarm config and AGENTS.md block")
    init_p.add_argument("name", help="Swarm/session name")
    init_p.add_argument("--root", default=".", help="Project root to initialize, default current directory")
    init_p.add_argument("--agents", default="codex,claude,antigravity,grok", help="Comma-separated list of agents (repeats allowed), default codex,claude,antigravity,grok")
    init_p.add_argument(
        "--flavour",
        default=None,
        choices=["1x1", "2x2", "3x2", "3x3", "4x2", "babysit", "demo"],
        help="Pane layout: 3x2 (default), 1x1, 2x2, 3x3 (9 panes: 3x codex, 2x claude, grok, 3x antigravity light), 4x2, babysit (2x2 with explicit babysit prompts), or demo (agents + log -w + shell)",
    )
    init_p.add_argument("-f", "--force", action="store_true", help="Overwrite existing configuration and prompt files")
    init_p.add_argument("-D", "--dry-run", action="store_true", help="Print planned files and AGENTS.md block without writing")

    start_p = sub.add_parser("start", help="Start the swarm (tmux session, monitors, titles, commands, and comms workers)")
    _add_optional_config(start_p)
    start_p.add_argument("-D", "--dry-run", action="store_true", help="Validate and print actions without changing tmux; still writes runtime notes")
    start_p.add_argument("-a", "--attach", action="store_true", help="Attach to the tmux session after start")
    start_p.add_argument("--skip-grid", action="store_true", help="Skip session/pane creation (use after tmuxp load)")
    start_p.add_argument(
        "--resume",
        action="store_true",
        help="Relaunch panes from session-ids.json, keeping config flags (append -r or --conversation; codex resume <id> then those flags). Panes with no recorded id are unchanged",
    )

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

    worker_p = sub.add_parser(
        "worker", help="Manage the shared session worker without touching tmux panes"
    )
    worker_sub = worker_p.add_subparsers(dest="worker_command", required=True)
    worker_restart = worker_sub.add_parser(
        "restart", help="Restart the shared comms/babysit/tasks worker in place"
    )
    _add_optional_config(worker_restart)
    worker_restart.add_argument(
        "-D", "--dry-run", action="store_true",
        help="Validate the recorded worker PID and print the restart action",
    )

    clear_p = sub.add_parser("clear-comms", help="Clear the event log for a session (destructive)")
    _add_optional_config(clear_p)
    clear_p.add_argument("-y", "--yes", action="store_true", help="Skip 'y' confirmation")

    log_p = sub.add_parser("log", help="Inspect the comms event log (events + cursors)")
    _add_optional_config(log_p)
    log_p.add_argument("--pane", help="Filter to a specific pane e.g. 0.2")
    log_p.add_argument("-n", "--limit", type=int, default=50)
    log_p.add_argument("--pending", action="store_true", help="Only show unread events (optionally filtered by --pane)")
    log_p.add_argument("-w", "--watch", action="store_true", help="Refresh the log in place until interrupted")
    log_p.add_argument("-i", "--interval", type=float, default=1.0, help="Watch refresh interval in seconds (default: 1)")

    send_p = sub.add_parser(
        "send",
        help="Send to one pane, category, 'any', or another swarm via event log",
        description=(
            "Send via the durable event log (delivered on pane idle). Target a "
            "pane (e.g. 0.2), category, 'any', or another swarm via qualified "
            "'<swarm>:<target>'. Messages delivered to panes include an envelope "
            "prefix identifying the sender."
        ),
        epilog=(
            "examples:\n"
            "  aiswarm send 0.0 hello\n"
            '  aiswarm send 0.2 "do the thing"\n'
            '  aiswarm send any "pick this up when free"\n'
            "  aiswarm send -c .aiswarm/config.yaml 0.1 hi there\n"
            "  aiswarm send ./swarm.yaml 0.0 hello   # legacy: leading config path\n"
            '  aiswarm send -s otherswarm 0.1 "hello from nudge"   # cross-swarm\n'
            '  aiswarm send otherswarm:0.1 "hello from nudge"      # qualified shorthand\n'
            '  aiswarm send otherswarm:any "pick this up"          # qualified any\n'
            '  aiswarm send --at +2h 0.2 "check progress"          # scheduled delivery\n'
            '  aiswarm send --at +30m any "nudge on idle"          # scheduled any'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    send_p.add_argument(
        "--at",
        dest="at",
        default=None,
        help=(
            "Defer message delivery until specified time: ISO timestamp "
            "(e.g. 2026-10-02T12:00:00) or relative offset (+2h, +30m, +45s)"
        ),
    )
    send_p.add_argument(
        "-c",
        "--config-file",
        dest="config_file",
        default=None,
        help=CONFIG_ARG_HELP,
    )
    send_p.add_argument(
        "-s",
        "--swarm",
        dest="swarm",
        default=None,
        help=(
            "Target another swarm by session name, resolved via "
            "/tmp/nudge-swarm/<name>/runtime.json. Default: this swarm."
        ),
    )

    health_p = sub.add_parser("healthcheck", help="Reply to a dispatcher healthcheck")
    health_sub = health_p.add_subparsers(dest="healthcheck_command", required=True)
    pong_p = health_sub.add_parser("pong", help="Record an agent healthcheck pong")
    _add_optional_config(pong_p)
    pong_p.add_argument("pane", help="Pane id from the HEALTHCHECK prompt")
    pong_p.add_argument("nonce", help="Nonce from the HEALTHCHECK prompt")
    send_p.add_argument(
        "--sender",
        dest="sender",
        default=None,
        help=(
            "Optional sender identity string recorded in comms.db "
            "(default: auto-inferred from tmux session/pane or local config)"
        ),
    )
    send_p.add_argument(
        "tokens",
        nargs="+",
        metavar=("TARGET", "MESSAGE"),
        help=(
            "TARGET pane (e.g. 0.2), category, 'any', 'mcp', or qualified '<swarm>:<target>', "
            "then MESSAGE words. Legacy: optional leading CONFIG path before the target"
        ),
    )
    send_p.add_argument("-D", "--dry-run", action="store_true", help="Print action without sending")

    unsend_p = sub.add_parser(
        "unsend",
        help="Cancel a queued message by id (as printed by send) before it is delivered",
        description=(
            "Cancel an undelivered message. Works while the message is still queued "
            "(busy pane, scheduled --at, or 'any' not yet claimed). Once delivered it is too late."
        ),
        epilog="examples:\n  aiswarm unsend 42\n  aiswarm unsend -s otherswarm 42",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    unsend_p.add_argument("-c", "--config-file", dest="config_file", default=None, help=CONFIG_ARG_HELP)
    unsend_p.add_argument("-s", "--swarm", dest="swarm", default=None, help="Swarm session name (default: this swarm)")
    unsend_p.add_argument("--force", action="store_true", help="Cancel even if sent by someone else")
    unsend_p.add_argument("id", type=int, help="Event id printed by send")

    clear_p = sub.add_parser(
        "clear",
        help="Send '/clear' to all agent panes (or target pane) via the event log",
        description="Send '/clear' to all agent panes by default, or a specific target pane, via the event log.",
        epilog=(
            "examples:\n"
            "  aiswarm clear           # broadcasts /clear to all agent panes\n"
            "  aiswarm clear 0.0       # sends /clear to pane 0.0\n"
            "  aiswarm clear -c .aiswarm/config.yaml 0.1\n"
            "  aiswarm clear ./swarm.yaml   # legacy: optional leading config path"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    clear_p.add_argument(
        "-c",
        "--config-file",
        dest="config_file",
        default=None,
        help=CONFIG_ARG_HELP,
    )
    clear_p.add_argument(
        "tokens",
        nargs="*",
        metavar=("PANE"),
        help="Optional PANE id (e.g. 0.2). If omitted, broadcasts /clear to all agent panes.",
    )
    clear_p.add_argument(
        "-A",
        "--include-nonmonitored",
        action="store_true",
        help="When clearing all panes, also include agent panes with monitor=false",
    )
    clear_p.add_argument("-D", "--dry-run", action="store_true", help="Print action without sending")

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

    quota_debug_p = sub.add_parser("quota-debug", aliases=["quota_debug"], help="Show raw and parsed usage details for a chosen agent")
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

    wait_p = sub.add_parser(
        "wait",
        help="Block until a pane is idle (monitor-bin state) or its screen stops changing",
        description=(
            "Standalone blocking CLI poll; no comms log, no messages sent. Default: poll "
            "the pane's monitor-bin idle state (same signal babysit/tasks/comms use) "
            "every --interval secs and exit when idle. --stable SECS ignores the monitor "
            "and instead diffs tmux capture-pane text, exiting once unchanged for SECS. "
            "Prints one line. Exit 0 = idle/stable, 1 = timeout, 2 = unknown pane."
        ),
    )
    wait_p.add_argument(
        "-c",
        "--config-file",
        dest="config_file",
        default=None,
        help=CONFIG_ARG_HELP,
    )
    wait_p.add_argument(
        "tokens",
        nargs="+",
        help="pane id, or legacy: config pane",
    )
    wait_p.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="Seconds to wait (default 120; 0 = forever)",
    )
    wait_p.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="Seconds between polls (default 1)",
    )
    wait_p.add_argument(
        "--stable",
        type=float,
        default=None,
        metavar="SECS",
        help="Use raw capture-pane text diffing instead of monitor-bin: done when unchanged for SECS",
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
                sp.add_argument(
                    "--for",
                    dest="for_duration",
                    type=_duration_arg,
                    metavar="DURATION",
                    help="Run babysit prompts for a duration (1h, 30m, 90s, or seconds) then auto-stop",
                )

    tasks_p = sub.add_parser(
        "tasks",
        help="Session task dispatcher: pull work from a source (v1: backlog) and assign to free panes (optional require_label filter; unassigned_only by default)",
        description=(
            "Session task dispatcher: claims tasks from backlog (e.g. To Do) onto free panes.\n"
            "By default claims unassigned tasks (unassigned_only: true). Set require_label (e.g. 'auto')\n"
            "in swarm config to filter claims to specific task tags."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    tasks_sub = tasks_p.add_subparsers(dest="tasks_command", required=True)
    for name, help_text in (
        ("start", "Enable the tasks group (does not reload the shared worker)"),
        ("stop", "Disable the tasks group (does not stop the shared worker)"),
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
            if name == "start":
                sp.add_argument(
                    "--for",
                    dest="for_duration",
                    type=_duration_arg,
                    metavar="DURATION",
                    help="Run the tasks group for a duration (1h, 30m, 90s, or seconds) then auto-stop",
                )

    presence_p = sub.add_parser(
        "presence",
        help="Human availability / presence state and overrides (global and swarm-local)",
        description=(
            "Check or override human availability state so agents know whether a human is present.\n"
            "Scopes:\n"
            "  aiswarm presence [config]                        Show effective, local, and global presence\n"
            "  aiswarm presence global in|out|auto [--for D]     Set global override or reset to auto\n"
            "  aiswarm presence local in|out|auto|global [--for] Set local override or follow global\n"
            "Shorthand:\n"
            "  aiswarm presence in|out|auto                      Sets local mode for current swarm"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    presence_p.add_argument("tokens", nargs="*", help="[local|global] [mode] or shorthand [mode]")
    presence_p.add_argument(
        "-c",
        "--config-file",
        dest="config_file",
        default=None,
        help=CONFIG_ARG_HELP,
    )
    presence_p.add_argument(
        "--for",
        dest="for_duration",
        type=_duration_arg,
        metavar="DURATION",
        help="Duration for override (e.g. 2h, 30m, 90s) before expiring back to auto/global",
    )
    presence_p.add_argument(
        "--idle-timeout",
        type=_duration_arg,
        default=None,
        metavar="DURATION",
        help="Idle duration threshold for passive auto detection (default 15m)",
    )
    presence_p.add_argument("--json", action="store_true", help="Emit JSON output")

    _order_subcommands(sub)
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


def _split_clear_tokens(tokens: list[str], config_file: str | None) -> tuple[str | None, str | None]:
    """Return (explicit_config, target_or_none)."""
    if config_file:
        return config_file, tokens[0] if tokens else None
    if tokens:
        if len(tokens) >= 2 and looks_like_config_path(tokens[0]):
            return tokens[0], tokens[1]
        if len(tokens) == 1 and looks_like_config_path(tokens[0]):
            return tokens[0], None
        return None, tokens[0]
    return None, None


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


def _infer_sender(local_session: str | None = None) -> str:
    """Infer sender identity from tmux pane/session or local config."""
    if os.environ.get("TMUX") or os.environ.get("TMUX_PANE"):
        target_args = ["-t", os.environ["TMUX_PANE"]] if os.environ.get("TMUX_PANE") else []
        try:
            res = subprocess.run(
                ["tmux", "display-message", *target_args, "-p", "#{session_name}:#{window_index}.#{pane_index}"],
                capture_output=True,
                text=True,
                check=False,
            )
            val = res.stdout.strip()
            if res.returncode == 0 and val:
                return val
        except OSError:
            pass

    if local_session:
        return f"{local_session}:cli"

    try:
        from .common import load_config
    except ImportError:
        from common import load_config
    try:
        cfg = load_config(None)
        if cfg and cfg.session_name:
            return f"{cfg.session_name}:cli"
    except Exception:
        pass

    return "cli send"


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if not args.command:
            print(swarm_instructions.bare_help().rstrip())
            return 0

        if args.command == "instructions":
            print(swarm_instructions.render(args.guide).rstrip())
            return 0

        if args.command == "this":
            print(build_this_text(_cfg_from_args(args)).rstrip())
            return 0

        if args.command == "sessions":
            cfg = _cfg_from_args(args)
            try:
                from .session_ids import format_records, load_records, refresh_records
            except ImportError:
                from session_ids import format_records, load_records, refresh_records
            if args.no_refresh:
                records = load_records(cfg)
            else:
                records = refresh_records(cfg, swarm_topology.collect_pane_pids(cfg))
            if args.json:
                print(json.dumps(
                    {
                        "session_name": cfg.session_name,
                        "panes": {p: r.as_dict() for p, r in records.items()},
                    },
                    indent=2,
                ))
            else:
                print(format_records(cfg, records))
            return 0

        if args.command == "swarms":
            r_root = Path(args.runtime_dir) if getattr(args, "runtime_dir", None) else None
            swarm_topology.print_swarms(brief=args.brief, as_json=args.json, runtime_root=r_root)
            return 0

        if args.command == "init":
            agents = [a.strip() for a in args.agents.split(",") if a.strip()]
            swarm_init.init(
                args.name,
                args.root,
                args.dry_run,
                agents,
                flavour=args.flavour or "3x2",
                force=args.force,
            )
            return 0

        if args.command == "start":
            cfg = _cfg_from_args(args)
            swarm_topology.start(cfg, args.dry_run, skip_grid=args.skip_grid, resume=args.resume)
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

        if args.command == "wait":
            explicit, pane = _split_capture_tokens(args.tokens, getattr(args, "config_file", None))
            cfg = load_config(explicit)
            return swarm_topology.wait_pane(
                cfg,
                pane,
                timeout=args.timeout,
                interval=args.interval,
                stable=args.stable,
            )

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
            msg = " ".join(msg_parts)
            try:
                from .common import log_any, log_send, parse_at_spec
            except ImportError:
                from common import log_any, log_send, parse_at_spec

            at_spec = getattr(args, "at", None)
            not_before = None
            if at_spec:
                try:
                    not_before = parse_at_spec(at_spec)
                except ValueError as exc:
                    print(f"error: {exc}", file=sys.stderr)
                    return 1

            swarm_name = getattr(args, "swarm", None)
            if not swarm_name and ":" in target and not target.startswith("mcp:"):
                swarm_name, target = target.split(":", 1)

            if swarm_name:
                runtime_path = Path("/tmp/nudge-swarm") / swarm_name / "runtime.json"
                try:
                    runtime = json.loads(runtime_path.read_text())
                except (OSError, json.JSONDecodeError) as exc:
                    print(
                        f"error: cannot read runtime map for swarm '{swarm_name}' "
                        f"({runtime_path}): {exc}",
                        file=sys.stderr,
                    )
                    return 1
                session_name = runtime.get("session_name", swarm_name)
                valid_panes = list((runtime.get("panes") or {}).keys())
                cats = {c for v in (runtime.get("panes") or {}).values() for c in (v.get("categories") or [])}
                category = target if target in cats else None
                is_valid_target = (target in valid_panes or target == "any" or target == "mcp"
                                   or target.startswith("mcp:") or category is not None)
                if not is_valid_target:
                    if not re.fullmatch(r"\d+\.\d+", target):
                        print(f"error: no pane or category '{target}' in swarm '{swarm_name}'", file=sys.stderr)
                        return 1
                    print(
                        f"Warning: recipient pane '{target}' is not present in "
                        f"swarm '{swarm_name}' runtime map",
                        file=sys.stderr,
                    )
            else:
                cfg = load_config(explicit)
                session_name = cfg.session_name
                cats = {c for p in cfg.panes for c in p.categories}
                category = target if target in cats else None
                is_valid_target = (target in [p.pane for p in cfg.panes] or target == "any" or target == "mcp"
                                   or target.startswith("mcp:") or category is not None)
                if not is_valid_target:
                    if not re.fullmatch(r"\d+\.\d+", target):
                        print(f"error: no pane or category '{target}' in the config", file=sys.stderr)
                        return 1
                    print(f"Warning: recipient pane '{target}' is not present in the config", file=sys.stderr)

            sender_name = getattr(args, "sender", None) or _infer_sender(session_name if not swarm_name else None)
            at_info = f" at={not_before}" if not_before else ""
            if args.dry_run:
                print(f"would log-send session={session_name} target={target} sender={sender_name}{at_info} msg={msg}")
            else:
                eid = (log_any(session_name, msg, sender=sender_name, category=category, not_before=not_before)
                       if target == "any" or category
                       else log_send(session_name, target, msg, sender=sender_name, not_before=not_before))
                print(f"log-sent id={eid} session={session_name} target={target}{at_info}")
            return 0

        if args.command == "unsend":
            try:
                from .common import unsend_event
            except ImportError:
                from common import unsend_event
            swarm_name = args.swarm
            if swarm_name:
                runtime_path = Path("/tmp/nudge-swarm") / swarm_name / "runtime.json"
                try:
                    session_name = json.loads(runtime_path.read_text()).get("session_name", swarm_name)
                except (OSError, json.JSONDecodeError) as exc:
                    print(f"error: cannot read runtime map for swarm '{swarm_name}': {exc}", file=sys.stderr)
                    return 1
            else:
                session_name = load_config(args.config_file).session_name
            status, detail = unsend_event(
                session_name, args.id,
                requester=_infer_sender(session_name if not swarm_name else None), force=args.force,
            )
            print(f"unsend {status}: {detail}", file=sys.stderr if status in ("denied", "not_found", "too_late") else sys.stdout)
            return 0 if status in ("cancelled", "partial") else 1

        if args.command == "clear":
            explicit, target = _split_clear_tokens(
                args.tokens, getattr(args, "config_file", None)
            )
            cfg = load_config(explicit)
            msg = "/clear"
            if target is None:
                swarm_topology.broadcast(
                    cfg,
                    msg,
                    include_nonmonitored=args.include_nonmonitored,
                    dry_run=args.dry_run,
                    via_log=True,
                )
                return 0

            try:
                from .common import log_any, log_send
            except ImportError:
                from common import log_any, log_send
            if target not in [p.pane for p in cfg.panes] and target != "any":
                print(f"Warning: recipient pane '{target}' is not present in the config", file=sys.stderr)
            if args.dry_run:
                print(f"would log-send session={cfg.session_name} target={target} msg={msg}")
            else:
                eid = (log_any(cfg.session_name, msg, sender="cli clear") if target == "any"
                       else log_send(cfg.session_name, target, msg, sender="cli clear"))
                print(f"log-sent id={eid} session={cfg.session_name} target={target}")
            return 0

        if args.command == "healthcheck":
            cfg = _cfg_from_args(args)
            if args.healthcheck_command == "pong":
                try:
                    from .tasksctl import healthcheck_recipient
                    from .common import log_send
                except ImportError:
                    from tasksctl import healthcheck_recipient
                    from common import log_send
                eid = log_send(
                    cfg.session_name,
                    healthcheck_recipient(args.pane),
                    f"pong {args.nonce}",
                    sender="agent-pong",
                    etype="healthcheck-pong",
                    meta={"pane": args.pane, "nonce": args.nonce},
                )
                print(f"healthcheck pong id={eid} session={cfg.session_name} pane={args.pane}")
                return 0

        if args.command == "stop":
            cfg = _cfg_from_args(args)
            swarm_tasks.stop_dispatcher(cfg, args.dry_run)
            swarm_babysit.stop_workers(cfg, args.dry_run)
            _stop_tmux_session(cfg.session_name, args.dry_run)
            return 0

        if args.command == "worker":
            cfg = _cfg_from_args(args)
            if args.worker_command == "restart":
                swarm_babysit.restart_worker(cfg, args.dry_run)
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
                swarm_tasks.start_dispatcher(
                    cfg, getattr(args, "dry_run", False), until=_until_from_args(args),
                )
            elif args.tasks_command == "stop":
                swarm_tasks.stop_dispatcher(cfg, getattr(args, "dry_run", False))
            elif args.tasks_command == "once":
                actions = swarm_tasks.dispatch_once(cfg, dry_run=getattr(args, "dry_run", False))
                if not actions:
                    print("no dispatch (no free pane or no candidates)")
            else:
                swarm_tasks.status(cfg)
            return 0

        if args.command == "presence":
            tokens = list(args.tokens)
            explicit_cfg = getattr(args, "config_file", None)
            if tokens and looks_like_config_path(tokens[0]) and not explicit_cfg:
                explicit_cfg = tokens.pop(0)

            # Determine scope and mode
            # Scopes: global, local
            # Commands:
            #   aiswarm presence                           -> query
            #   aiswarm presence global [in|out|auto]      -> set global override (or reset to auto)
            #   aiswarm presence local [in|out|auto|global]-> set local override (or follow global)
            #   aiswarm presence in|out|auto|global        -> shorthand for 'presence local <mode>'
            scope = None
            mode = None
            if len(tokens) > 2:
                raise ValueError(f"too many arguments for presence: {' '.join(tokens)}")

            if len(tokens) == 2:
                first, second = tokens[0].lower(), tokens[1].lower()
                if first in ("global", "g"):
                    scope = "global"
                    mode = second
                elif first in ("local", "l"):
                    scope = "local"
                    mode = second
                else:
                    raise ValueError(f"unknown presence scope '{tokens[0]}' (use 'global' or 'local')")
            elif len(tokens) == 1:
                arg = tokens[0].lower()
                if arg in ("global", "g"):
                    scope = "global"
                    # query or missing mode
                    mode = None
                elif arg in ("local", "l"):
                    scope = "local"
                    mode = None
                elif arg in ("in", "out", "auto"):
                    scope = "local"
                    mode = arg
                else:
                    raise ValueError(f"unknown presence mode or scope '{tokens[0]}' (use 'presence local global' to reset to global)")

            until = _until_from_args(args)
            if until is not None and not mode:
                raise ValueError("--for cannot be specified without setting a mode (in or out)")

            # Resolve config if needed for local scope or display
            cfg = None
            try:
                cfg = load_config(explicit_cfg)
            except Exception:
                pass
            session_name = cfg.session_name if cfg else None

            timeout = args.idle_timeout or swarm_presence.DEFAULT_IDLE_TIMEOUT_SECS

            if mode:
                if scope == "global":
                    if mode not in ("in", "out", "auto"):
                        raise ValueError(f"invalid global presence mode: '{mode}' (use in, out, auto)")
                    swarm_presence.save_override(swarm_presence.GLOBAL_PRESENCE_PATH, mode, until)
                    print(f"Set global presence to '{mode}'" + (f" until {time.strftime('%H:%M:%S', time.localtime(until))}" if until else ""))
                elif scope == "local":
                    if mode not in ("in", "out", "auto", "global"):
                        raise ValueError(f"invalid local presence mode: '{mode}' (use in, out, auto, global)")
                    if not session_name:
                        raise ValueError("local presence requires a valid swarm config/session")
                    local_path = swarm_presence.local_presence_path(session_name)
                    swarm_presence.save_override(local_path, mode, until)
                    print(f"Set local presence ({session_name}) to '{mode}'" + (f" until {time.strftime('%H:%M:%S', time.localtime(until))}" if until else ""))
                return 0

            # Query mode
            status = swarm_presence.evaluate_presence(
                session_name=session_name,
                idle_timeout=timeout,
                global_path=swarm_presence.GLOBAL_PRESENCE_PATH,
            )
            if args.json:
                data = {
                    "effective": status.effective,
                    "session": status.session_name,
                    "local": {
                        "mode": status.local.mode,
                        "state": status.local.state,
                        "source": status.local.source,
                        "idle_seconds": status.local.idle_seconds,
                    },
                    "global": {
                        "mode": status.global_eval.mode,
                        "state": status.global_eval.state,
                        "source": status.global_eval.source,
                        "idle_seconds": status.global_eval.idle_seconds,
                    },
                }
                print(json.dumps(data, indent=2))
            else:
                print(status.summary())
            return 0

        cfg = _cfg_from_args(args)
        if args.babysit_command == "start":
            no_action = getattr(args, "no_action", False)
            swarm_babysit.apply_babysit(
                cfg, args.dry_run, no_action, until=_until_from_args(args),
            )
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
