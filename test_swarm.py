from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import json
import os
import random
import shutil
import subprocess
import sys
import time

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parent / "swarm"))

import topology as swarm_start
swarm_apply = swarm_start
import pane_worker as babysit_worker
import session_worker
import babysitctl
import cli as swarm_cli
import init as swarm_init
import common
from common import (
    ROOT_DIR,
    SWARM_CLI,
    build_runtime_map,
    build_this_text,
    effective_config_dict,
    find_aiswarm_config,
    load_config,
    looks_like_config_path,
    resolve_config_path,
)
import tasksctl
import session_ids


def write_config(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "swarm.yaml"
    path.write_text(body)
    return path


def test_load_config_resolves_prompt_file(tmp_path: Path):
    prompt = tmp_path / "hello.txt"
    prompt.write_text("nudge gently")
    cfg_path = write_config(tmp_path, f"""
session_name: demo
windows:
  - window_name: grid
    layout: tiled
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
          babysit:
            enabled: true
            interval_secs: 123
            prompt_file: "{prompt.name}"
""")
    cfg = load_config(cfg_path)
    pane = cfg.panes[0]
    assert cfg.session_name == "demo"
    assert cfg.pane_count == 1
    assert pane.title == "claude"
    assert pane.babysit.enabled is True
    assert pane.babysit.interval_secs == 123
    assert pane.babysit.long_prompt == "nudge gently"
    assert pane.babysit.long_prompt_file == prompt.resolve()
    assert pane.babysit.short_prompt == "nudge gently"


def test_load_config_rejects_short_prompt_only_babysit(tmp_path: Path):
    cfg_path = write_config(tmp_path, """
session_name: demo
windows:
  - window_name: grid
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
          babysit:
            enabled: true
            short_prompt: "only short"
""")
    with pytest.raises(ValueError, match="short_prompt"):
        load_config(cfg_path)


def test_swarm_init_default_3x2_layout():
    text = swarm_init.config_text("demo", flavour="3x2")
    assert text.count("agent: codex") == 2
    assert text.count("agent: claude") == 2
    assert 'agent: antigravity' in text
    assert 'agy --dangerously-skip-permissions' in text
    assert 'agent: grok' in text
    assert 'grok --always-approve -m grok-build' in text
    assert 'title: shell' not in text
    assert 'shell_command: "bash"' not in text


def test_swarm_init_1x1_and_4x2_layouts():
    minimal = swarm_init.config_text("minimal", flavour="1x1")
    assert minimal.count("agent:") == 1
    assert "title: codex heavy" in minimal

    full = swarm_init.config_text("full", flavour="4x2")
    assert full.count("agent:") == 8
    for agent in ("codex", "claude", "antigravity", "grok"):
        assert full.count(f"agent: {agent}") == 2


def test_swarm_init_demo_flavour_layout():
    text = swarm_init.config_text("aiswarm-demo", flavour="demo")
    assert "session_name: aiswarm-demo" in text
    for agent in ("codex", "claude", "antigravity", "grok", "vibe", "copilot"):
        assert f"agent: {agent}" in text
    assert "agent: gemini" not in text
    assert text.count("agent:") == 6
    assert "tasks:" in text
    assert "source: backlog" in text
    assert "backlog_dir: ../backlog" in text  # relative to .aiswarm/config.yaml
    assert text.count("tasks:\n            enabled: true") == 6
    assert 'title: log' in text
    assert 'aiswarm log -w' in text
    assert 'title: shell' in text
    assert "bash --norc --noprofile" in text
    assert "PS1=" in text


def test_swarm_init_babysit_flavour_layout():
    text = swarm_init.config_text("babysit-demo", flavour="babysit")
    assert "session_name: babysit-demo" in text
    assert text.count("babysit:") == 4
    assert text.count("long_prompt_file: prompts/worker_long.md") == 4
    assert text.count("short_prompt_file: prompts/worker_short.txt") == 4
    assert "title: shell" in text


def test_swarm_init_creates_config_prompts_and_agents_block(tmp_path: Path):
    swarm_init.init("demo", tmp_path)
    assert (tmp_path / ".aiswarm" / "config.yaml").exists()
    assert (tmp_path / ".aiswarm" / "prompts" / "worker_long.md").exists()
    assert (tmp_path / ".aiswarm" / "prompts" / "worker_short.txt").exists()
    assert not (tmp_path / ".gitignore").exists()  # init does not gitignore harness
    agents = (tmp_path / "AGENTS.md").read_text()
    assert swarm_init.BLOCK_START in agents
    assert swarm_init.BLOCK_END in agents
    assert "## Swarm" in agents
    assert "`/tmp/nudge-swarm/demo/runtime.json`" in agents
    assert "self-awareness" not in agents
    assert "aiswarm this" in agents
    assert "aiswarm sessions" in agents
    assert "Swarm CLI: `aiswarm`" in agents
    assert "aiswarm instructions overview" in agents
    assert ".aiswarm/config.yaml" in agents
    assert "Do NOT raw `tmux send-keys`" in agents


def test_swarm_init_force_overwrites_existing_files(tmp_path: Path):
    swarm_init.init("demo", tmp_path)
    cfg_path = tmp_path / ".aiswarm" / "config.yaml"
    long_prompt_path = tmp_path / ".aiswarm" / "prompts" / "worker_long.md"

    # Modify initial files
    cfg_path.write_text("custom: config\n")
    long_prompt_path.write_text("custom prompt\n")

    # Without force, existing files are preserved
    swarm_init.init("demo", tmp_path, force=False)
    assert cfg_path.read_text() == "custom: config\n"
    assert long_prompt_path.read_text() == "custom prompt\n"

    # With force, existing files are overwritten
    swarm_init.init("demo", tmp_path, force=True)
    assert "session_name: demo" in cfg_path.read_text()
    assert "Continue the assigned work" in long_prompt_path.read_text()


def test_babysit_stop_workers_tolerates_empty_pid_file(tmp_path: Path, monkeypatch):
    bdir = _write_backlog_project(tmp_path)
    cfg = load_config(write_config(tmp_path, f"""
session_name: demo
tasks:
  backlog_dir: "{bdir}"
windows:
  - window_name: grid
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
"""))
    cfg.runtime_dir.mkdir(parents=True, exist_ok=True)
    babysitctl.supervisor_pid_path(cfg).write_text(" \n")
    monkeypatch.setattr(babysitctl, "process_running", lambda pid: (_ for _ in ()).throw(AssertionError("should not be called")))
    monkeypatch.setattr(babysitctl, "write_runtime_map", lambda cfg: None)
    babysitctl.stop_workers(cfg, dry_run=False)


def test_restart_worker_preserves_runtime_and_comms_state(tmp_path: Path, monkeypatch):
    bdir = _write_backlog_project(tmp_path)
    cfg = load_config(write_config(tmp_path, f'''
session_name: demo_restart
tasks:
  backlog_dir: "{bdir}"
windows:
  - window_name: grid
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
'''))
    monkeypatch.setattr(
        type(cfg), "runtime_dir",
        property(lambda self: tmp_path / "rt" / self.session_name),
    )
    cfg.runtime_dir.mkdir(parents=True)
    old_pid, new_pid = 123, 456
    babysitctl.supervisor_pid_path(cfg).write_text(f"{old_pid}\n")
    babysitctl.pid_path(cfg, "0.0").write_text(f"{old_pid}\n")
    babysitctl.spec_path(cfg, "0.0").write_text('{"long_prompt":"keep"}\n')
    (cfg.runtime_dir / "tasks").mkdir()
    (cfg.runtime_dir / "tasks" / "enabled.json").write_text('{"enabled":true}\n')
    (cfg.runtime_dir / "tasks" / "state.json").write_text(
        '{"assignments":{"0.0":{"task_id":"TASK-1"}}}\n'
    )
    comms = cfg.runtime_dir / "comms.db"
    monkeypatch.setattr(common, "_comms_db_path", lambda session: comms)
    delivered = common.log_send(cfg.session_name, "0.0", "already delivered")
    common.advance_cursor(cfg.session_name, "0.0", delivered)
    pending = common.log_send(cfg.session_name, "0.0", "deliver after restart")
    preserved = {
        path: path.read_bytes()
        for path in (
            babysitctl.spec_path(cfg, "0.0"),
            cfg.runtime_dir / "tasks" / "enabled.json",
            cfg.runtime_dir / "tasks" / "state.json",
            comms,
        )
    }
    running = iter([True, False, False, True])
    monkeypatch.setattr(babysitctl, "process_running", lambda pid: next(running))
    monkeypatch.setattr(
        babysitctl, "_process_argv",
        lambda pid: [sys.executable, str(babysitctl.ROOT_DIR / "session_worker.py"), str(cfg.path)],
    )
    killed = []
    monkeypatch.setattr(babysitctl.os, "kill", lambda pid, sig: killed.append((pid, sig)))
    monkeypatch.setattr(
        babysitctl, "_start_supervisor",
        lambda c, dry_run: babysitctl.supervisor_pid_path(c).write_text(f"{new_pid}\n"),
    )
    monkeypatch.setattr(babysitctl, "write_runtime_map", lambda c: None)

    babysitctl.restart_worker(cfg)

    assert killed == [(old_pid, babysitctl.signal.SIGTERM)]
    assert babysitctl.supervisor_pid_path(cfg).read_text() == f"{new_pid}\n"
    assert babysitctl.pid_path(cfg, "0.0").read_text() == f"{new_pid}\n"
    assert {path: path.read_bytes() for path in preserved} == preserved
    assert common.get_cursors(cfg.session_name)["0.0"] == delivered
    assert [event[0] for event in common.get_pending_events(cfg.session_name, "0.0")] == [pending]


@pytest.mark.parametrize("case", ["missing", "malformed", "stale", "unexpected"])
def test_restart_worker_fails_safely_for_invalid_pid_state(tmp_path: Path, monkeypatch, case):
    cfg = load_config(write_config(tmp_path, '''
session_name: demo
windows:
  - window_name: grid
    panes:
      - shell_command: claude
        nudge: {agent: claude, monitor: true}
'''))
    monkeypatch.setattr(
        type(cfg), "runtime_dir",
        property(lambda self: tmp_path / "rt" / self.session_name),
    )
    cfg.runtime_dir.mkdir(parents=True)
    if case != "missing":
        babysitctl.supervisor_pid_path(cfg).write_text(
            "garbage\n" if case == "malformed" else "123\n"
        )
    monkeypatch.setattr(babysitctl, "process_running", lambda pid: case != "stale")
    monkeypatch.setattr(
        babysitctl, "_process_argv",
        lambda pid: [sys.executable, "/some/other/process.py", str(cfg.path)],
    )
    monkeypatch.setattr(
        babysitctl.os, "kill", lambda *a: pytest.fail("invalid PID state was signalled")
    )

    expected = {"missing": "missing", "malformed": "malformed", "stale": "stale",
                "unexpected": "not the session worker"}[case]
    with pytest.raises(RuntimeError, match=expected):
        babysitctl.restart_worker(cfg)


def test_tasks_status_tolerates_garbage_pid_file(tmp_path: Path, monkeypatch, capsys):
    bdir = _write_backlog_project(tmp_path)
    cfg = load_config(write_config(tmp_path, f"""
session_name: demo
tasks:
  backlog_dir: "{bdir}"
windows:
  - window_name: grid
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
"""))
    cfg.runtime_dir.mkdir(parents=True, exist_ok=True)
    babysitctl.supervisor_pid_path(cfg).write_text("garbage\n")
    monkeypatch.setattr(tasksctl, "process_running", lambda pid: (_ for _ in ()).throw(AssertionError("should not be called")))
    tasksctl.status(cfg)
    out = capsys.readouterr().out
    assert "tasks:   OFF" in out


def test_resolve_config_walk_up_env_and_explicit(tmp_path: Path):
    root = tmp_path / "proj"
    nested = root / "a" / "b"
    nested.mkdir(parents=True)
    cfg = root / ".aiswarm" / "config.yaml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text("session_name: t\nwindows:\n  - window_name: g\n    panes: []\n")
    assert find_aiswarm_config(nested) == cfg.resolve()
    assert resolve_config_path(None, start=nested) == cfg.resolve()

    other = tmp_path / "other.yaml"
    other.write_text("x: 1\n")
    assert resolve_config_path(other) == other.resolve()

    assert resolve_config_path(None, start=tmp_path / "nowhere", env={"AISWARM_CONFIG": str(other)}) == other.resolve()
    # explicit wins over env
    assert resolve_config_path(cfg, env={"AISWARM_CONFIG": str(other)}) == cfg.resolve()

    assert looks_like_config_path("foo.yaml")
    assert looks_like_config_path(other)
    assert not looks_like_config_path("0.2")

    with pytest.raises(FileNotFoundError):
        resolve_config_path(None, start=tmp_path / "empty", env={})


def test_cli_send_token_split():
    assert swarm_cli._split_send_tokens(["0.2", "hi"], None) == (None, "0.2", ["hi"])
    assert swarm_cli._split_send_tokens(["cfg.yaml", "0.2", "hi", "there"], None) == (
        "cfg.yaml",
        "0.2",
        ["hi", "there"],
    )
    assert swarm_cli._split_send_tokens(["0.2", "hi"], "x.yaml") == ("x.yaml", "0.2", ["hi"])


def test_cli_bare_and_instructions(capsys):
    assert swarm_cli.main([]) == 0
    bare = capsys.readouterr().out
    assert "Common workflow:" in bare
    assert "aiswarm instructions" in bare
    assert "aiswarm start" in bare
    assert "aiswarm this" in bare

    assert swarm_cli.main(["instructions"]) == 0
    idx = capsys.readouterr().out
    assert "aiswarm instructions overview" in idx
    assert "aiswarm this" in idx
    assert "handoff" in idx
    assert "tasks" in idx

    assert swarm_cli.main(["instructions", "overview"]) == 0
    ov = capsys.readouterr().out
    assert "Do **not** use raw `tmux send-keys`" in ov or "Do **not** use raw" in ov
    assert "aiswarm send" in ov
    assert "babysit" in ov
    assert "tasks" in ov
    assert "aiswarm this" in ov
    assert "self-awareness" not in ov

    assert swarm_cli.main(["instructions", "handoff"]) == 0
    hf = capsys.readouterr().out
    assert "backlog" in hf.lower()
    assert "send" in hf.lower()
    assert "Do **not** attach" in hf

    assert swarm_cli.main(["instructions", "tasks"]) == 0
    ts = capsys.readouterr().out
    assert "tasks start" in ts
    assert "Done" in ts

    assert swarm_cli.main(["instructions", "nope"]) == 1
    err = capsys.readouterr().err
    assert "unknown guide" in err


def test_swarm_init_does_not_duplicate_agents_block(tmp_path: Path):
    agents = tmp_path / "AGENTS.md"
    agents.write_text("# Existing\n\n## Swarm\n\ncustom\n")
    swarm_init.init("demo", tmp_path)
    text = agents.read_text()
    assert text.count("## Swarm") == 1
    assert text.count(swarm_init.BLOCK_START) == 1
    assert "custom" not in text  # legacy section replaced by managed block
    assert "# Existing" in text


def test_agents_block_upsert_and_remove():
    block_a = swarm_init.agent_block("alpha")
    block_b = swarm_init.agent_block("beta")
    text, action = swarm_init.upsert_agents_text("# Project\n", block_a)
    assert action == "updated"
    assert swarm_init.BLOCK_START in text
    assert "/tmp/nudge-swarm/alpha/" in text
    text2, action2 = swarm_init.upsert_agents_text(text, block_b)
    assert action2 == "updated"
    assert text2.count(swarm_init.BLOCK_START) == 1
    assert "/tmp/nudge-swarm/beta/" in text2
    assert "/tmp/nudge-swarm/alpha/" not in text2
    text3, action3 = swarm_init.upsert_agents_text(text2, block_b)
    assert action3 == "unchanged"
    removed, ok = swarm_init.remove_agents_text(text2)
    assert ok
    assert swarm_init.BLOCK_START not in removed
    assert "# Project" in removed


def test_agents_block_upsert_idempotency_with_following_backlog_block():
    block = swarm_init.agent_block("demo")
    initial_text = "# Project\n\n" + block + "\n<!-- BACKLOG.MD GUIDELINES START -->\nx\n<!-- BACKLOG.MD GUIDELINES END -->\n"
    text = initial_text
    for _ in range(5):
        text, action = swarm_init.upsert_agents_text(text, block)
        assert action == "unchanged"
        assert text == initial_text
        assert text.endswith("<!-- BACKLOG.MD GUIDELINES END -->\n")
        assert not text.endswith("\n\n")

    backlog_only = "# Project\n\n<!-- BACKLOG.MD GUIDELINES START -->\nx\n<!-- BACKLOG.MD GUIDELINES END -->\n"
    text, action = swarm_init.upsert_agents_text(backlog_only, block)
    assert action == "updated"
    assert swarm_init.BLOCK_START in text
    assert "<!-- BACKLOG.MD GUIDELINES START -->" in text
    for _ in range(3):
        next_text, next_action = swarm_init.upsert_agents_text(text, block)
        assert next_action == "unchanged"
        assert next_text == text

    block_b = swarm_init.agent_block("beta")
    updated_text, update_action = swarm_init.upsert_agents_text(text, block_b)
    assert update_action == "updated"
    assert "/tmp/nudge-swarm/beta/" in updated_text
    assert "<!-- BACKLOG.MD GUIDELINES START -->" in updated_text
    for _ in range(3):
        t, a = swarm_init.upsert_agents_text(updated_text, block_b)
        assert a == "unchanged"
        assert t == updated_text



def test_cli_help_prints_probed_model_commands(monkeypatch, capsys):
    def fake_which(command):
        return f"/usr/bin/{command}"

    def fake_run(argv, timeout=5.0):
        class Proc:
            def __init__(self, stdout="", stderr="", returncode=0):
                self.stdout = stdout
                self.stderr = stderr
                self.returncode = returncode

        if argv == ["codex", "debug", "models", "--bundled"]:
            return Proc('{"models":[{"slug":"gpt-test","visibility":"list"}]}')
        if argv == ["grok", "models"]:
            return Proc("Available models:\n  - grok-build\n  * grok-composer-2.5-fast (default)\n")
        if argv[0] in {"claude", "gemini", "qwen", "agy", "grok"}:
            return Proc("Usage\n  -m, --model  Model\n")

        if argv[0] == "vibe":
            return Proc("VIBE_ACTIVE_MODEL Override any config field\n")
        raise AssertionError(f"unexpected command: {argv}")

    monkeypatch.setattr(swarm_cli.shutil, "which", fake_which)
    monkeypatch.setattr(swarm_cli, "_run_capture", fake_run)

    assert swarm_cli.main(["help"]) == 0
    out = capsys.readouterr().out

    assert "codex:" in out
    assert "list: codex debug models --bundled (stable local catalog)" in out
    assert "gpt-test" in out
    assert (
        'shell_command: "codex --dangerously-bypass-approvals-and-sandbox '
        '-m <model>"'
    ) in out
    assert "claude --dangerously-skip-permissions --model <model>" in out
    assert "gemini -y -m <model>" in out
    assert "grok --always-approve -m <model>" in out
    assert "grok-build" in out
    assert "qwen -y -m <model>" in out
    assert "VIBE_ACTIVE_MODEL=<model> vibe --agent auto-approve" in out


def test_babysit_log_nudge_includes_target(tmp_path: Path, monkeypatch):
    log_path = tmp_path / "nudge.log"
    monkeypatch.setenv("BABYSIT_LOG_FILE", str(log_path))

    babysit_worker._log_nudge("demo", "demo:0.2", "idle", "Please continue.")

    line = log_path.read_text()
    assert "demo                 | demo:0.2" in line
    assert "| idle" in line
    assert "Please continue." in line


def test_load_config_multiple_panes(tmp_path: Path):
    cfg_path = write_config(tmp_path, """
session_name: demo
windows:
  - window_name: grid
    layout: tiled
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
      - shell_command: codex
        nudge:
          agent: codex
          monitor: true
      -
""")
    cfg = load_config(cfg_path)
    assert cfg.pane_count == 3
    assert len(cfg.panes) == 3
    assert cfg.panes[0].agent == "claude"
    assert cfg.panes[1].agent == "codex"
    assert cfg.panes[2].agent is None
    assert cfg.panes[2].command == "bash"


def test_load_config_allows_non_agent_pane_when_monitor_disabled(tmp_path: Path):
    cfg_path = write_config(tmp_path, """
session_name: demo
windows:
  - window_name: main
    layout: tiled
    panes:
      - shell_command: htop
        nudge:
          title: shell
          monitor: false
""")
    cfg = load_config(cfg_path)
    pane = cfg.panes[0]
    assert pane.agent is None
    assert pane.title == "shell"
    assert pane.monitor is False


def test_load_config_rejects_babysit_without_monitor(tmp_path: Path):
    cfg_path = write_config(tmp_path, """
session_name: demo
windows:
  - window_name: main
    layout: tiled
    panes:
      - shell_command: htop
        nudge:
          monitor: false
          babysit:
            enabled: true
            prompt: "continue"
""")
    with pytest.raises(ValueError, match="cannot enable babysit when monitor=false"):
        load_config(cfg_path)


def test_load_config_supports_long_and_short_babysit_prompts(tmp_path: Path):
    long_prompt = tmp_path / "long.txt"
    short_prompt = tmp_path / "short.txt"
    long_prompt.write_text("full operating instructions")
    short_prompt.write_text("keep going")
    cfg_path = write_config(tmp_path, f"""
session_name: demo
windows:
  - window_name: main
    layout: tiled
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
          babysit:
            enabled: true
            long_prompt_file: "{long_prompt.name}"
            short_prompt_file: "{short_prompt.name}"
""")
    pane = load_config(cfg_path).panes[0]
    assert pane.babysit.long_prompt == "full operating instructions"
    assert pane.babysit.short_prompt == "keep going"


def test_load_config_supports_clear_every(tmp_path: Path):
    cfg_path = write_config(tmp_path, """
session_name: demo
windows:
  - window_name: main
    layout: tiled
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
          babysit:
            enabled: true
            clear_every: 10
""")
    pane = load_config(cfg_path).panes[0]
    assert pane.babysit.clear_every == 10


def test_start_invokes_grid_monitor_and_command(monkeypatch, tmp_path: Path):
    cfg = load_config(write_config(tmp_path, """
session_name: demo
windows:
  - window_name: grid
    layout: tiled
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
      - shell_command: codex
        nudge:
          agent: codex
          monitor: false
"""))
    calls: list[tuple[str, ...]] = []

    monkeypatch.setattr(swarm_apply, "setup_grid", lambda cfg, dry_run: calls.append(("grid", cfg.session_name, str(dry_run))))
    monkeypatch.setattr(swarm_apply, "ensure_monitor", lambda cfg, pane, agent, dry_run: calls.append(("monitor", pane, agent, str(dry_run))))
    monkeypatch.setattr(swarm_apply, "ensure_title", lambda cfg, pane, title, dry_run: calls.append(("title", pane, title, str(dry_run))))
    monkeypatch.setattr(swarm_apply, "ensure_command", lambda cfg, pane, title, command, dry_run: calls.append(("command", pane, title, command, str(dry_run))) or True)
    monkeypatch.setattr(swarm_apply, "write_runtime_map", lambda cfg: calls.append(("runtime_map", cfg.session_name)))
    monkeypatch.setattr(swarm_apply, "collect_pane_pids", lambda cfg: {})
    monkeypatch.setattr(session_ids, "new_session_id", lambda: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    monkeypatch.setattr(swarm_start.time, "sleep", lambda *_: None)
    monkeypatch.setattr(babysitctl, "apply_babysit", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected babysit apply")))
    monkeypatch.setattr(babysitctl, "ensure_workers", lambda *args, **kwargs: None)

    swarm_start.start(cfg, dry_run=False)

    assert calls[0] == ("grid", "demo", "False")
    assert calls[1] == ("monitor", "0.0", "claude", "False")
    assert calls[2] == ("title", "0.0", "claude", "False")
    assert calls[3] == (
        "command",
        "0.0",
        "claude",
        "claude --session-id aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "False",
    )
    assert calls[4] == ("title", "0.1", "codex", "False")
    assert calls[5] == ("command", "0.1", "codex", "codex", "False")
    assert calls[6] == ("runtime_map", "demo")


def test_start_dry_run_writes_runtime_notes(monkeypatch, tmp_path: Path):
    cfg = load_config(write_config(tmp_path, """
session_name: demo_dry
windows:
  - window_name: main
    layout: tiled
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
"""))
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(swarm_apply, "setup_grid", lambda cfg, dry_run: calls.append(("grid", str(dry_run))))
    monkeypatch.setattr(swarm_apply, "ensure_monitor", lambda cfg, pane, agent, dry_run: calls.append(("monitor", str(dry_run))))
    monkeypatch.setattr(swarm_apply, "ensure_title", lambda cfg, pane, title, dry_run: calls.append(("title", str(dry_run))))
    monkeypatch.setattr(swarm_apply, "ensure_command", lambda cfg, pane, title, command, dry_run: calls.append(("command", str(dry_run))) or True)
    monkeypatch.setattr(swarm_apply, "write_runtime_map", lambda cfg: calls.append(("runtime_map", cfg.session_name)))
    monkeypatch.setattr(swarm_apply, "collect_pane_pids", lambda cfg: {})
    monkeypatch.setattr(babysitctl, "apply_babysit", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected babysit apply")))
    monkeypatch.setattr(babysitctl, "ensure_workers", lambda *args, **kwargs: None)

    swarm_start.start(cfg, dry_run=True)

    assert calls == [
        ("grid", "True"),
        ("monitor", "True"),
        ("title", "True"),
        ("command", "True"),
        ("runtime_map", "demo_dry"),
    ]


def test_setup_grid_allows_new_session_to_expand(monkeypatch, tmp_path: Path):
    cfg = load_config(write_config(tmp_path, """
session_name: demo
windows:
  - window_name: grid
    layout: tiled
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
      - shell_command: codex
        nudge:
          agent: codex
          monitor: true
"""))
    tmux_calls: list[tuple[str, ...]] = []
    pane_counts = iter([1, 2])

    def fake_run(*args, **kwargs):
        class Proc:
            def __init__(self, returncode=0, stdout=""):
                self.returncode = returncode
                self.stdout = stdout
        tmux_calls.append(args)
        if args[:3] == ("tmux", "has-session", "-t"):
            return Proc(1, "")
        if args[:4] == ("tmux", "new-session", "-d", "-s"):
            return Proc(0, "")
        if args[:3] == ("tmux", "list-windows", "-t"):
            return Proc(0, "grid\n")
        if args[:3] == ("tmux", "list-panes", "-t"):
            return Proc(0, "%0\n" if next(pane_counts) == 1 else "%0\n%1\n")
        if args[:3] == ("tmux", "split-window", "-t"):
            return Proc(0, "")
        if args[:3] == ("tmux", "select-layout", "-t"):
            return Proc(0, "")
        raise AssertionError(f"unexpected tmux call: {args}")

    monkeypatch.setattr(swarm_apply, "run", fake_run)
    swarm_start.setup_grid(cfg, dry_run=False)

    assert (
        "tmux",
        "split-window",
        "-t",
        "demo:grid.0",
        "env PS1='$ ' bash --norc --noprofile",
    ) in tmux_calls
    assert ("tmux", "select-layout", "-t", "demo:grid", "tiled") in tmux_calls


def test_babysit_start_updates_pane_spec_without_per_pane_process(monkeypatch, tmp_path: Path):
    cfg = load_config(write_config(tmp_path, """
session_name: demo
windows:
  - window_name: grid
    layout: tiled
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
          babysit:
            enabled: true
            interval_secs: 321
            prompt: "please continue"
"""))
    cfg.runtime_dir.mkdir(parents=True, exist_ok=True)
    calls: list[str] = []
    monkeypatch.setattr(babysitctl, "_start_supervisor", lambda cfg, dry_run: calls.append(cfg.session_name))

    babysitctl.apply_babysit(cfg, dry_run=False)

    assert calls == ["demo"]
    spec = json.loads(babysitctl.spec_path(cfg, "0.0").read_text())
    assert spec["interval_secs"] == 321
    assert spec["long_prompt"] == "please continue"


def test_tasks_start_toggles_session_worker_group(monkeypatch, tmp_path: Path):
    bdir = _write_backlog_project(tmp_path)
    cfg = load_config(write_config(tmp_path, f"""
session_name: demo
tasks:
  backlog_dir: "{bdir}"
windows:
  - window_name: grid
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
"""))
    monkeypatch.setattr(tasksctl, "validate_tasks_config", lambda cfg: None)
    monkeypatch.setattr(tasksctl, "write_runtime_map", lambda cfg: None)
    monkeypatch.setattr(babysitctl, "ensure_workers", lambda cfg, dry_run: None)

    tasksctl.start_dispatcher(cfg)

    assert tasksctl.enabled_path(cfg).exists()
    assert tasksctl.spec_path(cfg).exists()
    assert not tasksctl.pid_path(cfg).exists()
    assert json.loads(tasksctl.enabled_path(cfg).read_text()) == {"enabled": True}
    tasksctl.stop_dispatcher(cfg)
    assert not tasksctl.enabled_path(cfg).exists()


def test_parse_duration_units_and_bare_seconds():
    assert common.parse_duration("3600") == 3600
    assert common.parse_duration("1h") == 3600
    assert common.parse_duration("30m") == 1800
    assert common.parse_duration("90s") == 90
    assert common.parse_duration("1h30m") == 5400
    assert common.parse_duration(" 2H ") == 7200
    with pytest.raises(ValueError):
        common.parse_duration("")
    with pytest.raises(ValueError):
        common.parse_duration("0")
    with pytest.raises(ValueError):
        common.parse_duration("1d")
    with pytest.raises(ValueError):
        common.parse_duration("h1")


def test_tasks_start_for_duration_expires_and_stop_clears(monkeypatch, tmp_path: Path):
    bdir = _write_backlog_project(tmp_path)
    cfg = load_config(write_config(tmp_path, f"""
session_name: demo
tasks:
  backlog_dir: "{bdir}"
windows:
  - window_name: grid
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
"""))
    monkeypatch.setattr(tasksctl, "validate_tasks_config", lambda cfg: None)
    monkeypatch.setattr(tasksctl, "write_runtime_map", lambda cfg: None)
    monkeypatch.setattr(babysitctl, "ensure_workers", lambda cfg, dry_run: None)

    tasksctl.start_dispatcher(cfg, until=1_000.0)
    data = json.loads(tasksctl.enabled_path(cfg).read_text())
    assert data["enabled"] is True
    assert data["until"] == 1_000.0
    assert tasksctl.is_group_enabled(cfg, now=999.0) is True
    assert tasksctl.is_group_enabled(cfg, now=1_000.0) is False
    assert not tasksctl.enabled_path(cfg).exists()

    tasksctl.start_dispatcher(cfg, until=2_000.0)
    tasksctl.start_dispatcher(cfg)  # untimed start overwrites the timer
    assert json.loads(tasksctl.enabled_path(cfg).read_text()) == {"enabled": True}
    tasksctl.stop_dispatcher(cfg)
    assert not tasksctl.enabled_path(cfg).exists()


def test_babysit_start_for_duration_expires_and_stop_clears(monkeypatch, tmp_path: Path):
    cfg = load_config(write_config(tmp_path, """
session_name: demo
windows:
  - window_name: grid
    layout: tiled
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
          babysit:
            enabled: true
            interval_secs: 321
            prompt: "please continue"
"""))
    cfg.runtime_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(babysitctl, "_start_supervisor", lambda cfg, dry_run: None)
    monkeypatch.setattr(babysitctl, "write_runtime_map", lambda cfg: None)

    babysitctl.apply_babysit(cfg, dry_run=False, until=1_000.0)
    spec = json.loads(babysitctl.spec_path(cfg, "0.0").read_text())
    assert spec["long_prompt"] == "please continue"
    assert json.loads(babysitctl.until_path(cfg).read_text()) == {"until": 1_000.0}
    assert babysitctl.expire_if_due(cfg, now=999.0) is False
    assert babysitctl.until_path(cfg).exists()

    assert babysitctl.expire_if_due(cfg, now=1_000.0) is True
    spec = json.loads(babysitctl.spec_path(cfg, "0.0").read_text())
    assert not spec.get("long_prompt")
    assert not babysitctl.until_path(cfg).exists()

    babysitctl.apply_babysit(cfg, dry_run=False, until=2_000.0)
    babysitctl.apply_babysit(cfg, dry_run=False)  # untimed start drops the timer
    assert not babysitctl.until_path(cfg).exists()
    spec = json.loads(babysitctl.spec_path(cfg, "0.0").read_text())
    assert spec["long_prompt"] == "please continue"

    babysitctl.apply_babysit(cfg, dry_run=False, until=3_000.0)
    babysitctl.disable_babysit(cfg, dry_run=False)
    assert not babysitctl.until_path(cfg).exists()

    babysitctl.apply_babysit(cfg, dry_run=False, until=4_000.0)
    babysitctl.stop_workers(cfg, dry_run=False)
    assert not babysitctl.until_path(cfg).exists()


def test_session_worker_expire_timed_groups(monkeypatch, tmp_path: Path):
    cfg = load_config(write_config(tmp_path, """
session_name: demo
windows:
  - window_name: grid
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
"""))
    cfg.runtime_dir.mkdir(parents=True, exist_ok=True)
    calls: list[str] = []
    monkeypatch.setattr(babysitctl, "expire_if_due", lambda cfg, now=None: calls.append("babysit") or False)
    monkeypatch.setattr(tasksctl, "expire_if_due", lambda cfg, now=None: calls.append("tasks") or False)
    session_worker.expire_timed_groups(cfg, now=1_000.0)
    assert calls == ["babysit", "tasks"]


def test_cli_start_for_passes_until(monkeypatch):
    calls: list[tuple] = []
    monkeypatch.setattr(time, "time", lambda: 1_000.0)
    monkeypatch.setattr(swarm_cli, "load_config", lambda path: "CFG")
    monkeypatch.setattr(
        tasksctl,
        "start_dispatcher",
        lambda cfg, dry_run=False, until=None: calls.append(("tasks", until)),
    )
    monkeypatch.setattr(
        babysitctl,
        "apply_babysit",
        lambda cfg, dry_run, no_action=False, until=None: calls.append(("babysit", until)),
    )
    assert swarm_cli.main(["tasks", "start", "examples/swarm-grid.yaml", "--for", "1h"]) == 0
    assert swarm_cli.main(["babysit", "start", "examples/swarm-grid.yaml", "--for", "30m"]) == 0
    assert calls == [("tasks", 4_600.0), ("babysit", 2_800.0)]


def test_pane_worker_ema_spec_controls_next_wait():
    assert session_worker.PaneWorker is babysit_worker.PaneWorker
    worker = babysit_worker.PaneWorker("demo", "0.0")
    worker.nudge_count = 3
    worker.nudge_sent_ts = 900.0
    worker.current_pct = 50.0
    worker.current_reset_ts = 10_900.0
    fast = {
        "interval_secs": 60, "ema_alpha": .3, "ema_safety": .92,
        "ema_k_var": 0, "ema_warmup": 3, "ema_min_wait": 1, "ema_max_wait": 10,
    }
    slow = {**fast, "ema_min_wait": 100, "ema_max_wait": 500}
    assert worker._next_wait(fast, 1_000.0) == 10
    assert worker._next_wait(slow, 1_000.0) == 500


def test_pane_worker_tick_preserves_underscore_session(monkeypatch):
    """Regression: do not split session_name on '_' when querying the monitor."""
    calls: list[tuple[str, str]] = []

    def capture(session, pane, timeout=2.0):
        calls.append((session, pane))
        return {"state": "idle"}

    monkeypatch.setattr(babysit_worker, "query_monitor_socket", capture)
    monkeypatch.setattr(babysit_worker, "_drain_comms", lambda *a, **k: None)
    monkeypatch.setattr(babysit_worker, "_ensure_quota_refresh", lambda *a, **k: None)
    worker = babysit_worker.PaneWorker("my_session", "0.1")
    worker.last_poll = 0.0
    worker.initial_comms = False
    worker.tick(
        {
            "interval_secs": 60,
            "long_prompt": "",
            "short_prompt": "",
            "target": "my_session:0.1",
        },
        now_f=100.0,
    )
    assert calls == [("my_session", "0.1")]


def test_pane_spec_reloads_only_after_mtime_change(tmp_path: Path, monkeypatch):
    cfg = load_config(write_config(tmp_path, """
session_name: demo
windows:
  - window_name: grid
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
"""))
    spec_path = babysitctl.spec_path(cfg, "0.0")
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text('{"interval_secs": 10}\n')
    reads = 0
    original = Path.read_text

    def counting_read(path, *args, **kwargs):
        nonlocal reads
        if path == spec_path:
            reads += 1
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", counting_read)
    cache = {}
    assert session_worker.pane_spec(cfg, "0.0", cache)["interval_secs"] == 10
    assert session_worker.pane_spec(cfg, "0.0", cache)["interval_secs"] == 10
    assert reads == 1

    spec_path.write_text('{"interval_secs": 20}\n')
    stat = spec_path.stat()
    os.utime(spec_path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1))
    assert session_worker.pane_spec(cfg, "0.0", cache)["interval_secs"] == 20
    assert reads == 2


def test_stop_workers_accepts_panespec_list(tmp_path: Path):
    """Regression: stop_workers must use pane.pane, not PaneSpec.replace."""
    cfg = load_config(write_config(tmp_path, """
session_name: demo
windows:
  - window_name: grid
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
          comms: true
"""))
    cfg.runtime_dir.mkdir(parents=True, exist_ok=True)
    for pane in cfg.panes:
        babysitctl.pid_path(cfg, pane.pane).write_text("0\n")
        babysitctl.spec_path(cfg, pane.pane).write_text("{}\n")
        babysitctl.state_path(cfg, pane.pane).write_text("{}\n")
    babysitctl.supervisor_pid_path(cfg).write_text("0\n")
    babysitctl.stop_workers(cfg, dry_run=False)
    assert not babysitctl.supervisor_pid_path(cfg).exists()
    for pane in cfg.panes:
        assert not babysitctl.pid_path(cfg, pane.pane).exists()


def test_swarm_status_reports_window_command_and_monitor(monkeypatch, tmp_path: Path, capsys):
    cfg = load_config(write_config(tmp_path, """
session_name: demo
windows:
  - window_name: grid
    layout: tiled
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
          babysit:
            enabled: true
            prompt: "nudge"
"""))

    def fake_run(*args, **kwargs):
        class Proc:
            def __init__(self, returncode=0, stdout=""):
                self.returncode = returncode
                self.stdout = stdout
        if args[:3] == ("tmux", "has-session", "-t"):
            return Proc(0, "")
        if args[:3] == ("tmux", "list-windows", "-t"):
            return Proc(0, "grid\n")
        if args[:3] == ("tmux", "list-panes", "-t"):
            return Proc(0, "%0\n")
        if args[:3] == ("tmux", "display-message", "-p"):
            return Proc(0, "claude\n")
        raise AssertionError(f"unexpected tmux call: {args}")

    monkeypatch.setattr(swarm_apply, "run", fake_run)
    monkeypatch.setattr(swarm_apply, "_query_monitor", lambda cfg, pane: {"state": "idle"})

    swarm_start.print_status(cfg)
    out = capsys.readouterr().out

    assert "session=demo exists=yes panes=1/1" in out
    lines = out.splitlines()
    matching = [l for l in lines if "demo:0.0" in l]
    assert len(matching) == 1
    assert "claude" in matching[0]
    assert "idle" in matching[0]
    assert any(s in matching[0] for s in ["stopped", "stale", "on", "not started"])


def test_swarm_status_brief_reports_compact_states(monkeypatch, tmp_path: Path, capsys):
    import shutil
    shutil.rmtree("/tmp/nudge-swarm/demo", ignore_errors=True)
    cfg = load_config(write_config(tmp_path, """
session_name: demo
windows:
  - window_name: grid
    layout: tiled
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
      - shell_command: codex
        nudge:
          agent: codex
          monitor: false
"""))

    def fake_run(*args, **kwargs):
        class Proc:
            def __init__(self, returncode=0, stdout=""):
                self.returncode = returncode
                self.stdout = stdout
        if args[:3] == ("tmux", "has-session", "-t"):
            return Proc(0, "")
        if args[:3] == ("tmux", "list-windows", "-t"):
            return Proc(0, "grid\n")
        if args[:3] == ("tmux", "list-panes", "-t"):
            return Proc(0, "%0\n%1\n")
        raise AssertionError(f"unexpected tmux call: {args}")

    monkeypatch.setattr(swarm_apply, "run", fake_run)
    monkeypatch.setattr(swarm_apply, "_query_monitor", lambda cfg, pane: {"state": "working"})

    swarm_start.print_status(cfg, brief=True)
    out = capsys.readouterr().out

    assert "demo panes=2/2" in out
    lines = out.splitlines()
    matching_0 = [l for l in lines if "demo:0.0" in l]
    assert len(matching_0) == 1
    assert "claude" in matching_0[0]
    assert "working" in matching_0[0]
    assert "stopped" in matching_0[0]
    
    matching_1 = [l for l in lines if "demo:0.1" in l]
    assert len(matching_1) == 1
    assert "codex" in matching_1[0]
    assert "off" in matching_1[0]


def test_swarm_status_reports_tasks_state_and_heartbeat(monkeypatch, tmp_path: Path):
    cfg = load_config(write_config(tmp_path, """
session_name: demo_tasks_status
windows:
  - window_name: grid
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
      - shell_command: codex
        nudge:
          agent: codex
          monitor: true
          tasks:
            enabled: false
"""))
    monkeypatch.setattr(
        type(cfg),
        "runtime_dir",
        property(lambda self: tmp_path / "rt" / self.session_name),
    )
    cfg.runtime_dir.mkdir(parents=True)
    (cfg.runtime_dir / "session_worker.pid").write_text("123\n")
    (cfg.runtime_dir / "tasks").mkdir()
    (cfg.runtime_dir / "tasks" / "enabled.json").write_text('{"enabled": true}\n')
    tasksctl.save_worker_state(cfg, 1060)

    def fake_run(*args, **kwargs):
        stdout = "%0\n%1\n" if args[:3] == ("tmux", "list-panes", "-t") else "grid\n"
        return type("Proc", (), {"returncode": 0, "stdout": stdout})()

    monkeypatch.setattr(swarm_apply, "run", fake_run)
    monkeypatch.setattr(swarm_apply, "_query_monitor", lambda cfg, pane: {"state": "idle"})
    monkeypatch.setattr(swarm_apply, "babysit_process_running", lambda pid: True)
    monkeypatch.setattr(swarm_apply.time, "time", lambda: 1000)

    lines = swarm_start.status_lines(cfg)
    assert "Tasks" in lines[2]
    assert "Tasks HB" in lines[2]
    enabled = next(line for line in lines if "demo_tasks_status:0.0" in line)
    disabled = next(line for line in lines if "demo_tasks_status:0.1" in line)
    assert enabled.split()[-2:] == ["on", "60s"]
    assert disabled.split()[-2:] == ["off", "-"]
    assert any("Nudge HB = countdown" in line for line in lines)
    assert any("Tasks HB = countdown" in line for line in lines)


@pytest.mark.parametrize(
    ("pid_text", "running", "expected"),
    [(None, False, "stopped"), ("123", False, "stale")],
)
def test_swarm_status_reports_inactive_tasks_worker(
    monkeypatch, tmp_path: Path, pid_text: str | None, running: bool, expected: str
):
    cfg = load_config(write_config(tmp_path, f"""
session_name: demo_tasks_{expected}
windows:
  - window_name: grid
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
"""))
    monkeypatch.setattr(
        type(cfg),
        "runtime_dir",
        property(lambda self: tmp_path / "rt" / self.session_name),
    )
    (cfg.runtime_dir / "tasks").mkdir(parents=True)
    (cfg.runtime_dir / "tasks" / "enabled.json").write_text('{"enabled": true}\n')
    if pid_text is not None:
        (cfg.runtime_dir / "session_worker.pid").write_text(pid_text)
    monkeypatch.setattr(
        swarm_apply,
        "run",
        lambda *args, **kwargs: type(
            "Proc", (), {
                "returncode": 0,
                "stdout": "%0\n" if args[:3] == ("tmux", "list-panes", "-t") else "grid\n",
            },
        )(),
    )
    monkeypatch.setattr(swarm_apply, "_query_monitor", lambda cfg, pane: {"state": "idle"})
    monkeypatch.setattr(swarm_apply, "babysit_process_running", lambda pid: running)
    row = next(
        line for line in swarm_start.status_lines(cfg)
        if f"demo_tasks_{expected}:0.0" in line
    )
    assert row.split()[-2:] == [expected, "-"]


def test_status_lines_handles_missing_window(monkeypatch, tmp_path: Path):
    cfg = load_config(write_config(tmp_path, """
session_name: demo
windows:
  - window_name: grid
    layout: tiled
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
"""))

    def fake_run(*args, **kwargs):
        class Proc:
            def __init__(self, returncode=0, stdout=""):
                self.returncode = returncode
                self.stdout = stdout
        if args[:3] == ("tmux", "has-session", "-t"):
            return Proc(1, "")
        raise AssertionError(f"unexpected tmux call: {args}")

    monkeypatch.setattr(swarm_apply, "run", fake_run)
    assert swarm_start.status_lines(cfg, brief=True) == ["demo missing"]


def test_shell_prefixed_command_sets_ps1_prefix():
    assert swarm_start.shell_prefixed_command("codex", "codex") == "export PS1='[codex] '\"$PS1\"; codex"


def test_runtime_map_contains_only_derived_runtime_paths(tmp_path: Path):
    cfg = load_config(write_config(tmp_path, """
session_name: demo
windows:
  - window_name: grid
    layout: tiled
    panes:
      - shell_command: htop
        nudge:
          title: shell
          monitor: false
      - shell_command: claude
        nudge:
          title: claude
          agent: claude
          monitor: true
          babysit:
            enabled: true
            prompt: "continue"
"""))
    data = build_runtime_map(cfg)
    assert data["session_name"] == "demo"
    assert data["runtime_dir"] == "/tmp/nudge-swarm/demo"
    assert data["panes"]["0.0"]["target"] == "demo:0.0"
    assert data["panes"]["0.0"]["socket"] is None
    assert data["panes"]["0.1"]["socket"] == "/tmp/demo_0.1.sock"
    assert data["panes"]["0.1"]["babysit"]["pid"] == "/tmp/nudge-swarm/demo/babysit-0-1.pid"
    assert data["panes"]["0.1"]["babysit"]["state"] == "/tmp/nudge-swarm/demo/babysit-0-1.state.json"
    assert data["panes"]["0.1"]["babysit"]["has_long_prompt"] is True
    assert data["panes"]["0.1"]["babysit"]["has_short_prompt"] is True


def test_swarm_status_brief_includes_babysit_countdown(tmp_path: Path):
    cfg = load_config(write_config(tmp_path, """
session_name: demo
windows:
  - window_name: grid
    layout: tiled
    panes:
      - shell_command: claude
        nudge:
          title: claude
          agent: claude
          monitor: true
          babysit:
            enabled: true
            interval_secs: 60
            prompt: "continue"
"""))
    cfg.runtime_dir.mkdir(parents=True, exist_ok=True)
    Path(cfg.runtime_dir / "babysit-0-0.state.json").write_text('{"next_poll_at": 1060, "last_monitor_state": "idle", "next_force_nudge_at": 0}\n')
    from topology import status_lines
    import topology
    real_time = topology.time
    class FakeTime:
        @staticmethod
        def time():
            return 1000
        @staticmethod
        def strftime(fmt):
            return real_time.strftime(fmt)
    topology.time = FakeTime
    topology.run = lambda *args, **kwargs: type("Proc", (), {"returncode": 0, "stdout": "%0\n" if args[:3] == ("tmux", "list-panes", "-t") else "grid"})()
    topology._query_monitor = lambda cfg, pane: {"state": "idle"}
    try:
        lines = status_lines(cfg, brief=True)
    finally:
        topology.time = real_time
    matching = [l for l in lines if "demo:0.0" in l]
    assert len(matching) == 1
    assert matching[0].split() == ["demo:0.0", "claude", "idle", "next=60s"]


def test_swarm_status_brief_shows_stopped_when_babysit_not_running(tmp_path: Path):
    cfg = load_config(write_config(tmp_path, """
session_name: demo_stopped
windows:
  - window_name: grid
    layout: tiled
    panes:
      - shell_command: claude
        nudge:
          title: claude
          agent: claude
          monitor: true
          babysit:
            enabled: true
            interval_secs: 60
            prompt: "continue"
"""))
    import topology
    topology.run = lambda *args, **kwargs: type("Proc", (), {"returncode": 0, "stdout": "%0\n" if args[:3] == ("tmux", "list-panes", "-t") else "grid"})()
    topology._query_monitor = lambda cfg, pane: {"state": "idle"}
    lines = topology.status_lines(cfg, brief=True)
    matching = [l for l in lines if "demo_stopped:0.0" in l]
    assert len(matching) == 1
    assert matching[0].split() == ["demo_stopped:0.0", "claude", "idle", "stopped"]


def test_swarm_status_marks_unreachable_monitor_socket(tmp_path: Path, monkeypatch):
    cfg = load_config(write_config(tmp_path, """
session_name: demo_unreachable
windows:
  - window_name: grid
    layout: tiled
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
"""))
    monkeypatch.setattr(swarm_apply, "run", lambda *args, **kwargs: type("Proc", (), {"returncode": 0, "stdout": "%0\n" if args[:3] == ("tmux", "list-panes", "-t") else "grid"})())
    monkeypatch.setattr(swarm_apply, "query_monitor_socket", lambda s, p, timeout=2.0: {})
    lines = swarm_apply.status_lines(cfg, brief=True)
    matching = [l for l in lines if "demo_unreachable:0.0" in l]
    assert len(matching) == 1
    assert "unreachable" in matching[0]


def test_this_text_points_at_runtime_map(tmp_path: Path):
    cfg = load_config(write_config(tmp_path, """
session_name: demo
windows:
  - window_name: grid
    layout: tiled
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
"""))
    text = build_this_text(cfg)
    assert "Session: demo" in text
    assert f"Config:  {cfg.path}" in text
    assert "Runtime: /tmp/nudge-swarm/demo/runtime.json" in text
    assert "missing" in text  # map not written yet
    assert "0.0" in text
    assert "aiswarm instructions overview" in text


def test_comms_defaults_to_monitor(tmp_path: Path):
    cfg = load_config(write_config(tmp_path, """
session_name: demo
windows:
  - window_name: grid
    layout: tiled
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
          babysit:
            enabled: false
"""))
    assert cfg.panes[0].comms is True
    assert cfg.panes[0].babysit.enabled is False

    cfg2 = load_config(write_config(tmp_path, """
session_name: demo
windows:
  - window_name: grid
    layout: tiled
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
          comms:
            enabled: false
"""))
    assert cfg2.panes[0].comms is False


def test_comms_helpers(tmp_path: Path):
    import os
    from common import (
        init_comms_db,
        log_send,
        log_broadcast,
        log_ack,
        get_events,
        get_pending_events,
        get_pending_broadcasts,
        advance_cursor,
        advance_broadcast_cursor,
        get_cursors,
    )
    # force a temp session db by chdir and monkey the path? but functions hardcode /tmp
    # instead test via direct sqlite for now is complex; test the logic with a session that uses /tmp
    sess = "test_comms_" + str(os.getpid())
    try:
        init_comms_db(sess)
        direct_id = log_send(sess, "0.0", "direct to 0.0")
        log_broadcast(sess, "broadcast msg")
        log_ack(sess, "0.0", direct_id, "0.0", "test:0.0")
        evs = get_events(sess)
        assert len(evs) >= 3
        pane_evs = get_events(sess, "0.0")
        assert any(row[4] == "ack" for row in pane_evs)
        pend = get_pending_events(sess, "0.0")
        assert len(pend) >= 1
        assert all(row[3] != "ack" for row in pend)
        bcasts = get_pending_broadcasts(sess, "0.0")
        assert len(bcasts) >= 1
        # advance
        advance_cursor(sess, "0.0", pend[-1][0])
        advance_broadcast_cursor(sess, "0.0", bcasts[-1][0])
        assert len(get_pending_events(sess, "0.0")) == 0
        curs = get_cursors(sess)
        assert "0.0" in curs
    finally:
        # cleanup
        from common import _comms_db_path
        db = _comms_db_path(sess)
        if db.exists():
            db.unlink()
        # also remove parent if empty? skip


def test_any_message_waits_for_idle_worker_and_delivers_once(monkeypatch):
    sess = f"test_any_idle_{os.getpid()}_{random.randrange(1_000_000)}"
    sent = []
    try:
        common.log_any(sess, "voice note", sender="voice-mcp")
        worker = babysit_worker.PaneWorker(sess, "0.0")
        states = iter(["working", "idle", "idle"])
        monkeypatch.setattr(
            babysit_worker, "query_monitor_socket", lambda *_: {"state": next(states)}
        )
        monkeypatch.setattr(
            babysit_worker, "_send_message", lambda target, msg, simulate=False: sent.append((target, msg))
        )
        spec = {"target": f"{sess}:0.0", "interval_secs": 5, "monitor": True}

        worker.tick(spec, 10)
        assert common.get_pending_any(sess)
        assert sent == []

        worker.tick(spec, 16)
        assert common.get_pending_any(sess) == []
        assert sent == [(f"{sess}:0.0", "voice note")]
        types = [row[4] for row in common.get_events(sess)]
        assert types == ["any", "any-delivery", "ack"]

        worker.tick(spec, 22)
        assert sent == [(f"{sess}:0.0", "voice note")]
    finally:
        shutil.rmtree(Path("/tmp/nudge-swarm") / sess, ignore_errors=True)


def test_any_message_claim_is_atomic():
    sess = f"test_any_atomic_{os.getpid()}_{random.randrange(1_000_000)}"
    try:
        queued = common.log_any(sess, "one consumer")
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda pane: common.claim_any(sess, pane), ["0.0", "0.1"]))
        assert sum(result is not None for result in results) == 1
        events = common.get_events(sess)
        deliveries = [row for row in events if row[4] == "any-delivery"]
        assert len(deliveries) == 1
        meta = json.loads(deliveries[0][6])
        assert meta["queue_event_id"] == queued
        assert meta["selected_pane"] in {"0.0", "0.1"}
    finally:
        shutil.rmtree(Path("/tmp/nudge-swarm") / sess, ignore_errors=True)


def test_any_message_skips_pane_with_task_assignment():
    sess = f"test_any_task_{os.getpid()}_{random.randrange(1_000_000)}"
    runtime = Path("/tmp/nudge-swarm") / sess
    try:
        tasks = runtime / "tasks"
        tasks.mkdir(parents=True)
        (tasks / "state.json").write_text(
            '{"assignments":{"0.0":{"task_id":"TASK-1"}}}\n'
        )
        common.log_any(sess, "unassigned work")
        assert common.claim_any(sess, "0.0") is None
        assert common.get_pending_any(sess)
        assert common.claim_any(sess, "0.1") is not None
    finally:
        shutil.rmtree(runtime, ignore_errors=True)


def test_usage_scraper_timeout_cleans_exact_tmux_session(monkeypatch, tmp_path: Path):
    class TimedOutProcess:
        pid = 4321
        args = ["usage.sh"]
        returncode = -9
        calls = 0
        killed = False

        def communicate(self, timeout=None):
            self.calls += 1
            if self.calls == 1:
                raise subprocess.TimeoutExpired(self.args, timeout)
            return "", ""

        def kill(self):
            self.killed = True

    proc = TimedOutProcess()
    commands = []
    monkeypatch.setattr(common.subprocess, "Popen", lambda *a, **k: proc)
    monkeypatch.setattr(
        common.subprocess,
        "run",
        lambda args, **kwargs: commands.append(args) or subprocess.CompletedProcess(args, 0),
    )

    with pytest.raises(subprocess.TimeoutExpired):
        common._run_usage_scraper(tmp_path / "usage.sh", "codex", timeout=0.1)

    assert proc.killed is True
    assert commands == [["tmux", "kill-session", "-t", "=codex-usage-4321"]]


def test_comms_end_to_end_plain_pane_no_agent(tmp_path: Path):
    """Test the full log → consumer → delivery path with a plain tmux pane (no LLM agent required).

    - Spins up a tmux session + pane.
    - Attaches monitor-bin.
    - Starts a comms-only worker (no babysit prompts).
    - Writes a message to the log for the pane.
    - Waits for the worker to detect idle and deliver it via tmux-send.
    - Verifies the message appears in the pane capture.

    This exercises the consumer independently of any agent.
    """
    if shutil.which("tmux") is None:
        pytest.skip("tmux not available for end-to-end comms test")
    monitor_bin = Path.cwd() / "monitor-bin"
    attach_sh = Path.cwd() / "attach.sh"
    if not monitor_bin.exists():
        pytest.skip("monitor-bin not built (run 'make build')")
    if not attach_sh.exists():
        pytest.skip("attach.sh not found")

    import random
    pid = os.getpid()
    uniq = f"{pid}-{random.randint(1000,9999)}"
    session = f"comms-e2e-{uniq}"
    pane = "0.0"
    target = f"{session}:{pane}"
    sock = f"/tmp/{session}_{pane}.sock"
    runtime = Path("/tmp/nudge-swarm") / session
    runtime.mkdir(parents=True, exist_ok=True)
    worker_log = runtime / "worker.log"
    worker = None
    tmux_started = False

    try:
        # 1. Create plain tmux session (bash pane, no agent)
        subprocess.check_call(["tmux", "new-session", "-d", "-s", session, "-n", "main", "bash"], timeout=5)
        tmux_started = True

        # 2. Attach monitor. Use "grok" (or any) to exercise grok-specific output parsing / idle detection.
        # This lets us test the comms consumer against grok's monitor logic even with a plain pane (no real grok agent needed).
        monitor_agent = "grok"
        subprocess.check_call(
            [str(attach_sh), target, monitor_agent],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10
        )

        # Wait for socket
        for _ in range(30):
            if Path(sock).exists():
                break
            time.sleep(0.1)
        else:
            pytest.fail(f"monitor socket {sock} never appeared")

        # Give it a moment to stabilize to idle
        time.sleep(0.8)

        # 3. Start comms-only worker (interval=2s for faster test, no prompts)
        # This is the consumer that watches the log + monitor and delivers.
        env = dict(
            os.environ,
            BABYSIT_STATE_FILE=str(runtime / "state.json"),
        )
        worker = subprocess.Popen(
            [sys.executable, str(Path.cwd() / "pane_worker.py"), target, "2", "", ""],
            stdout=worker_log.open("ab"),
            stderr=worker_log.open("ab"),
            env=env,
            start_new_session=True,
        )

        # 4. Write a unique message to the log (simulates cli.py send / broadcast --via-log)
        msg = f"COMMS-E2E-TEST-{uniq}"
        from common import log_send, init_comms_db
        init_comms_db(session)
        log_send(session, pane, msg)

        # 5. Poll for delivery (capture the pane; worker should deliver when it sees idle)
        delivered = False
        capture = ""
        for _ in range(40):  # up to ~8s
            try:
                capture = subprocess.check_output(
                    ["tmux", "capture-pane", "-t", target, "-p"],
                    text=True, timeout=2
                )
            except Exception:
                capture = ""
            if msg in capture:
                delivered = True
                break
            time.sleep(0.2)

        # Also peek at worker log for diagnostic
        worker_out = ""
        if worker_log.exists():
            worker_out = worker_log.read_text()[-2000:]

        assert delivered, (
            f"Message never delivered to pane.\n"
            f"Last capture tail: {capture[-300:]!r}\n"
            f"Worker log tail:\n{worker_out}"
        )

    finally:
        # Cleanup
        if worker:
            try:
                worker.terminate()
                worker.wait(timeout=2)
            except Exception:
                try:
                    worker.kill()
                except Exception:
                    pass
        if tmux_started:
            try:
                subprocess.check_call(["tmux", "kill-session", "-t", session], stderr=subprocess.DEVNULL, timeout=3)
            except Exception:
                pass
        # Remove sockets / runtime
        for p in [sock, str(runtime)]:
            try:
                pp = Path(p)
                if pp.is_file():
                    pp.unlink(missing_ok=True)
                elif pp.is_dir():
                    shutil.rmtree(pp, ignore_errors=True)
            except Exception:
                pass



def test_broadcast_targets_monitored_panes_by_default(monkeypatch, tmp_path: Path, capsys):
    cfg = load_config(write_config(tmp_path, """
session_name: demo
windows:
  - window_name: grid
    layout: tiled
    panes:
      - shell_command: claude
        nudge:
          title: claude
          agent: claude
          monitor: true
      - shell_command: htop
        nudge:
          title: shell
          monitor: false
"""))
    calls: list[tuple[str, ...]] = []

    def fake_run(args, check, text):
        calls.append(tuple(args))
        class Proc:
            returncode = 0
        return Proc()

    monkeypatch.setattr(swarm_start.subprocess, "run", fake_run)
    swarm_start.broadcast(cfg, "AGENTS updated", include_nonmonitored=False, dry_run=False)
    out = capsys.readouterr().out

    assert calls == [(str(ROOT_DIR / "tmux-send"), "--no-prefix", "demo:0.0", "AGENTS updated")]
    assert "broadcast to demo:0.0 (claude)" in out


def test_broadcast_can_include_nonmonitored_agents(monkeypatch, tmp_path: Path):
    cfg = load_config(write_config(tmp_path, """
session_name: demo
windows:
  - window_name: grid
    layout: tiled
    panes:
      - shell_command: claude
        nudge:
          title: claude
          agent: claude
          monitor: true
      - shell_command: codex
        nudge:
          title: unmonitored-codex
          agent: codex
          monitor: false
      - shell_command: htop
        nudge:
          title: shell
          monitor: false
"""))
    calls: list[tuple[str, ...]] = []

    def fake_run(args, check, text):
        calls.append(tuple(args))
        class Proc:
            returncode = 0
        return Proc()

    monkeypatch.setattr(swarm_start.subprocess, "run", fake_run)
    swarm_start.broadcast(cfg, "hello all", include_nonmonitored=True, dry_run=False)

    assert calls == [
        (str(ROOT_DIR / "tmux-send"), "--no-prefix", "demo:0.0", "hello all"),
        (str(ROOT_DIR / "tmux-send"), "--no-prefix", "demo:0.1", "hello all"),
    ]


def test_broadcast_rejects_empty_message(tmp_path: Path):
    cfg = load_config(write_config(tmp_path, """
session_name: demo
windows:
  - window_name: grid
    layout: tiled
    panes:
      - shell_command: claude
        nudge:
          title: claude
          agent: claude
          monitor: true
"""))
    with pytest.raises(ValueError, match="must not be empty"):
        swarm_start.broadcast(cfg, "   ", include_nonmonitored=False, dry_run=False)


def test_cli_status_watch_dispatches_to_watch_status(monkeypatch):
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(swarm_cli, "load_config", lambda path: "CFG")
    monkeypatch.setattr(swarm_apply, "watch_status", lambda cfg, brief, interval: calls.append(("watch", cfg, str(brief), str(interval))))
    rc = swarm_cli.main(["status", "examples/swarm-grid.yaml", "--brief", "-w", "--interval", "2.5"])
    assert rc == 0
    assert calls == [("watch", "CFG", "True", "2.5")]


def test_cli_short_options_dispatch(monkeypatch):
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(swarm_cli, "load_config", lambda path: "CFG")
    monkeypatch.setattr(swarm_apply, "print_status", lambda cfg, brief: calls.append(("status", cfg, str(brief))))
    monkeypatch.setattr(swarm_topology := __import__("topology"), "broadcast", lambda cfg, msg, include_nonmonitored, dry_run, via_log=False: calls.append(("broadcast", cfg, msg, str(include_nonmonitored), str(dry_run))))
    rc1 = swarm_cli.main(["status", "examples/swarm-grid.yaml", "-b"])
    rc2 = swarm_cli.main(["broadcast", "examples/swarm-grid.yaml", "hi", "-A", "-D"])
    assert rc1 == 0 and rc2 == 0
    assert calls == [("status", "CFG", "True"), ("broadcast", "CFG", "hi", "True", "True")]


def test_cli_stop_dispatches_to_babysit_and_tmux_stop(monkeypatch):
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(tasksctl, "stop_dispatcher", lambda cfg, dry_run: calls.append(("tasks", cfg.session_name, str(dry_run))))
    monkeypatch.setattr(babysitctl, "stop_workers", lambda cfg, dry_run: calls.append(("workers", cfg.session_name, str(dry_run))))
    monkeypatch.setattr(swarm_cli, "_stop_tmux_session", lambda session_name, dry_run: calls.append(("tmux", session_name, str(dry_run))))
    rc = swarm_cli.main(["stop", "examples/swarm-grid.yaml"])
    assert rc == 0
    assert calls == [
        ("tasks", "agent_grid", "False"),
        ("workers", "agent_grid", "False"),
        ("tmux", "agent_grid", "False"),
    ]


def test_cli_worker_restart_does_not_stop_tmux(monkeypatch):
    calls = []
    monkeypatch.setattr(
        babysitctl, "restart_worker",
        lambda cfg, dry_run=False: calls.append((cfg.session_name, dry_run)),
    )
    monkeypatch.setattr(
        swarm_cli, "_stop_tmux_session",
        lambda *a, **k: pytest.fail("worker restart touched tmux"),
    )

    rc = swarm_cli.main(["worker", "restart", "examples/swarm-grid.yaml", "-D"])

    assert rc == 0
    assert calls == [("agent_grid", True)]


def test_cli_babysit_status_dispatches(monkeypatch):
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(swarm_cli, "load_config", lambda path: "CFG")
    monkeypatch.setattr(babysitctl, "status", lambda cfg: calls.append(("status", cfg)))
    rc = swarm_cli.main(["babysit", "status", "examples/swarm-grid.yaml"])
    assert rc == 0
    assert calls == [("status", "CFG")]


def test_cli_babysit_stop_dispatches_to_disable_babysit(monkeypatch):
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(swarm_cli, "load_config", lambda path: "CFG")
    monkeypatch.setattr(babysitctl, "disable_babysit", lambda cfg, dry_run: calls.append(("disable_babysit", cfg, dry_run)))
    rc = swarm_cli.main(["babysit", "stop", "examples/swarm-grid.yaml"])
    assert rc == 0
    assert calls == [("disable_babysit", "CFG", False)]


def _write_backlog_project(root: Path) -> Path:
    bdir = root / "backlog"
    bdir.mkdir(parents=True, exist_ok=True)
    (bdir / "config.yml").write_text(
        'project_name: "demo"\n'
        'statuses: ["To Do", "In Progress", "Done"]\n'
        'default_status: "To Do"\n'
    )
    (bdir / "tasks").mkdir(exist_ok=True)
    return bdir


def test_load_config_tasks_defaults_and_pane_enable(tmp_path: Path):
    bdir = _write_backlog_project(tmp_path)
    cfg_path = write_config(tmp_path, f"""
session_name: demo
tasks:
  backlog_dir: "{bdir}"
  ingest: ["To Do"]
windows:
  - window_name: grid
    layout: tiled
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
      - shell_command: codex
        nudge:
          agent: codex
          monitor: true
          babysit:
            enabled: true
      - shell_command: bash
        nudge:
          monitor: false
      - shell_command: gemini
        nudge:
          agent: gemini
          monitor: true
          tasks:
            enabled: false
""")
    cfg = load_config(cfg_path)
    assert cfg.tasks is not None
    assert cfg.tasks.source == "backlog"
    assert cfg.tasks.backlog_dir == bdir.resolve()
    assert cfg.tasks.ingest == ["To Do"]
    assert cfg.tasks.unassigned_only is True
    assert cfg.tasks.min_chase_secs == cfg.tasks.poll_secs  # default tracks poll
    assert cfg.tasks.complete_statuses == ["Done"]
    assert cfg.panes[0].tasks_enabled is True   # monitor default on
    assert cfg.panes[1].tasks_enabled is True   # monitor default on (no tasks: key)
    assert cfg.panes[2].tasks_enabled is False  # shell / monitor=false
    assert cfg.panes[3].tasks_enabled is False  # explicit opt-out
    assert [p.pane for p in cfg.task_panes] == ["0.0", "0.1"]
    eff = effective_config_dict(cfg)
    assert eff["tasks"]["enabled_panes"] == ["0.0", "0.1"]
    assert eff["tasks"]["min_chase_secs"] == eff["tasks"]["poll_secs"]
    assert eff["tasks"]["complete_statuses"] == ["Done"]


def test_load_config_tasks_ingest_in_progress_explicit(tmp_path: Path):
    bdir = _write_backlog_project(tmp_path)
    cfg = load_config(write_config(tmp_path, f"""
session_name: demo
tasks:
  backlog_dir: "{bdir}"
  ingest: ["To Do", "In Progress"]
windows:
  - window_name: grid
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
          tasks:
            enabled: true
"""))
    assert cfg.tasks.ingest == ["To Do", "In Progress"]


def test_load_config_tasks_ingest_defaults_to_to_do_and_in_progress(tmp_path: Path):
    """Default must include In Progress or a restarted dispatcher can't recover
    existing claims via recover_assignments_from_backlog (TASK-37/TASK-41)."""
    bdir = _write_backlog_project(tmp_path)
    cfg = load_config(write_config(tmp_path, f"""
session_name: demo
tasks:
  backlog_dir: "{bdir}"
windows:
  - window_name: grid
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
          tasks:
            enabled: true
"""))
    assert cfg.tasks.ingest == ["To Do", "In Progress"]


def test_load_config_rejects_tasks_without_monitor(tmp_path: Path):
    bdir = _write_backlog_project(tmp_path)
    cfg_path = write_config(tmp_path, f"""
session_name: demo
tasks:
  backlog_dir: "{bdir}"
windows:
  - window_name: grid
    panes:
      - shell_command: bash
        nudge:
          monitor: false
          tasks:
            enabled: true
""")
    with pytest.raises(ValueError, match="cannot enable tasks when monitor=false"):
        load_config(cfg_path)


def test_parse_task_list_json_priority_and_status():
    data = {
        "schemaVersion": 1,
        "kind": "task-list",
        "tasks": [
            {"id": "TASK-9", "title": "Design DAG", "status": "To Do", "priority": "high"},
            {"id": "TASK-10", "title": "Session meta", "status": "To Do", "priority": "medium"},
            {"id": "TASK-19", "title": "Low-ish", "status": "To Do", "priority": None},
            {"id": "TASK-3", "title": "Capture", "status": "In Progress", "priority": "low"},
        ],
    }
    tasks = tasksctl.parse_task_list_json(data)
    assert [t.id for t in tasks] == ["TASK-9", "TASK-10", "TASK-3", "TASK-19"]
    assert tasks[0].priority == "HIGH"
    assert tasks[0].status == "To Do"
    assert tasks[2].status == "In Progress"


def test_build_task_prompt_includes_claim_and_complete_instructions(tmp_path: Path):
    bdir = _write_backlog_project(tmp_path)
    cfg = load_config(write_config(tmp_path, f"""
session_name: demo
tasks:
  backlog_dir: "{bdir}"
windows:
  - window_name: grid
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
          tasks:
            enabled: true
"""))
    task = tasksctl.BacklogTask(id="TASK-9", title="Do the thing", status="To Do", priority="HIGH")
    prompt = tasksctl.build_task_prompt(cfg, task, "0.0", "body here")
    assert "TASK-9" in prompt
    assert "aiswarm:demo:0.0" in prompt
    assert "backlog task complete TASK-9" in prompt
    assert "body here" in prompt
    chase = tasksctl.build_task_prompt(cfg, task, "0.0", "full snapshot body", chase=True)
    assert "Reminder:" in chase
    assert "TASK-9" in chase
    assert "full snapshot body" not in chase
    assert "backlog task complete" not in chase


def test_load_config_min_chase_secs_override(tmp_path: Path):
    bdir = _write_backlog_project(tmp_path)
    cfg = load_config(write_config(tmp_path, f"""
session_name: demo
tasks:
  backlog_dir: "{bdir}"
  poll_secs: 30
  min_chase_secs: 90
windows:
  - window_name: grid
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
"""))
    assert cfg.tasks.poll_secs == 30
    assert cfg.tasks.min_chase_secs == 90
    # omitted min_chase_secs → equals poll_secs
    p2 = tmp_path / "p2"
    p2.mkdir()
    cfg2 = load_config(write_config(p2, f"""
session_name: demo2
tasks:
  backlog_dir: "{bdir}"
  poll_secs: 45
windows:
  - window_name: grid
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
"""))
    assert cfg2.tasks.min_chase_secs == 45


def test_chase_due_respects_min_interval():
    now = 1_700_000_000.0
    # no stamps → due
    assert tasksctl.chase_due({}, 300, now=now) is True
    # recent claim → not due
    claimed = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now - 60))
    assert tasksctl.chase_due({"claimed_at": claimed}, 300, now=now) is False
    # old claim → due
    old = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now - 400))
    assert tasksctl.chase_due({"claimed_at": old}, 300, now=now) is True
    # last_chased_at wins over older claimed_at
    recent_chase = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now - 10))
    assert tasksctl.chase_due(
        {"claimed_at": old, "last_chased_at": recent_chase}, 300, now=now
    ) is False
    # min_chase_secs 0 → always due
    assert tasksctl.chase_due({"last_chased_at": recent_chase}, 0, now=now) is True


