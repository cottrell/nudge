from pathlib import Path
import os
import random
import shutil
import subprocess
import sys
import time

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parent / "swarm"))

import topology as swarm_apply
import babysit as babysit_worker
import babysitctl
import cli as swarm_cli
import init as swarm_init
from common import ROOT_DIR, SWARM_CLI, build_runtime_map, build_self_awareness_text, load_config


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


def test_swarm_init_creates_config_prompts_and_agents_block(tmp_path: Path):
    swarm_init.init("demo", tmp_path)
    assert (tmp_path / "swarm" / "demo.yaml").exists()
    assert (tmp_path / "swarm" / "prompts" / "worker_long.md").exists()
    assert (tmp_path / "swarm" / "prompts" / "worker_short.txt").exists()
    agents = (tmp_path / "AGENTS.md").read_text()
    assert "## Swarm" in agents
    assert "Runtime map: `/tmp/nudge-swarm/demo/runtime.json`" in agents
    assert "Self-awareness note: `/tmp/nudge-swarm/demo/self-awareness.txt`" in agents
    assert "ALWAYS use `tmux-send`" in agents
    assert "Do NOT use raw `tmux send-keys ... Enter`" in agents


def test_swarm_init_does_not_duplicate_agents_block(tmp_path: Path):
    agents = tmp_path / "AGENTS.md"
    agents.write_text("# Existing\n\n## Swarm\n\ncustom\n")
    swarm_init.init("demo", tmp_path)
    assert agents.read_text().count("## Swarm") == 1


def test_cli_help_prints_probed_model_commands(monkeypatch, capsys):
    def fake_which(command):
        return f"/usr/bin/{command}"

    def fake_run(argv, timeout=5.0):
        class Proc:
            def __init__(self, stdout="", stderr="", returncode=0):
                self.stdout = stdout
                self.stderr = stderr
                self.returncode = returncode

        if argv == ["codex", "debug", "models"]:
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
    assert "list: codex debug models" in out
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