def test_chase_assigned_skips_when_throttled(tmp_path: Path, monkeypatch, capsys):
    bdir = _write_backlog_project(tmp_path)
    cfg = load_config(write_config(tmp_path, f"""
session_name: demo
tasks:
  backlog_dir: "{bdir}"
  min_chase_secs: 60
  require_idle: false
windows:
  - window_name: grid
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
          tasks:
            enabled: true
"""))
    monkeypatch.setattr(
        type(cfg),
        "runtime_dir",
        property(lambda self: tmp_path / "rt" / self.session_name),
    )
    recent = time.strftime("%Y-%m-%dT%H:%M:%S")
    tasksctl.save_state(
        cfg,
        {
            "assignments": {
                "0.0": {
                    "task_id": "TASK-99",
                    "title": "Stay busy",
                    "assignee": "aiswarm:demo:0.0",
                    "claimed_at": recent,
                }
            },
            "history": [],
        },
    )
    monkeypatch.setattr(
        tasksctl,
        "view_assignment",
        lambda c, p, tid: tasksctl.AssignmentView(
            "open",
            task={"id": tid, "title": "Stay busy", "status": "In Progress", "assignees": ["aiswarm:demo:0.0"]},
        ),
    )
    monkeypatch.setattr(tasksctl, "dependency_gate", lambda *a, **k: tasksctl.DependencyGate(True, False))
    monkeypatch.setattr(tasksctl, "pane_ready_for_prompt", lambda c, p: True)
    delivered: list = []
    monkeypatch.setattr(
        tasksctl,
        "deliver_task_prompt",
        lambda *a, **k: delivered.append(1) or 42,
    )
    actions = tasksctl.chase_assigned(cfg, tasksctl.load_state(cfg), dry_run=False)
    assert actions == []
    assert delivered == []
    # Force due: last_chased_at far in the past
    old = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - 9999))
    state = tasksctl.load_state(cfg)
    state["assignments"]["0.0"]["last_chased_at"] = old
    state["assignments"]["0.0"].pop("claimed_at", None)
    actions = tasksctl.chase_assigned(cfg, state, dry_run=False)
    assert len(actions) == 1
    assert actions[0]["chase"] is True
    assert delivered == [1]
    saved = tasksctl.load_state(cfg)
    assert saved["assignments"]["0.0"].get("last_chased_at")
    out = capsys.readouterr().out
    assert "chased TASK-99" in out


def test_load_config_skip_assignees_default_empty_and_legacy(tmp_path: Path):
    bdir = _write_backlog_project(tmp_path)
    cfg = load_config(write_config(tmp_path, f"""
session_name: demo
tasks:
  backlog_dir: "{bdir}"
windows:
  - window_name: grid
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
"""))
    assert cfg.tasks.skip_assignees == ["human"]
    p2 = tmp_path / "empty_skip"
    p2.mkdir()
    cfg2 = load_config(write_config(p2, f"""
session_name: demo2
tasks:
  backlog_dir: "{bdir}"
  skip_assignees: []
windows:
  - window_name: grid
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
"""))
    assert cfg2.tasks.skip_assignees == []
    p3 = tmp_path / "legacy_ha"
    p3.mkdir()
    cfg3 = load_config(write_config(p3, f"""
session_name: demo3
tasks:
  backlog_dir: "{bdir}"
  human_assignees: [human, "reviewer"]
windows:
  - window_name: grid
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
"""))
    assert cfg3.tasks.skip_assignees == ["human", "reviewer"]


def test_load_config_tasks_complete_statuses(tmp_path: Path):
    bdir = _write_backlog_project(tmp_path)
    cfg = load_config(write_config(tmp_path, f"""
session_name: demo
tasks:
  backlog_dir: "{bdir}"
  complete_statuses: [Done, Closed]
windows:
  - window_name: grid
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
"""))
    assert cfg.tasks.complete_statuses == ["Done", "Closed"]
    eff = effective_config_dict(cfg)
    assert eff["tasks"]["complete_statuses"] == ["Done", "Closed"]
    assert tasksctl.desired_spec(cfg)["complete_statuses"] == ["Done", "Closed"]