def test_apply_invokes_grid_monitor_and_command(monkeypatch, tmp_path: Path):
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
    monkeypatch.setattr(swarm_apply, "ensure_command", lambda cfg, pane, title, command, dry_run: calls.append(("command", pane, title, command, str(dry_run))))
    monkeypatch.setattr(swarm_apply, "write_runtime_map", lambda cfg: calls.append(("runtime_map", cfg.session_name)))
    monkeypatch.setattr(swarm_apply, "write_self_awareness_text", lambda cfg: calls.append(("self_awareness", cfg.session_name)))
    monkeypatch.setattr(swarm_apply.time, "sleep", lambda *_: None)
    monkeypatch.setattr(babysitctl, "apply", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected babysit apply")))
    monkeypatch.setattr(babysitctl, "apply_comms", lambda *args, **kwargs: None)

    swarm_apply.apply(cfg, dry_run=False)

    assert calls == [
        ("grid", "demo", "False"),
        ("monitor", "0.0", "claude", "False"),
        ("title", "0.0", "claude", "False"),
        ("command", "0.0", "claude", "claude", "False"),
        ("title", "0.1", "codex", "False"),
        ("command", "0.1", "codex", "codex", "False"),
        ("runtime_map", "demo"),
        ("self_awareness", "demo"),
    ]


def test_apply_dry_run_writes_runtime_notes(monkeypatch, tmp_path: Path):
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
    monkeypatch.setattr(swarm_apply, "ensure_command", lambda cfg, pane, title, command, dry_run: calls.append(("command", str(dry_run))))
    monkeypatch.setattr(swarm_apply, "write_runtime_map", lambda cfg: calls.append(("runtime_map", cfg.session_name)))
    monkeypatch.setattr(swarm_apply, "write_self_awareness_text", lambda cfg: calls.append(("self_awareness", cfg.session_name)))
    monkeypatch.setattr(babysitctl, "apply", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected babysit apply")))
    monkeypatch.setattr(babysitctl, "apply_comms", lambda *args, **kwargs: None)

    swarm_apply.apply(cfg, dry_run=True)

    assert calls == [
        ("grid", "True"),
        ("monitor", "True"),
        ("title", "True"),
        ("command", "True"),
        ("runtime_map", "demo_dry"),
        ("self_awareness", "demo_dry"),
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
    swarm_apply.setup_grid(cfg, dry_run=False)

    assert ("tmux", "split-window", "-t", "demo:grid.0", "bash") in tmux_calls
    assert ("tmux", "select-layout", "-t", "demo:grid", "tiled") in tmux_calls


def test_babysit_apply_restarts_worker_when_spec_changes(monkeypatch, tmp_path: Path):
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
    babysitctl.pid_path(cfg, "0.0").write_text("1234")
    babysitctl.spec_path(cfg, "0.0").write_text("""{
  "session": "demo",
  "pane": "0.0",
  "target": "demo:0.0",
  "interval_secs": 600,
  "long_prompt": "old long",
  "short_prompt": "old short"
}
""")
    actions: list[tuple[str, ...]] = []

    monkeypatch.setattr(babysitctl, "process_running", lambda pid: pid == 1234)
    monkeypatch.setattr(babysitctl, "stop_worker", lambda cfg, pane, dry_run: actions.append(("stop", pane, str(dry_run))))
    monkeypatch.setattr(babysitctl, "start_worker", lambda cfg, pane, interval, clear_every, long_prompt, short_prompt, lp_file, sp_file, via_log, dry_run: actions.append(("start", pane, str(interval), str(clear_every), long_prompt, short_prompt, lp_file, sp_file, str(via_log), str(dry_run))))

    babysitctl.apply(cfg, dry_run=False)

    assert actions == [
        ("stop", "0.0", "False"),
        ("start", "0.0", "321", "0", "please continue", "please continue", "", "", "True", "False"),
    ]


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

    swarm_apply.print_status(cfg)
    out = capsys.readouterr().out

    assert "session=demo exists=yes panes=1/1" in out
    lines = out.splitlines()
    matching = [l for l in lines if "demo:0.0" in l]
    assert len(matching) == 1
    assert "claude" in matching[0]
    assert "idle" in matching[0]
    assert "on" in matching[0]


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

    swarm_apply.print_status(cfg, brief=True)
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
    assert swarm_apply.status_lines(cfg, brief=True) == ["demo missing"]


def test_shell_prefixed_command_sets_ps1_prefix():
    assert swarm_apply.shell_prefixed_command("codex", "codex") == "export PS1='[codex] '\"$PS1\"; codex"


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


def test_self_awareness_text_mentions_runtime_map_and_status(tmp_path: Path):
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
    text = build_self_awareness_text(cfg)
    assert "Runtime map: /tmp/nudge-swarm/demo/runtime.json" in text
    assert f"Status: python {SWARM_CLI} status {cfg.path} --brief" in text
    assert f"Watch: python {SWARM_CLI} status {cfg.path} --brief -w" in text
    assert "log_send" in text or "tmux-send" in text
    assert "Do NOT use raw tmux send-keys" in text


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
    from common import init_comms_db, log_send, log_broadcast, get_events, get_pending_events, get_pending_broadcasts, advance_cursor, advance_broadcast_cursor, get_cursors
    # force a temp session db by chdir and monkey the path? but functions hardcode /tmp
    # instead test via direct sqlite for now is complex; test the logic with a session that uses /tmp
    sess = "test_comms_" + str(os.getpid())
    try:
        init_comms_db(sess)
        log_send(sess, "0.0", "direct to 0.0")
        log_broadcast(sess, "broadcast msg")
        evs = get_events(sess)
        assert len(evs) >= 2
        pend = get_pending_events(sess, "0.0")
        assert len(pend) >= 1
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
            [sys.executable, str(Path.cwd() / "babysit.py"), target, "2", "", ""],
            stdout=worker_log.open("ab"),
            stderr=worker_log.open("ab"),
            env=env,
            start_new_session=True,
        )

        # 4. Write a unique message to the log (simulates aiswarm send / broadcast --via-log)
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

    monkeypatch.setattr(swarm_apply.subprocess, "run", fake_run)
    swarm_apply.broadcast(cfg, "AGENTS updated", include_nonmonitored=False, dry_run=False)
    out = capsys.readouterr().out

    assert calls == [(str(ROOT_DIR / "tmux-send"), "demo:0.0", "broadcast: AGENTS updated")]
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

    monkeypatch.setattr(swarm_apply.subprocess, "run", fake_run)
    swarm_apply.broadcast(cfg, "hello all", include_nonmonitored=True, dry_run=False)

    assert calls == [
        (str(ROOT_DIR / "tmux-send"), "demo:0.0", "broadcast: hello all"),
        (str(ROOT_DIR / "tmux-send"), "demo:0.1", "broadcast: hello all"),
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
        swarm_apply.broadcast(cfg, "   ", include_nonmonitored=False, dry_run=False)


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
    monkeypatch.setattr(babysitctl, "stop", lambda cfg, dry_run: calls.append(("babysit", cfg.session_name, str(dry_run))))
    monkeypatch.setattr(swarm_cli, "_stop_tmux_session", lambda session_name, dry_run: calls.append(("tmux", session_name, str(dry_run))))
    rc = swarm_cli.main(["stop", "examples/swarm-grid.yaml"])
    assert rc == 0
    assert calls == [("babysit", "agent_grid", "False"), ("tmux", "agent_grid", "False")]


def test_cli_babysit_status_dispatches(monkeypatch):
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(swarm_cli, "load_config", lambda path: "CFG")
    monkeypatch.setattr(babysitctl, "status", lambda cfg: calls.append(("status", cfg)))
    rc = swarm_cli.main(["babysit", "status", "examples/swarm-grid.yaml"])
    assert rc == 0
    assert calls == [("status", "CFG")]