def test_load_config_tasks_complete_statuses_rejects_empty(tmp_path: Path):
    bdir = _write_backlog_project(tmp_path)
    with pytest.raises(ValueError, match="complete_statuses"):
        load_config(write_config(tmp_path, f"""
session_name: demo
tasks:
  backlog_dir: "{bdir}"
  complete_statuses: []
windows:
  - window_name: grid
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
"""))


def test_dependency_gate_blocks_any_incomplete_dep(tmp_path: Path, monkeypatch):
    bdir = _write_backlog_project(tmp_path)
    cfg = load_config(write_config(tmp_path, f"""
session_name: demo
tasks:
  backlog_dir: "{bdir}"
windows:
  - window_name: grid
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
"""))
    tasks = {
        "TASK-1": {
            "id": "TASK-1",
            "status": "To Do",
            "dependencies": ["TASK-A", "TASK-B", "TASK-C"],
        },
        "TASK-A": {"id": "TASK-A", "status": "In Progress", "assignees": []},
        "TASK-B": {
            "id": "TASK-B",
            "status": "In Progress",
            "assignees": ["aiswarm:demo:0.2"],
        },
        "TASK-C": {
            "id": "TASK-C",
            "status": "In Progress",
            "assignees": ["Codex GPT-5"],
        },
    }
    monkeypatch.setattr(tasksctl, "view_task_json", lambda c, tid: tasks[tid])
    gate = tasksctl.dependency_gate(cfg, "TASK-1")
    assert gate.blocked is True
    assert set(gate.blocked_on) == {"TASK-A", "TASK-B", "TASK-C"}
    tasks["TASK-A"]["status"] = "Done"
    tasks["TASK-B"]["status"] = "Done"
    tasks["TASK-C"]["status"] = "Done"
    gate2 = tasksctl.dependency_gate(cfg, "TASK-1")
    assert gate2.ready is True
    assert gate2.blocked is False


def test_dependency_gate_finds_task_moved_to_completed(tmp_path: Path, monkeypatch):
    bdir = _write_backlog_project(tmp_path)
    completed = bdir / "completed"
    completed.mkdir()
    (completed / "task-2.md").write_text(
        "---\nid: TASK-2\ntitle: Blocker\nstatus: Done\ndependencies: []\n---\n"
    )
    cfg = load_config(write_config(tmp_path, f"""
session_name: demo
tasks:
  backlog_dir: "{bdir}"
windows:
  - window_name: grid
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
"""))
    parent = {
        "id": "TASK-1",
        "status": "To Do",
        "dependencies": ["TASK-2"],
    }

    def view(_cfg, task_id):
        if task_id == "TASK-1":
            return parent
        raise RuntimeError(f"backlog task {task_id}: Task {task_id} not found.")

    monkeypatch.setattr(tasksctl, "view_task_json", view)
    gate = tasksctl.dependency_gate(cfg, "TASK-1")
    assert gate.ready is True
    assert gate.blocked is False


def test_dependency_gate_reports_genuinely_missing_task(tmp_path: Path, monkeypatch):
    bdir = _write_backlog_project(tmp_path)
    cfg = load_config(write_config(tmp_path, f"""
session_name: demo
tasks:
  backlog_dir: "{bdir}"
windows:
  - window_name: grid
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
"""))
    parent = {
        "id": "TASK-1",
        "status": "To Do",
        "dependencies": ["TASK-MISSING"],
    }

    def view(_cfg, task_id):
        if task_id == "TASK-1":
            return parent
        raise RuntimeError(f"backlog task {task_id}: Task {task_id} not found.")

    monkeypatch.setattr(tasksctl, "view_task_json", view)
    gate = tasksctl.dependency_gate(cfg, "TASK-1")
    assert gate.blocked is True
    assert gate.reason == "missing"
    assert gate.missing == ["TASK-MISSING"]


def test_complete_statuses_non_default_shared_by_gate_and_assignment(
    tmp_path: Path, monkeypatch
):
    """tasks.complete_statuses is honored end-to-end; gate + view_assignment share it."""
    bdir = _write_backlog_project(tmp_path)
    completed = bdir / "completed"
    completed.mkdir()
    (completed / "task-arch.md").write_text(
        "---\nid: TASK-ARCH\ntitle: Archived\nstatus: Closed\ndependencies: []\n---\n"
    )
    cfg = load_config(write_config(tmp_path, f"""
session_name: demo
tasks:
  backlog_dir: "{bdir}"
  complete_statuses: [Closed]
windows:
  - window_name: grid
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
"""))
    tasks = {
        "TASK-1": {
            "id": "TASK-1",
            "status": "To Do",
            "dependencies": ["TASK-DEP", "TASK-ARCH"],
            "assignees": ["aiswarm:demo:0.0"],
        },
        "TASK-DEP": {
            "id": "TASK-DEP",
            "status": "Done",  # default complete, but config only accepts Closed
            "assignees": [],
        },
    }

    def view(_cfg, task_id):
        if task_id in tasks:
            return tasks[task_id]
        raise RuntimeError(f"backlog task {task_id}: Task {task_id} not found.")

    monkeypatch.setattr(tasksctl, "view_task_json", view)

    # Done is NOT complete under this config; Closed (archived) is.
    gate = tasksctl.dependency_gate(cfg, "TASK-1")
    assert gate.blocked is True
    assert gate.blocked_on == ["TASK-DEP"]

    tasks["TASK-DEP"]["status"] = "Closed"
    gate2 = tasksctl.dependency_gate(cfg, "TASK-1")
    assert gate2.ready is True

    # view_assignment uses the same predicate (not a hardcoded "done").
    assert tasksctl.task_is_complete(cfg, {"status": "Closed"}) is True
    assert tasksctl.task_is_complete(cfg, {"status": "Done"}) is False
    assert tasksctl.task_is_complete(cfg, {"status": "closed"}) is True  # casefold

    view_open = tasksctl.view_assignment(cfg, "0.0", "TASK-1")
    assert view_open.kind == "open"

    tasks["TASK-1"]["status"] = "Closed"
    view_done = tasksctl.view_assignment(cfg, "0.0", "TASK-1")
    assert view_done.kind == "done"

    # Default config still treats Done as complete (regression).
    cfg_default = load_config(write_config(tmp_path, f"""
session_name: demo2
tasks:
  backlog_dir: "{bdir}"
windows:
  - window_name: grid
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
"""))
    assert tasksctl.task_is_complete(cfg_default, {"status": "Done"}) is True
    assert tasksctl.task_is_complete(cfg_default, {"status": "Closed"}) is False


def test_tasks_status_labels_blocked_candidates(tmp_path: Path, monkeypatch, capsys):
    bdir = _write_backlog_project(tmp_path)
    cfg = load_config(write_config(tmp_path, f"""
session_name: demo
tasks:
  backlog_dir: "{bdir}"
windows:
  - window_name: grid
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
"""))
    monkeypatch.setattr(
        type(cfg),
        "runtime_dir",
        property(lambda self: tmp_path / "rt" / self.session_name),
    )
    monkeypatch.setattr(tasksctl, "free_task_panes", lambda c, state: ["0.0"])
    monkeypatch.setattr(tasksctl, "list_candidate_tasks", lambda c: [
        tasksctl.BacklogTask(id="TASK-1", title="Ready", status="To Do"),
        tasksctl.BacklogTask(id="TASK-2", title="Blocked", status="To Do"),
    ])
    monkeypatch.setattr(
        tasksctl,
        "dependency_gate",
        lambda c, tid, cache=None: (
            tasksctl.DependencyGate(True, False)
            if tid == "TASK-1"
            else tasksctl.DependencyGate(
                False, True, reason="missing", missing=["TASK-MISSING"]
            )
        ),
    )
    tasksctl.status(cfg)
    out = capsys.readouterr().out
    assert "candidates (2; showing 2: ready 1, blocked 1)" in out
    assert "TASK-1 - Ready (To Do; ready)" in out
    assert "TASK-2 - Blocked (To Do; blocked: missing dependency ids: TASK-MISSING)" in out


def test_task_skipped_for_claim_skip_assignees(tmp_path: Path):
    bdir = _write_backlog_project(tmp_path)
    cfg = load_config(write_config(tmp_path, f"""
session_name: demo
tasks:
  backlog_dir: "{bdir}"
windows:
  - window_name: grid
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
"""))
    assert tasksctl.task_skipped_for_claim(
        cfg, {"id": "T1", "assignees": ["human"]}
    ) is True
    assert tasksctl.task_skipped_for_claim(
        cfg, {"id": "T2", "assignees": ["Codex GPT-5"]}
    ) is False
    assert tasksctl.task_skipped_for_claim(
        cfg, {"id": "T3", "assignees": ["aiswarm:demo:0.0"]}
    ) is False
    assert tasksctl.task_skipped_for_claim(cfg, {"id": "T4", "assignees": []}) is False
    assert tasksctl.is_skip_assignee(cfg, "human") is True
    assert tasksctl.is_swarm_assignee(cfg, "aiswarm:demo:0.1") is True


def test_dispatch_skips_blocked_claim_until_dependency_done(tmp_path: Path, monkeypatch):
    bdir = _write_backlog_project(tmp_path)
    cfg = load_config(write_config(tmp_path, f"""
session_name: demo
tasks:
  backlog_dir: "{bdir}"
  require_idle: false
windows:
  - window_name: grid
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
          tasks:
            enabled: true
"""))
    monkeypatch.setattr(
        type(cfg),
        "runtime_dir",
        property(lambda self: tmp_path / "rt" / self.session_name),
    )
    monkeypatch.setattr(
        tasksctl, "recover_assignments_from_backlog",
        lambda c, state, **kwargs: state,
    )
    monkeypatch.setattr(tasksctl, "reconcile_assignments", lambda c, state: state)
    monkeypatch.setattr(tasksctl, "pane_has_pending", lambda c, p: False)
    tasks = {
        "TASK-1": {"id": "TASK-1", "title": "Blocked", "status": "To Do", "dependencies": ["TASK-2"]},
        "TASK-2": {"id": "TASK-2", "title": "Blocker", "status": "In Progress", "dependencies": []},
        "TASK-3": {"id": "TASK-3", "title": "Ready", "status": "To Do", "dependencies": []},
    }
    monkeypatch.setattr(tasksctl, "list_candidate_tasks", lambda c, **kwargs: [
        tasksctl.BacklogTask(id="TASK-1", title="Blocked", status="To Do", priority="HIGH"),
        tasksctl.BacklogTask(id="TASK-3", title="Ready", status="To Do", priority="LOW"),
    ])
    monkeypatch.setattr(tasksctl, "view_task_json", lambda c, tid: tasks[tid])
    actions = tasksctl.dispatch_once(cfg, dry_run=True)
    assert [a["task_id"] for a in actions] == ["TASK-3"]
    tasks["TASK-2"]["status"] = "Done"
    actions2 = tasksctl.dispatch_once(cfg, dry_run=True)
    assert [a["task_id"] for a in actions2] == ["TASK-1"]


def test_chase_blocks_once_for_open_dependency_then_resumes(tmp_path: Path, monkeypatch, capsys):
    bdir = _write_backlog_project(tmp_path)
    cfg = load_config(write_config(tmp_path, f"""
session_name: demo
tasks:
  backlog_dir: "{bdir}"
  min_chase_secs: 0
  require_idle: false
windows:
  - window_name: grid
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
          tasks:
            enabled: true
"""))
    monkeypatch.setattr(
        type(cfg),
        "runtime_dir",
        property(lambda self: tmp_path / "rt" / self.session_name),
    )
    state = {
        "assignments": {
            "0.0": {
                "task_id": "TASK-1",
                "title": "Blocked",
                "assignee": "aiswarm:demo:0.0",
                "claimed_at": "2026-07-22T00:00:00",
            }
        },
        "history": [],
    }
    tasks = {
        "TASK-1": {
            "id": "TASK-1",
            "title": "Blocked",
            "status": "In Progress",
            "dependencies": ["TASK-2"],
            "assignees": ["aiswarm:demo:0.0"],
        },
        "TASK-2": {"id": "TASK-2", "title": "Review", "status": "In Progress", "dependencies": []},
    }
    monkeypatch.setattr(tasksctl, "view_task_json", lambda c, tid: tasks[tid])
    monkeypatch.setattr(tasksctl, "pane_has_pending", lambda c, p: False)
    delivered: list[int] = []
    monkeypatch.setattr(tasksctl, "deliver_task_prompt", lambda *a, **k: delivered.append(1) or 42)

    actions = tasksctl.chase_assigned(cfg, state, dry_run=False)
    assert actions == []
    err1 = capsys.readouterr().err
    assert "blocked TASK-1" in err1
    blocked = tasksctl.load_state(cfg)["assignments"]["0.0"]
    assert blocked["blocked_on"] == ["TASK-2"]

    actions2 = tasksctl.chase_assigned(cfg, tasksctl.load_state(cfg), dry_run=False)
    assert actions2 == []
    err2 = capsys.readouterr().err
    assert err2 == ""

    tasks["TASK-2"]["status"] = "Done"
    state2 = tasksctl.load_state(cfg)
    actions3 = tasksctl.chase_assigned(cfg, state2, dry_run=False)
    assert [a["task_id"] for a in actions3] == ["TASK-1"]
    assert delivered == [1]


def test_dispatch_once_dry_run_claims_without_side_effects(tmp_path: Path, monkeypatch, capsys):
    bdir = _write_backlog_project(tmp_path)
    cfg = load_config(write_config(tmp_path, f"""
session_name: demo
tasks:
  backlog_dir: "{bdir}"
  require_idle: false
windows:
  - window_name: grid
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
          tasks:
            enabled: true
"""))
    # Isolate runtime under tmp
    monkeypatch.setattr(
        type(cfg),
        "runtime_dir",
        property(lambda self: tmp_path / "rt" / self.session_name),
    )
    monkeypatch.setattr(
        tasksctl, "recover_assignments_from_backlog",
        lambda c, state, **kwargs: state,
    )
    monkeypatch.setattr(tasksctl, "reconcile_assignments", lambda c, state: state)
    monkeypatch.setattr(
        tasksctl,
        "list_candidate_tasks",
        lambda c, **kwargs: [
            tasksctl.BacklogTask(
                id="TASK-42", title="Example", status="To Do", priority="HIGH"
            )
        ],
    )
    monkeypatch.setattr(tasksctl, "pane_has_pending", lambda c, p: False)
    monkeypatch.setattr(tasksctl, "query_monitor_state", lambda s, p: "idle")
    monkeypatch.setattr(tasksctl, "dependency_gate", lambda *a, **k: tasksctl.DependencyGate(True, False))
    monkeypatch.setattr(
        tasksctl,
        "_task_or_none",
        lambda c, tid, cache: {"id": tid, "title": "Example", "status": "To Do", "dependencies": [], "assignees": []},
    )
    actions = tasksctl.dispatch_once(cfg, dry_run=True)
    assert len(actions) == 1
    assert actions[0]["task_id"] == "TASK-42"
    assert actions[0]["pane"] == "0.0"
    assert actions[0]["dry_run"] is True
    # dry-run must not write assignments
    assert tasksctl.load_state(cfg).get("assignments") in ({}, None) or not tasksctl.load_state(cfg).get("assignments")
    out = capsys.readouterr().out
    assert "would claim TASK-42" in out


def test_claim_failure_does_not_save_assignment(tmp_path: Path, monkeypatch, capsys):
    bdir = _write_backlog_project(tmp_path)
    cfg = load_config(write_config(tmp_path, f"""
session_name: demo
tasks:
  backlog_dir: "{bdir}"
  require_idle: false
windows:
  - window_name: grid
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
"""))
    monkeypatch.setattr(type(cfg), "runtime_dir", property(lambda self: tmp_path / "rt" / self.session_name))
    monkeypatch.setattr(
        tasksctl,
        "list_candidate_tasks",
        lambda c: [tasksctl.BacklogTask(id="TASK-42", title="Example", status="To Do", priority="HIGH")],
    )
    monkeypatch.setattr(tasksctl, "dependency_gate", lambda *a, **k: tasksctl.DependencyGate(True, False))
    monkeypatch.setattr(
        tasksctl,
        "_task_or_none",
        lambda c, tid, cache: {"id": tid, "title": "Example", "status": "To Do", "dependencies": [], "assignees": []},
    )
    monkeypatch.setattr(tasksctl, "claim_task", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("nope")))

    assert tasksctl._claim_new_onto_free(cfg, {"assignments": {}}, dry_run=False) == []
    assert tasksctl.load_state(cfg).get("assignments", {}) == {}
    assert "warning: claim TASK-42 -> demo:0.0 failed: nope" in capsys.readouterr().err


def test_delivery_failure_keeps_assignment_for_chase(tmp_path: Path, monkeypatch, capsys):
    bdir = _write_backlog_project(tmp_path)
    cfg = load_config(write_config(tmp_path, f"""
session_name: demo
tasks:
  backlog_dir: "{bdir}"
  require_idle: false
windows:
  - window_name: grid
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
"""))
    monkeypatch.setattr(type(cfg), "runtime_dir", property(lambda self: tmp_path / "rt" / self.session_name))
    monkeypatch.setattr(
        tasksctl,
        "list_candidate_tasks",
        lambda c: [tasksctl.BacklogTask(id="TASK-42", title="Example", status="To Do", priority="HIGH")],
    )
    monkeypatch.setattr(tasksctl, "dependency_gate", lambda *a, **k: tasksctl.DependencyGate(True, False))
    monkeypatch.setattr(
        tasksctl,
        "_task_or_none",
        lambda c, tid, cache: {"id": tid, "title": "Example", "status": "To Do", "dependencies": [], "assignees": []},
    )
    monkeypatch.setattr(tasksctl, "claim_task", lambda *a, **k: "aiswarm:demo:0.0")
    monkeypatch.setattr(
        tasksctl,
        "deliver_task_prompt",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("log unavailable")),
    )

    assert tasksctl._claim_new_onto_free(cfg, {"assignments": {}}, dry_run=False) == []
    assignment = tasksctl.load_state(cfg)["assignments"]["0.0"]
    assert assignment["task_id"] == "TASK-42"
    assert assignment["assignee"] == "aiswarm:demo:0.0"
    assert "assignment retained for chase: log unavailable" in capsys.readouterr().err


def test_healthcheck_pong_ignores_consumer_ack(tmp_path: Path, monkeypatch):
    bdir = _write_backlog_project(tmp_path)
    cfg = load_config(write_config(tmp_path, f"""
session_name: demo
tasks:
  backlog_dir: "{bdir}"
windows:
  - window_name: grid
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
"""))
    nonce = "nonce-123"
    monkeypatch.setattr(
        tasksctl,
        "get_events",
        lambda *a: [(1, "", "0.0:healthcheck:ack", "consumer", "ack", nonce, "{}")],
    )
    assert tasksctl.healthcheck_ponged(cfg, "0.0", nonce) is False
    monkeypatch.setattr(
        tasksctl,
        "get_events",
        lambda *a: [(2, "", "0.0:healthcheck", "agent-pong", "healthcheck-pong", f"pong {nonce}", "{}")],
    )
    assert tasksctl.healthcheck_ponged(cfg, "0.0", nonce) is True


def test_pane_respawn_argv_splits_shell_command():
    assert tasksctl.pane_respawn_argv("claude --safe") == ["claude", "--safe"]
    assert tasksctl.pane_respawn_argv("agy --dangerously-skip-permissions") == [
        "agy",
        "--dangerously-skip-permissions",
    ]
    with pytest.raises(ValueError, match="empty"):
        tasksctl.pane_respawn_argv("   ")


def test_respawn_task_pane_uses_split_argv(tmp_path: Path, monkeypatch):
    bdir = _write_backlog_project(tmp_path)
    cfg = load_config(write_config(tmp_path, f"""
session_name: demo
tasks:
  backlog_dir: "{bdir}"
windows:
  - window_name: grid
    panes:
      - shell_command: claude --safe
        nudge:
          agent: claude
          monitor: true
"""))
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        class R:
            returncode = 0
        return R()

    monkeypatch.setattr(tasksctl.subprocess, "run", fake_run)
    monkeypatch.setattr(tasksctl, "monitor_socket_path", lambda *a: tmp_path / "m.sock")
    tasksctl.respawn_task_pane(cfg, "0.0")
    respawn = next(c for c in calls if c[:1] == ["tmux"] and "respawn-pane" in c)
    assert respawn[:5] == ["tmux", "respawn-pane", "-k", "-t", "demo:0.0"]
    assert respawn[-3:] == ["--", "claude", "--safe"]
    assert any("attach.sh" in " ".join(c) for c in calls)


def test_healthcheck_probe_then_respawn_is_bounded(tmp_path: Path, monkeypatch):
    bdir = _write_backlog_project(tmp_path)
    cfg = load_config(write_config(tmp_path, f"""
session_name: demo
tasks:
  backlog_dir: "{bdir}"
  require_idle: false
  min_chase_secs: 0
  healthcheck_chases: 1
  healthcheck_timeout_secs: 5
  healthcheck_max_restarts: 1
windows:
  - window_name: grid
    panes:
      - shell_command: claude --safe
        nudge:
          agent: claude
          monitor: true
"""))
    monkeypatch.setattr(type(cfg), "runtime_dir", property(lambda self: tmp_path / "rt" / self.session_name))
    monkeypatch.setattr(
        tasksctl,
        "view_assignment",
        lambda *a: tasksctl.AssignmentView("open", task={"id": "TASK-9", "title": "Stalled"}),
    )
    monkeypatch.setattr(tasksctl, "dependency_gate", lambda *a, **k: tasksctl.DependencyGate(True, False))
    monkeypatch.setattr(tasksctl, "pane_ready_for_prompt", lambda *a: True)
    monkeypatch.setattr(tasksctl, "deliver_task_prompt", lambda *a, **k: 7)
    monkeypatch.setattr(tasksctl, "log_send", lambda *a, **k: 8)
    monkeypatch.setattr(tasksctl, "healthcheck_ponged", lambda *a: False)
    state = {"assignments": {"0.0": {"task_id": "TASK-9", "assignee": "aiswarm:demo:0.0"}}}

    tasksctl.chase_assigned(cfg, state)
    probe = state["assignments"]["0.0"]["healthcheck"]
    assert probe["event_id"] == 8
    assert state["assignments"]["0.0"]["idle_chases"] == 1

    respawns = []
    monkeypatch.setattr(tasksctl, "respawn_task_pane", lambda c, p: respawns.append((c, p)))
    probe["sent_at"] = 0
    tasksctl.chase_assigned(cfg, state)
    assert respawns == [(cfg, "0.0")]
    assert state["assignments"]["0.0"]["healthcheck_restarts"] == 1
    assert "healthcheck" not in state["assignments"]["0.0"]

    state["assignments"]["0.0"]["healthcheck"] = {"nonce": "again", "sent_at": 0}
    tasksctl.chase_assigned(cfg, state)
    assert respawns == [(cfg, "0.0")]
    assert state["assignments"]["0.0"].get("healthcheck_exhausted_at")


def test_claim_logs_and_skips_when_task_detail_unavailable(tmp_path: Path, monkeypatch, capsys):
    bdir = _write_backlog_project(tmp_path)
    cfg = load_config(write_config(tmp_path, f"""
session_name: demo
tasks:
  backlog_dir: "{bdir}"
  require_idle: false
windows:
  - window_name: grid
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
          tasks:
            enabled: true
"""))
    monkeypatch.setattr(type(cfg), "runtime_dir", property(lambda self: tmp_path / "rt" / self.session_name))
    monkeypatch.setattr(
        tasksctl,
        "list_candidate_tasks",
        lambda c, **kwargs: [
            tasksctl.BacklogTask(
                id="TASK-404", title="Missing", status="To Do", priority="HIGH"
            )
        ],
    )
    monkeypatch.setattr(tasksctl, "pane_has_pending", lambda c, p: False)
    monkeypatch.setattr(tasksctl, "query_monitor_state", lambda s, p: "idle")
    monkeypatch.setattr(tasksctl, "task_skipped_for_claim", lambda *a, **k: False)
    monkeypatch.setattr(tasksctl, "dependency_gate", lambda *a, **k: tasksctl.DependencyGate(True, False))
    monkeypatch.setattr(tasksctl, "_task_or_none", lambda *a, **k: None)
    actions = tasksctl.dispatch_once(cfg, dry_run=True)
    assert actions == []
    err = capsys.readouterr().err
    assert "skip claim TASK-404" in err


def test_healthcheck_dry_run_does_not_respawn_or_probe(tmp_path: Path, monkeypatch, capsys):
    bdir = _write_backlog_project(tmp_path)
    cfg = load_config(write_config(tmp_path, f"""
session_name: demo
tasks:
  backlog_dir: "{bdir}"
  require_idle: false
  min_chase_secs: 0
  healthcheck_chases: 1
  healthcheck_timeout_secs: 5
windows:
  - window_name: grid
    panes:
      - shell_command: claude --safe
        nudge:
          agent: claude
          monitor: true
"""))
    monkeypatch.setattr(type(cfg), "runtime_dir", property(lambda self: tmp_path / "rt" / self.session_name))
    monkeypatch.setattr(
        tasksctl,
        "view_assignment",
        lambda *a: tasksctl.AssignmentView("open", task={"id": "TASK-9", "title": "Stalled"}),
    )
    monkeypatch.setattr(tasksctl, "dependency_gate", lambda *a, **k: tasksctl.DependencyGate(True, False))
    monkeypatch.setattr(tasksctl, "pane_ready_for_prompt", lambda *a: True)
    monkeypatch.setattr(tasksctl, "healthcheck_ponged", lambda *a: False)
    sent = []
    respawns = []
    monkeypatch.setattr(tasksctl, "log_send", lambda *a, **k: sent.append(1) or 1)
    monkeypatch.setattr(tasksctl, "deliver_task_prompt", lambda *a, **k: sent.append(1) or 1)
    monkeypatch.setattr(tasksctl, "respawn_task_pane", lambda *a: respawns.append(1))

    state = {
        "assignments": {
            "0.0": {
                "task_id": "TASK-9",
                "healthcheck": {"nonce": "n1", "sent_at": 0},
                "healthcheck_restarts": 0,
            }
        }
    }
    tasksctl.chase_assigned(cfg, state, dry_run=True)
    assert respawns == []
    assert sent == []
    assert state["assignments"]["0.0"].get("healthcheck", {}).get("nonce") == "n1"
    out = capsys.readouterr().out
    assert "would respawn TASK-9" in out

    state2 = {"assignments": {"0.0": {"task_id": "TASK-9", "idle_chases": 0}}}
    tasksctl.chase_assigned(cfg, state2, dry_run=True)
    assert sent == []
    assert "healthcheck" not in state2["assignments"]["0.0"]
    out2 = capsys.readouterr().out
    assert "would chase TASK-9" in out2
    assert "would healthcheck probe TASK-9" in out2


def test_require_idle_rejects_unknown_monitor_state(tmp_path: Path, monkeypatch):
    bdir = _write_backlog_project(tmp_path)
    cfg = load_config(write_config(tmp_path, f"""
session_name: demo
tasks:
  backlog_dir: "{bdir}"
windows:
  - window_name: grid
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
          tasks:
            enabled: true
"""))
    monkeypatch.setattr(tasksctl, "pane_has_pending", lambda c, p: False)
    monkeypatch.setattr(tasksctl, "query_monitor_state", lambda s, p: "unknown")
    assert tasksctl.pane_ready_for_prompt(cfg, "0.0") is False
    assert tasksctl.is_pane_free(cfg, "0.0", {"assignments": {}}) is False


def test_dispatch_skips_claim_and_chase_when_monitor_socket_missing(tmp_path: Path, monkeypatch):
    bdir = _write_backlog_project(tmp_path)
    cfg = load_config(write_config(tmp_path, f"""
session_name: demo
tasks:
  backlog_dir: "{bdir}"
windows:
  - window_name: grid
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
          tasks:
            enabled: true
"""))
    monkeypatch.setattr(
        type(cfg),
        "runtime_dir",
        property(lambda self: tmp_path / "rt" / self.session_name),
    )
    monkeypatch.setattr(
        tasksctl,
        "list_candidate_tasks",
        lambda c, **kwargs: [
            tasksctl.BacklogTask(
                id="TASK-7", title="Example", status="To Do", priority="HIGH"
            )
        ],
    )
    monkeypatch.setattr(tasksctl, "pane_has_pending", lambda c, p: False)
    actions = tasksctl.dispatch_once(cfg, dry_run=True)
    assert actions == []


def test_chase_skips_when_monitor_socket_missing(tmp_path: Path, monkeypatch):
    bdir = _write_backlog_project(tmp_path)
    cfg = load_config(write_config(tmp_path, f"""
session_name: demo
tasks:
  backlog_dir: "{bdir}"
windows:
  - window_name: grid
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
          tasks:
            enabled: true
"""))
    monkeypatch.setattr(
        type(cfg),
        "runtime_dir",
        property(lambda self: tmp_path / "rt" / self.session_name),
    )
    state = {
        "assignments": {
            "0.0": {
                "task_id": "TASK-7",
                "title": "Example",
                "assignee": "aiswarm:demo:0.0",
            }
        }
    }
    monkeypatch.setattr(tasksctl, "pane_has_pending", lambda c, p: False)
    monkeypatch.setattr(
        tasksctl,
        "view_assignment",
        lambda cfg, pane, task_id: tasksctl.AssignmentView(
            "open",
            task={"id": task_id, "title": "Example", "status": "To Do"},
        ),
    )
    actions = tasksctl.chase_assigned(cfg, state, dry_run=True)
    assert actions == []


def test_save_state_atomic_rename_no_partial_writes(tmp_path: Path, monkeypatch):
    cfg = load_config(write_config(tmp_path, """
session_name: demo
windows:
  - window_name: grid
    panes:
      - shell_command: claude
"""))
    monkeypatch.setattr(
        type(cfg),
        "runtime_dir",
        property(lambda self: tmp_path / "rt" / self.session_name),
    )
    tasksctl.save_state(cfg, {"assignments": {"0.0": {"task_id": "TASK-1"}}, "history": []})
    path = tasksctl.state_path(cfg)
    assert path.exists()
    assert tasksctl.load_state(cfg)["assignments"]["0.0"]["task_id"] == "TASK-1"
    # no leftover temp files after a successful save
    leftovers = list(path.parent.glob("state.json.tmp.*"))
    assert leftovers == []
    # second save replaces atomically; readers never see a truncated/partial file
    tasksctl.save_state(cfg, {"assignments": {}, "history": ["done"]})
    state = tasksctl.load_state(cfg)
    assert state["assignments"] == {}
    assert state["history"] == ["done"]


def test_cli_tasks_once_and_status_dispatch(monkeypatch):
    calls: list[tuple] = []
    monkeypatch.setattr(swarm_cli, "load_config", lambda path: "CFG")
    monkeypatch.setattr(
        tasksctl,
        "dispatch_once",
        lambda cfg, dry_run=False: calls.append(("once", cfg, dry_run)) or [{"task_id": "TASK-1"}],
    )
    monkeypatch.setattr(tasksctl, "status", lambda cfg: calls.append(("status", cfg)))
    monkeypatch.setattr(
        tasksctl,
        "start_dispatcher",
        lambda cfg, dry_run=False, until=None: calls.append(("start", cfg, dry_run, until)),
    )
    monkeypatch.setattr(tasksctl, "stop_dispatcher", lambda cfg, dry_run=False: calls.append(("stop", cfg, dry_run)))
    assert swarm_cli.main(["tasks", "once", "examples/swarm-grid.yaml", "-D"]) == 0
    assert swarm_cli.main(["tasks", "status", "examples/swarm-grid.yaml"]) == 0
    assert swarm_cli.main(["tasks", "start", "examples/swarm-grid.yaml", "-D"]) == 0
    assert swarm_cli.main(["tasks", "stop", "examples/swarm-grid.yaml"]) == 0
    assert calls == [
        ("once", "CFG", True),
        ("status", "CFG"),
        ("start", "CFG", True, None),
        ("stop", "CFG", False),
    ]


def test_cli_this_command(tmp_path: Path, capsys, monkeypatch):
    cfg_path = write_config(tmp_path, """
session_name: demo
windows:
  - window_name: grid
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
""")
    monkeypatch.chdir(tmp_path)
    assert swarm_cli.main(["this", str(cfg_path)]) == 0
    out = capsys.readouterr().out
    assert "Session: demo" in out
    assert "runtime.json" in out
    assert "0.0" in out


def test_recover_assignments_from_backlog_empty_state_finds_existing_claims(tmp_path: Path, monkeypatch):
    """AC #1: restart with empty state.json recovers aiswarm:session:pane claims from backlog."""
    bdir = _write_backlog_project(tmp_path)
    cfg = load_config(write_config(tmp_path, f"""
session_name: demo
tasks:
  backlog_dir: "{bdir}"
  require_idle: false
windows:
  - window_name: grid
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
          tasks:
            enabled: true
"""))
    monkeypatch.setattr(
        type(cfg),
        "runtime_dir",
        property(lambda self: tmp_path / "rt" / self.session_name),
    )

    # Mock backlog CLI: task list returns a task assigned to our pane
    list_calls = []
    detail_calls = []

    def mock_run_backlog(cfg, args, timeout=30.0):
        list_calls.append(tuple(args))
        result = subprocess.CompletedProcess(args, returncode=0, stdout="", stderr="")
        if "task" in args and "list" in args:
            result.stdout = """{
                "schemaVersion": 1,
                "kind": "task-list",
                "tasks": [{
                    "id": "TASK-99",
                    "title": "Recovered task",
                    "status": "In Progress",
                    "priority": "high",
                    "assignees": ["aiswarm:demo:0.0"]
                }]
            }"""
        return result

    def mock_view_task_json(cfg, task_id):
        detail_calls.append(task_id)
        if task_id == "TASK-99":
            return {
                "id": "TASK-99",
                "title": "Recovered task",
                "status": "In Progress",
                "priority": "high",
                "assignees": ["aiswarm:demo:0.0"],
            }
        return {}

    monkeypatch.setattr(tasksctl, "_run_backlog", mock_run_backlog)
    monkeypatch.setattr(tasksctl, "view_task_json", mock_view_task_json)
    monkeypatch.setattr(tasksctl, "pane_has_pending", lambda c, p: False)
    monkeypatch.setattr(tasksctl, "query_monitor_state", lambda s, p: "idle")

    # Start with empty state (simulating lost state.json)
    state = tasksctl.load_state(cfg)
    assert state.get("assignments") in ({}, None) or not state.get("assignments")

    # Recovery should rebuild assignments from backlog
    state = tasksctl.recover_assignments_from_backlog(cfg, state)

    assert state["assignments"]["0.0"]["task_id"] == "TASK-99"
    assert state["assignments"]["0.0"]["assignee"] == "aiswarm:demo:0.0"
    assert "recovered_at" in state["assignments"]["0.0"]
    assert len(list_calls) == len(cfg.tasks.ingest)
    assert detail_calls == []


def test_recover_assignments_dry_run_does_not_save(tmp_path: Path, monkeypatch):
    bdir = _write_backlog_project(tmp_path)
    cfg = load_config(write_config(tmp_path, f"""
session_name: demo
tasks:
  backlog_dir: "{bdir}"
windows:
  - window_name: grid
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
"""))
    monkeypatch.setattr(
        tasksctl,
        "_run_backlog",
        lambda cfg, args, timeout=30.0: subprocess.CompletedProcess(
            args,
            returncode=0,
            stdout='{"kind":"task-list","tasks":[{"id":"TASK-99","title":"Recovered","status":"In Progress","assignees":["aiswarm:demo:0.0"]}]}',
            stderr="",
        ),
    )
    monkeypatch.setattr(
        tasksctl,
        "view_task_json",
        lambda cfg, task_id: {
            "id": task_id,
            "assignees": ["aiswarm:demo:0.0"],
        },
    )
    monkeypatch.setattr(
        tasksctl,
        "save_state",
        lambda *args, **kwargs: pytest.fail("dry-run recovery wrote state"),
    )
    state = tasksctl.recover_assignments_from_backlog(
        cfg, {"assignments": {}, "history": []}, dry_run=True
    )
    assert state["assignments"]["0.0"]["task_id"] == "TASK-99"


def test_recover_assignments_does_not_override_existing_local_assignments(tmp_path: Path, monkeypatch):
    """AC #2: does not double-claim free To Do already owned by a pane."""
    bdir = _write_backlog_project(tmp_path)
    cfg = load_config(write_config(tmp_path, f"""
session_name: demo
tasks:
  backlog_dir: "{bdir}"
  require_idle: false
windows:
  - window_name: grid
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
          tasks:
            enabled: true
"""))
    monkeypatch.setattr(
        type(cfg),
        "runtime_dir",
        property(lambda self: tmp_path / "rt" / self.session_name),
    )

    # Mock backlog CLI to return a different task
    def mock_run_backlog(cfg, args, timeout=30.0):
        result = subprocess.CompletedProcess(args, returncode=0, stdout="", stderr="")
        if "task" in args and "list" in args:
            result.stdout = """{
                "schemaVersion": 1,
                "kind": "task-list",
                "tasks": [{
                    "id": "TASK-99",
                    "title": "Different task",
                    "status": "In Progress",
                    "priority": "high",
                    "assignees": ["aiswarm:demo:0.0"]
                }]
            }"""
        return result

    def mock_view_task_json(cfg, task_id):
        if task_id == "TASK-99":
            return {
                "id": "TASK-99",
                "title": "Different task",
                "status": "In Progress",
                "priority": "high",
                "assignees": ["aiswarm:demo:0.0"],
            }
        if task_id == "TASK-88":
            return {
                "id": "TASK-88",
                "title": "Local task",
                "status": "In Progress",
                "priority": "high",
                "assignees": ["aiswarm:demo:0.0"],
            }
        return {}

    monkeypatch.setattr(tasksctl, "_run_backlog", mock_run_backlog)
    monkeypatch.setattr(tasksctl, "view_task_json", mock_view_task_json)

    # Start with existing local assignment
    state = {
        "assignments": {
            "0.0": {
                "task_id": "TASK-88",
                "title": "Local task",
                "assignee": "aiswarm:demo:0.0",
                "claimed_at": "2026-07-22T10:00:00",
            }
        },
        "history": []
    }

    # Recovery should NOT override existing assignments
    state = tasksctl.recover_assignments_from_backlog(cfg, state)

    # Local assignment should be preserved
    assert state["assignments"]["0.0"]["task_id"] == "TASK-88"
    assert "claimed_at" in state["assignments"]["0.0"]
    assert "recovered_at" not in state["assignments"]["0.0"]


def test_broadcast_via_log_filtering_and_warning(tmp_path: Path, monkeypatch, capsys):
    from common import init_comms_db, log_broadcast
    from pane_worker import _drain_comms
    from cli import main as cli_main

    # 1. Test warning when sending to a target pane not in config
    cfg_file = write_config(tmp_path, """
session_name: demo_warning
windows:
  - window_name: grid
    layout: tiled
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
""")
    monkeypatch.setenv("AISWARM_CONFIG", str(cfg_file))
    
    try:
        cli_main(["send", "0.9", "hello"])
    except SystemExit:
        pass
    out, err = capsys.readouterr()
    assert "Warning: recipient pane '0.9' is not present in the config" in err

    cli_main(["send", "any", "voice note"])
    out, err = capsys.readouterr()
    assert "target=any" in out
    assert "Warning" not in err
    assert common.get_pending_any("demo_warning")[0][4] == "voice note"

    # 2. Test log_broadcast filtering under _drain_comms
    sess = "demo_warning"
    init_comms_db(sess)

    db_path = Path("/tmp/nudge-swarm") / sess / "comms.db"
    if db_path.exists():
        try:
            db_path.unlink()
        except OSError:
            pass
    init_comms_db(sess)

    # Let's write the specs for 0.0 (monitored agent) and 0.1 (nonmonitored agent)
    spec_0_0 = {
        "session": sess, "pane": "0.0", "target": f"{sess}:0.0",
        "agent": "claude", "monitor": True
    }
    spec_0_1 = {
        "session": sess, "pane": "0.1", "target": f"{sess}:0.1",
        "agent": "codex", "monitor": False
    }

    log_broadcast(sess, "monitored only msg", include_nonmonitored=False)
    
    delivered = []
    def mock_send(target, msg, simulate=False):
        delivered.append((target, msg))
    monkeypatch.setattr("pane_worker._send_message", mock_send)

    _drain_comms(sess, f"{sess}:0.0", "0.0", spec=spec_0_0)
    assert len(delivered) == 1
    assert delivered[0] == (f"{sess}:0.0", "monitored only msg")

    delivered.clear()
    _drain_comms(sess, f"{sess}:0.1", "0.1", spec=spec_0_1)
    assert len(delivered) == 0

    log_broadcast(sess, "all agents msg", include_nonmonitored=True)

    delivered.clear()
    _drain_comms(sess, f"{sess}:0.1", "0.1", spec=spec_0_1)
    assert len(delivered) == 1
    assert delivered[0] == (f"{sess}:0.1", "all agents msg")


def test_dispatch_once_backlog_call_count_independent_of_candidate_count(
    tmp_path: Path, monkeypatch
):
    """AC #5 (TASK-55): a steady-state pass with K assigned panes and M candidates
    makes O(ingest_statuses + K) backlog calls, not O(M) — no per-candidate detail
    fetch when list rows already carry assignees, and reconcile/chase/claim share
    one cache so each task is fetched at most once per pass.
    """
    bdir = _write_backlog_project(tmp_path)
    cfg = load_config(write_config(tmp_path, f"""
session_name: demo
tasks:
  backlog_dir: "{bdir}"
  ingest: ["To Do"]
  require_idle: false
  min_chase_secs: 0
windows:
  - window_name: grid
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
          tasks:
            enabled: true
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
          tasks:
            enabled: true
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
          tasks:
            enabled: true
"""))
    monkeypatch.setattr(
        type(cfg),
        "runtime_dir",
        property(lambda self: tmp_path / "rt" / self.session_name),
    )
    monkeypatch.setattr(tasksctl, "pane_has_pending", lambda c, p: False)

    num_candidates = 50
    detail_tasks = {
        "TASK-A": {
            "id": "TASK-A", "title": "A", "status": "In Progress",
            "assignees": ["aiswarm:demo:0.0"], "dependencies": [],
        },
        "TASK-B": {
            "id": "TASK-B", "title": "B", "status": "In Progress",
            "assignees": ["aiswarm:demo:0.1"], "dependencies": [],
        },
    }
    for i in range(1, num_candidates + 1):
        detail_tasks[f"TASK-{i}"] = {
            "id": f"TASK-{i}", "title": f"cand {i}", "status": "To Do",
            "assignees": [], "dependencies": [],
        }

    calls: list[tuple] = []

    def mock_run_backlog(cfg, args, timeout=30.0):
        calls.append(tuple(args))
        if list(args[:2]) == ["task", "list"]:
            rows = [
                {
                    "id": f"TASK-{i}", "title": f"cand {i}", "status": "To Do",
                    "priority": "", "assignees": [],
                }
                for i in range(1, num_candidates + 1)
            ]
            return subprocess.CompletedProcess(
                args, 0, json.dumps({"kind": "task-list", "tasks": rows}), ""
            )
        if list(args[:2]) == ["task", "edit"]:
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[0] == "task" and len(args) >= 3 and args[2] == "--json":
            task = detail_tasks.get(args[1])
            if task is None:
                return subprocess.CompletedProcess(args, 1, "", "not found")
            return subprocess.CompletedProcess(
                args, 0, json.dumps({"kind": "task", "task": task}), ""
            )
        raise AssertionError(f"unexpected backlog args: {args}")

    monkeypatch.setattr(tasksctl, "_run_backlog", mock_run_backlog)

    tasksctl.save_state(cfg, {
        "assignments": {
            "0.0": {"task_id": "TASK-A", "title": "A", "assignee": "aiswarm:demo:0.0"},
            "0.1": {"task_id": "TASK-B", "title": "B", "assignee": "aiswarm:demo:0.1"},
        },
        "history": [],
    })

    tasksctl.dispatch_once(cfg, dry_run=False)

    # 1 list call ("To Do") + 2 assigned-task detail fetches (TASK-A, TASK-B,
    # reused across recover/reconcile/chase/dependency_gate via the shared cache)
    # + 1 detail fetch for the single candidate claimed onto the one free pane
    # + 1 claim edit. Flat regardless of num_candidates.
    list_calls = [c for c in calls if c[:2] == ("task", "list")]
    detail_calls = [c for c in calls if c[0] == "task" and len(c) >= 3 and c[2] == "--json"]
    edit_calls = [c for c in calls if c[:2] == ("task", "edit")]
    assert len(list_calls) == 1
    assert len(edit_calls) == 1
    assert len(detail_calls) <= 3, f"expected O(K) detail fetches, got {detail_calls}"
    assert len(calls) <= 5, f"expected O(ingest + K) total backlog calls, got {calls}"


def test_todo_task_assigned_to_our_pane_is_dispatched_as_new_claim(tmp_path: Path, monkeypatch):
    """Verify that a task in 'To Do' status already assigned to one of our panes is NOT recovered,
    but is instead treated as a claim candidate, dispatched with the full prompt, and set to In Progress.
    """
    bdir = _write_backlog_project(tmp_path)
    cfg = load_config(write_config(tmp_path, f"""
session_name: demo
tasks:
  backlog_dir: "{bdir}"
  require_idle: false
windows:
  - window_name: grid
    panes:
      - shell_command: claude
        nudge:
          agent: claude
          monitor: true
          tasks:
            enabled: true
"""))
    monkeypatch.setattr(
        type(cfg),
        "runtime_dir",
        property(lambda self: tmp_path / "rt" / self.session_name),
    )

    calls = []

    def mock_run_backlog(cfg, args, timeout=30.0):
        calls.append(tuple(args))
        if list(args[:2]) == ["task", "list"]:
            rows = [{
                "id": "TASK-123",
                "title": "Assigned To Do task",
                "status": "To Do",
                "priority": "high",
                "assignees": ["aiswarm:demo:0.0"]
            }]
            return subprocess.CompletedProcess(
                args, 0, json.dumps({"kind": "task-list", "tasks": rows}), ""
            )
        if list(args[:2]) == ["task", "edit"]:
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[0] == "task" and len(args) >= 3 and args[2] == "--json":
            return subprocess.CompletedProcess(
                args, 0, json.dumps({
                    "kind": "task",
                    "task": {
                        "id": "TASK-123",
                        "title": "Assigned To Do task",
                        "status": "To Do",
                        "priority": "high",
                        "assignees": ["aiswarm:demo:0.0"],
                        "dependencies": [],
                    }
                }), ""
            )
        raise AssertionError(f"unexpected backlog args: {args}")

    monkeypatch.setattr(tasksctl, "_run_backlog", mock_run_backlog)
    monkeypatch.setattr(tasksctl, "pane_has_pending", lambda c, p: False)
    monkeypatch.setattr(tasksctl, "query_monitor_state", lambda s, p: "idle")
    monkeypatch.setattr(tasksctl, "deliver_task_prompt", lambda *a, **k: "evt-123")

    state = tasksctl.load_state(cfg)
    assert not state.get("assignments")

    # Recovery should NOT find it because it's 'To Do'
    state = tasksctl.recover_assignments_from_backlog(cfg, state)
    assert not state.get("assignments")

    # Now dispatch once
    actions = tasksctl.dispatch_once(cfg, dry_run=False)

    # It should have claimed TASK-123 and transitioned it to In Progress
    edit_calls = [c for c in calls if c[:2] == ("task", "edit")]
    assert len(edit_calls) == 1
    # Check that it claimed the task for pane 0.0 with status "In Progress"
    assert "In Progress" in edit_calls[0]
    assert "aiswarm:demo:0.0" in edit_calls[0]


def test_claim_matches_later_preassigned_pane_before_unmatched_pane(tmp_path: Path, monkeypatch):
    bdir = _write_backlog_project(tmp_path)
    cfg = load_config(write_config(tmp_path, f'''\
session_name: demo
tasks:
  backlog_dir: "{bdir}"
  require_idle: false
windows:
  - window_name: grid
    panes:
      - shell_command: claude
        nudge: {{agent: claude, monitor: true, tasks: {{enabled: true}}}}
'''))
    candidates = [tasksctl.BacklogTask(
        "TASK-61", "Later pane", "To Do", assignees=["aiswarm:demo:0.4"]
    )]
    details = {
        "TASK-61": {
            "id": "TASK-61", "title": "Later pane", "status": "To Do",
            "assignees": ["aiswarm:demo:0.4"], "dependencies": [],
        }
    }
    monkeypatch.setattr(tasksctl, "free_task_panes", lambda c, s: ["0.2", "0.4", "0.5"])
    monkeypatch.setattr(tasksctl, "_task_or_none", lambda c, tid, cache: details[tid])

    actions = tasksctl._claim_new_onto_free(
        cfg, {"assignments": {}}, True, candidates=candidates
    )

    assert [(a["task_id"], a["pane"]) for a in actions] == [("TASK-61", "0.4")]


def test_claim_prioritizes_preassigned_before_unassigned_with_max_inflight(
    tmp_path: Path, monkeypatch
):
    bdir = _write_backlog_project(tmp_path)
    cfg = load_config(write_config(tmp_path, f'''\
session_name: demo
tasks:
  backlog_dir: "{bdir}"
  require_idle: false
  max_inflight: 2
windows:
  - window_name: grid
    panes:
      - shell_command: claude
        nudge: {{agent: claude, monitor: true, tasks: {{enabled: true}}}}
'''))
    candidates = [
        tasksctl.BacklogTask("TASK-U", "Unassigned", "To Do", priority="HIGH"),
        tasksctl.BacklogTask("TASK-4", "Pane four", "To Do", assignees=["aiswarm:demo:0.4"]),
        tasksctl.BacklogTask("TASK-5", "Pane five", "To Do", assignees=["aiswarm:demo:0.5"]),
    ]
    details = {
        task.id: {
            "id": task.id, "title": task.title, "status": "To Do",
            "assignees": task.assignees, "dependencies": [],
        }
        for task in candidates
    }
    monkeypatch.setattr(tasksctl, "free_task_panes", lambda c, s: ["0.2", "0.4", "0.5"])
    monkeypatch.setattr(tasksctl, "_task_or_none", lambda c, tid, cache: details[tid])
    monkeypatch.setattr(
        tasksctl, "claim_task",
        lambda c, tid, pane, dry_run=False: tasksctl.claim_assignee(c, pane),
    )
    monkeypatch.setattr(tasksctl, "deliver_task_prompt", lambda *a, **k: "evt")

    dry_actions = tasksctl._claim_new_onto_free(
        cfg, {"assignments": {}}, True, candidates=candidates
    )
    live_actions = tasksctl._claim_new_onto_free(
        cfg, {"assignments": {}}, False, candidates=candidates
    )

    expected = [
        ("TASK-4", "0.4"), ("TASK-5", "0.5")
    ]
    assert [(a["task_id"], a["pane"]) for a in dry_actions] == expected
    assert [(a["task_id"], a["pane"]) for a in live_actions] == expected


def _write_proc_pid(proc_root: Path, pid: int, argv: list[str], children: list[int] | None = None) -> None:
    pdir = proc_root / str(pid)
    task = pdir / "task" / str(pid)
    task.mkdir(parents=True)
    (pdir / "cmdline").write_bytes(b"\0".join(a.encode() for a in argv) + b"\0")
    (task / "children").write_text(" ".join(str(c) for c in (children or [])) + "\n")
    (pdir / "fd").mkdir()


def test_mint_claude_and_grok_session_ids(monkeypatch):
    monkeypatch.setattr(session_ids, "new_session_id", lambda: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    cmd, sid, src = session_ids.mint_launch_command("claude", "claude --dangerously-skip-permissions")
    assert sid == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    assert src == "minted"
    assert cmd.endswith("--session-id aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")

    cmd, sid, src = session_ids.mint_launch_command(
        "grok", "grok --always-approve -m grok-build"
    )
    assert sid == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    assert "--session-id" in cmd


def test_mint_skips_when_resume_or_id_already_present():
    cmd, sid, src = session_ids.mint_launch_command(
        "claude", "claude --session-id 11111111-1111-4111-8111-111111111111"
    )
    assert cmd == "claude --session-id 11111111-1111-4111-8111-111111111111"
    assert sid == "11111111-1111-4111-8111-111111111111"
    assert src == "argv"

    cmd, sid, src = session_ids.mint_launch_command("grok", "grok -r 11111111-1111-4111-8111-111111111111")
    assert sid == "11111111-1111-4111-8111-111111111111"
    assert src == "argv"

    cmd, sid, src = session_ids.mint_launch_command("codex", "codex --dangerously-bypass-approvals-and-sandbox")
    assert cmd == "codex --dangerously-bypass-approvals-and-sandbox"
    assert sid is None


def test_discover_does_not_use_newest_cwd_file(tmp_path: Path):
    home = tmp_path / "home"
    proc = tmp_path / "proc"
    sid_old = "00000000-0000-4000-8000-000000000001"
    sid_live = "00000000-0000-4000-8000-000000000002"
    grok_dir = home / ".grok"
    grok_dir.mkdir(parents=True)
    (grok_dir / "active_sessions.json").write_text(json.dumps([
        {"session_id": sid_old, "pid": 11, "cwd": "/proj"},
        {"session_id": sid_live, "pid": 22, "cwd": "/proj"},
    ]))
    # Newest on-disk session is the *other* pane — must not win.
    sess = grok_dir / "sessions" / "%2Fproj"
    (sess / sid_old).mkdir(parents=True)
    (sess / sid_live).mkdir(parents=True)
    (sess / sid_old / "events.jsonl").write_text("old\n")
    newer = sess / sid_live / "events.jsonl"
    newer.write_text("live\n")
    os.utime(sess / sid_old / "events.jsonl", (1, 9_999_999_999))

    _write_proc_pid(proc, 10, ["bash"], children=[22])
    _write_proc_pid(proc, 22, ["grok", "--always-approve"])

    sid, source, pid = session_ids.discover_session_id("grok", 10, home=home, proc_root=proc)
    assert sid == sid_live
    assert source == "active_sessions"
    assert pid == 22


def test_discover_claude_pid_file_and_grok_fd(tmp_path: Path):
    home = tmp_path / "home"
    proc = tmp_path / "proc"
    claude_sid = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    grok_sid = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    cdir = home / ".claude" / "sessions"
    cdir.mkdir(parents=True)
    (cdir / "31.json").write_text(json.dumps({"pid": 31, "sessionId": claude_sid}))

    _write_proc_pid(proc, 30, ["bash"], children=[31])
    _write_proc_pid(proc, 31, ["claude", "--dangerously-skip-permissions"])
    sid, source, pid = session_ids.discover_session_id("claude", 30, home=home, proc_root=proc)
    assert (sid, source, pid) == (claude_sid, "pid_file", 31)

    events = home / ".grok" / "sessions" / "%2Fproj" / grok_sid / "events.jsonl"
    events.parent.mkdir(parents=True)
    events.write_text("{}\n")
    _write_proc_pid(proc, 40, ["bash"], children=[41])
    _write_proc_pid(proc, 41, ["grok", "--always-approve"])
    fd = proc / "41" / "fd" / "5"
    fd.symlink_to(events)
    sid, source, pid = session_ids.discover_session_id("grok", 40, home=home, proc_root=proc)
    assert (sid, source, pid) == (grok_sid, "proc_fd", 41)


def test_discover_agy_and_codex_from_open_files(tmp_path: Path):
    home = tmp_path / "home"
    proc = tmp_path / "proc"
    agy_sid = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
    db = home / ".gemini" / "antigravity-cli" / "conversations" / f"{agy_sid}.db"
    db.parent.mkdir(parents=True)
    db.write_bytes(b"sqlite")
    _write_proc_pid(proc, 50, ["bash"], children=[51])
    _write_proc_pid(proc, 51, ["agy", "--dangerously-skip-permissions"])
    (proc / "51" / "fd" / "8").symlink_to(db)
    sid, source, pid = session_ids.discover_session_id("antigravity", 50, home=home, proc_root=proc)
    assert (sid, source, pid) == (agy_sid, "proc_fd", 51)

    codex_sid = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
    rollout = home / ".codex" / "sessions" / "2026" / "09" / f"rollout-2026-09-13-{codex_sid}.jsonl"
    other = home / ".codex" / "sessions" / "2026" / "09" / "rollout-2026-09-13-eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee.jsonl"
    rollout.parent.mkdir(parents=True)
    other.write_text("newer-other-pane\n")
    os.utime(other, (1, 9_999_999_999))
    rollout.write_text("this-pane\n")
    _write_proc_pid(proc, 60, ["bash"], children=[61])
    _write_proc_pid(proc, 61, ["codex"])
    (proc / "61" / "fd" / "9").symlink_to(rollout)
    sid, source, pid = session_ids.discover_session_id("codex", 60, home=home, proc_root=proc)
    assert (sid, source, pid) == (codex_sid, "proc_fd", 61)


def test_refresh_records_and_runtime_map(tmp_path: Path, monkeypatch):
    cfg = load_config(write_config(tmp_path, """
session_name: sidtest
windows:
  - window_name: grid
    panes:
      - shell_command: grok --always-approve
        nudge: {agent: grok, monitor: true}
      - shell_command: claude
        nudge: {agent: claude, monitor: true}
"""))
    monkeypatch.setattr(session_ids, "new_session_id", lambda: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    cmd, sid, src = session_ids.mint_launch_command("claude", "claude")
    recs = {
        "0.1": session_ids.make_record("0.1", "claude", sid, src),
    }
    session_ids.save_records(cfg, recs)
    home = tmp_path / "home"
    proc = tmp_path / "proc"
    grok_sid = "ffffffff-ffff-4fff-8fff-ffffffffffff"
    grok_dir = home / ".grok"
    grok_dir.mkdir(parents=True)
    (grok_dir / "active_sessions.json").write_text(json.dumps([
        {"session_id": grok_sid, "pid": 71, "cwd": str(tmp_path)},
    ]))
    _write_proc_pid(proc, 70, ["bash"], children=[71])
    _write_proc_pid(proc, 71, ["grok", "--always-approve"])
    records = session_ids.refresh_records(
        cfg, {"0.0": 70, "0.1": 80}, home=home, proc_root=proc
    )
    assert records["0.0"].session_id == grok_sid
    assert records["0.0"].source == "active_sessions"
    assert records["0.1"].session_id == sid
    data = build_runtime_map(cfg)
    assert data["panes"]["0.0"]["session"]["id"] == grok_sid
    assert data["panes"]["0.1"]["session"]["id"] == sid
    text = session_ids.format_records(cfg, records)
    assert "grok -r" in text
    assert "claude -r" in text


def test_cli_sessions_no_refresh(tmp_path: Path, capsys):
    cfg_path = write_config(tmp_path, """
session_name: sidcli
windows:
  - window_name: grid
    panes:
      - shell_command: grok
        nudge: {agent: grok, monitor: true}
""")
    cfg = load_config(cfg_path)
    rec = session_ids.make_record(
        "0.0", "grok", "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", "minted"
    )
    session_ids.save_records(cfg, {"0.0": rec})
    assert swarm_cli.main(["sessions", "--no-refresh", "-c", str(cfg_path)]) == 0
    out = capsys.readouterr().out
    assert "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee" in out
    assert "grok -r" in out
