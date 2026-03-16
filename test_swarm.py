from pathlib import Path
import sys

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parent / "swarm"))

import apply as swarm_apply
import babysit_apply
from common import ROOT_DIR, SWARM_APPLY, build_runtime_map, build_self_awareness_text, load_config


def write_config(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "swarm.yaml"
    path.write_text(body)
    return path


def test_load_config_resolves_prompt_file(tmp_path: Path):
    prompt = tmp_path / "hello.txt"
    prompt.write_text("nudge gently")
    cfg_path = write_config(tmp_path, f"""
session:
  name: demo
  window: grid
layout:
  type: grid
  rows: 1
  cols: 1
panes:
  - pane: "0.0"
    agent: claude
    command: "aiclaude"
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


def test_load_config_requires_full_grid(tmp_path: Path):
    cfg_path = write_config(tmp_path, """
session:
  name: demo
layout:
  type: grid
  rows: 2
  cols: 2
panes:
  - pane: "0.0"
    agent: claude
    command: "aiclaude"
    monitor: true
""")
    with pytest.raises(ValueError, match="layout expects 4 panes but config defines 1"):
        load_config(cfg_path)


def test_load_config_requires_contiguous_indices(tmp_path: Path):
    cfg_path = write_config(tmp_path, """
session:
  name: demo
layout:
  type: grid
  rows: 1
  cols: 2
panes:
  - pane: "0.0"
    agent: claude
    command: "aiclaude"
    monitor: true
  - pane: "0.2"
    agent: codex
    command: "aicodex"
    monitor: true
""")
    with pytest.raises(ValueError, match="pane indices must be contiguous 0..1"):
        load_config(cfg_path)


def test_load_config_allows_non_agent_pane_when_monitor_disabled(tmp_path: Path):
    cfg_path = write_config(tmp_path, """
session:
  name: demo
layout:
  type: grid
  rows: 1
  cols: 1
panes:
  - pane: "0.0"
    title: shell
    command: "htop"
    monitor: false
""")
    cfg = load_config(cfg_path)
    pane = cfg.panes[0]
    assert pane.agent is None
    assert pane.title == "shell"
    assert pane.monitor is False


def test_load_config_rejects_babysit_without_monitor(tmp_path: Path):
    cfg_path = write_config(tmp_path, """
session:
  name: demo
layout:
  type: grid
  rows: 1
  cols: 1
panes:
  - pane: "0.0"
    command: "htop"
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
session:
  name: demo
layout:
  type: grid
  rows: 1
  cols: 1
panes:
  - pane: "0.0"
    agent: claude
    command: "aiclaude"
    monitor: true
    babysit:
      enabled: true
      long_prompt_file: "{long_prompt.name}"
      short_prompt_file: "{short_prompt.name}"
""")
    pane = load_config(cfg_path).panes[0]
    assert pane.babysit.long_prompt == "full operating instructions"
    assert pane.babysit.short_prompt == "keep going"


def test_apply_invokes_grid_monitor_and_command(monkeypatch, tmp_path: Path):
    cfg = load_config(write_config(tmp_path, """
session:
  name: demo
layout:
  type: grid
  rows: 1
  cols: 2
panes:
  - pane: "0.0"
    agent: claude
    command: "aiclaude"
    monitor: true
  - pane: "0.1"
    agent: codex
    command: "aicodex"
    monitor: false
"""))
    calls: list[tuple[str, ...]] = []

    monkeypatch.setattr(swarm_apply, "ensure_grid", lambda cfg, dry_run: calls.append(("grid", cfg.session_name, str(dry_run))))
    monkeypatch.setattr(swarm_apply, "ensure_monitor", lambda cfg, pane, agent, dry_run: calls.append(("monitor", pane, agent, str(dry_run))))
    monkeypatch.setattr(swarm_apply, "ensure_title", lambda cfg, pane, title, dry_run: calls.append(("title", pane, title, str(dry_run))))
    monkeypatch.setattr(swarm_apply, "ensure_command", lambda cfg, pane, title, command, dry_run: calls.append(("command", pane, title, command, str(dry_run))))
    monkeypatch.setattr(swarm_apply, "write_runtime_map", lambda cfg: calls.append(("runtime_map", cfg.session_name)))
    monkeypatch.setattr(swarm_apply, "write_self_awareness_text", lambda cfg: calls.append(("self_awareness", cfg.session_name)))
    monkeypatch.setattr(swarm_apply.time, "sleep", lambda *_: None)

    swarm_apply.apply(cfg, dry_run=False)

    assert calls == [
        ("grid", "demo", "False"),
        ("monitor", "0.0", "claude", "False"),
        ("title", "0.0", "claude", "False"),
        ("command", "0.0", "claude", "aiclaude", "False"),
        ("title", "0.1", "codex", "False"),
        ("command", "0.1", "codex", "aicodex", "False"),
        ("runtime_map", "demo"),
        ("self_awareness", "demo"),
    ]


def test_ensure_grid_allows_new_session_to_expand(monkeypatch, tmp_path: Path):
    cfg = load_config(write_config(tmp_path, """
session:
  name: demo
layout:
  type: grid
  rows: 1
  cols: 2
panes:
  - pane: "0.0"
    agent: claude
    command: "aiclaude"
    monitor: true
  - pane: "0.1"
    agent: codex
    command: "aicodex"
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
        if args[:3] == ("tmux", "list-panes", "-t"):
            return Proc(0, "%0\n" if next(pane_counts) == 1 else "%0\n%1\n")
        if args[:3] == ("tmux", "split-window", "-t"):
            return Proc(0, "")
        if args[:3] == ("tmux", "select-layout", "-t"):
            return Proc(0, "")
        raise AssertionError(f"unexpected tmux call: {args}")

    monkeypatch.setattr(swarm_apply, "run", fake_run)
    swarm_apply.ensure_grid(cfg, dry_run=False)

    assert ("tmux", "split-window", "-t", "demo:grid.0", "bash") in tmux_calls
    assert ("tmux", "select-layout", "-t", "demo:grid", "tiled") in tmux_calls


def test_babysit_apply_restarts_worker_when_spec_changes(monkeypatch, tmp_path: Path):
    cfg = load_config(write_config(tmp_path, """
session:
  name: demo
layout:
  type: grid
  rows: 1
  cols: 1
panes:
  - pane: "0.0"
    agent: claude
    command: "aiclaude"
    monitor: true
    babysit:
      enabled: true
      interval_secs: 321
      prompt: "please continue"
"""))
    cfg.runtime_dir.mkdir(parents=True, exist_ok=True)
    babysit_apply.pid_path(cfg, "0.0").write_text("1234")
    babysit_apply.spec_path(cfg, "0.0").write_text("""{
  "session": "demo",
  "pane": "0.0",
  "target": "demo:0.0",
  "interval_secs": 600,
  "long_prompt": "old long",
  "short_prompt": "old short"
}
""")
    actions: list[tuple[str, ...]] = []

    monkeypatch.setattr(babysit_apply, "process_running", lambda pid: pid == 1234)
    monkeypatch.setattr(babysit_apply, "stop_worker", lambda cfg, pane, dry_run: actions.append(("stop", pane, str(dry_run))))
    monkeypatch.setattr(babysit_apply, "start_worker", lambda cfg, pane, interval, long_prompt, short_prompt, dry_run: actions.append(("start", pane, str(interval), long_prompt, short_prompt, str(dry_run))))

    babysit_apply.apply(cfg, dry_run=False)

    assert actions == [
        ("stop", "0.0", "False"),
        ("start", "0.0", "321", "please continue", "please continue", "False"),
    ]


def test_swarm_status_reports_window_command_and_monitor(monkeypatch, tmp_path: Path, capsys):
    cfg = load_config(write_config(tmp_path, """
session:
  name: demo
  window: grid
layout:
  type: grid
  rows: 1
  cols: 1
panes:
  - pane: "0.0"
    agent: claude
    command: "aiclaude"
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
            return Proc(0, "0: grid\n")
        if args[:3] == ("tmux", "list-panes", "-t"):
            return Proc(0, "%0\n")
        if args[:3] == ("tmux", "display-message", "-p"):
            return Proc(0, "claude\n")
        raise AssertionError(f"unexpected tmux call: {args}")

    monkeypatch.setattr(swarm_apply, "run", fake_run)
    monkeypatch.setattr(swarm_apply, "pane_count", lambda cfg: 1)
    monkeypatch.setattr(swarm_apply, "monitor_state", lambda cfg, pane: "idle")

    swarm_apply.print_status(cfg)
    out = capsys.readouterr().out

    assert "session=demo window=grid exists=yes panes=1/1" in out
    assert "demo:0.0 title=claude cmd=claude monitor=idle babysit=on" in out


def test_swarm_status_brief_reports_compact_states(monkeypatch, tmp_path: Path, capsys):
    cfg = load_config(write_config(tmp_path, """
session:
  name: demo
  window: grid
layout:
  type: grid
  rows: 1
  cols: 2
panes:
  - pane: "0.0"
    agent: claude
    command: "aiclaude"
    monitor: true
  - pane: "0.1"
    agent: codex
    command: "aicodex"
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
            return Proc(0, "0: grid\n")
        if args[:3] == ("tmux", "list-panes", "-t"):
            return Proc(0, "%0\n")
        raise AssertionError(f"unexpected tmux call: {args}")

    monkeypatch.setattr(swarm_apply, "run", fake_run)
    monkeypatch.setattr(swarm_apply, "pane_count", lambda cfg: 2)
    monkeypatch.setattr(swarm_apply, "monitor_state", lambda cfg, pane: "working")

    swarm_apply.print_status(cfg, brief=True)
    out = capsys.readouterr().out

    assert "demo:grid panes=2/2" in out
    assert "demo:0.0 claude working" in out
    assert "demo:0.1 codex off" in out


def test_status_lines_handles_missing_window(monkeypatch, tmp_path: Path):
    cfg = load_config(write_config(tmp_path, """
session:
  name: demo
layout:
  type: grid
  rows: 1
  cols: 1
panes:
  - pane: "0.0"
    agent: claude
    command: "aiclaude"
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
    assert swarm_apply.status_lines(cfg, brief=True) == ["demo:grid missing"]


def test_shell_prefixed_command_sets_ps1_prefix():
    assert swarm_apply.shell_prefixed_command("codex", "aicodex") == "export PS1='[codex] '\"$PS1\"; aicodex"


def test_runtime_map_contains_only_derived_runtime_paths(tmp_path: Path):
    cfg = load_config(write_config(tmp_path, """
session:
  name: demo
layout:
  type: grid
  rows: 1
  cols: 2
panes:
  - pane: "0.0"
    title: shell
    command: "htop"
    monitor: false
  - pane: "0.1"
    title: claude
    agent: claude
    command: "aiclaude"
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
    assert data["panes"]["0.1"]["babysit"]["has_long_prompt"] is True
    assert data["panes"]["0.1"]["babysit"]["has_short_prompt"] is True


def test_self_awareness_text_mentions_runtime_map_and_status(tmp_path: Path):
    cfg = load_config(write_config(tmp_path, """
session:
  name: demo
layout:
  type: grid
  rows: 1
  cols: 1
panes:
  - pane: "0.0"
    agent: claude
    command: "aiclaude"
    monitor: true
"""))
    text = build_self_awareness_text(cfg)
    assert "Runtime map: /tmp/nudge-swarm/demo/runtime.json" in text
    assert f"Status: python {SWARM_APPLY} {cfg.path} status --brief" in text
    assert f"Watch: python {SWARM_APPLY} {cfg.path} status --brief --watch" in text


def test_broadcast_targets_monitored_panes_by_default(monkeypatch, tmp_path: Path, capsys):
    cfg = load_config(write_config(tmp_path, """
session:
  name: demo
layout:
  type: grid
  rows: 1
  cols: 2
panes:
  - pane: "0.0"
    title: claude
    agent: claude
    command: "aiclaude"
    monitor: true
  - pane: "0.1"
    title: shell
    command: "htop"
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

    assert calls == [(str(ROOT_DIR / "tmux-send"), "demo:0.0", "AGENTS updated")]
    assert "broadcast to demo:0.0 (claude)" in out


def test_broadcast_can_include_nonmonitored_panes(monkeypatch, tmp_path: Path):
    cfg = load_config(write_config(tmp_path, """
session:
  name: demo
layout:
  type: grid
  rows: 1
  cols: 2
panes:
  - pane: "0.0"
    title: claude
    agent: claude
    command: "aiclaude"
    monitor: true
  - pane: "0.1"
    title: shell
    command: "htop"
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
        (str(ROOT_DIR / "tmux-send"), "demo:0.0", "hello all"),
        (str(ROOT_DIR / "tmux-send"), "demo:0.1", "hello all"),
    ]


def test_broadcast_rejects_empty_message(tmp_path: Path):
    cfg = load_config(write_config(tmp_path, """
session:
  name: demo
layout:
  type: grid
  rows: 1
  cols: 1
panes:
  - pane: "0.0"
    title: claude
    agent: claude
    command: "aiclaude"
    monitor: true
"""))
    with pytest.raises(ValueError, match="must not be empty"):
        swarm_apply.broadcast(cfg, "   ", include_nonmonitored=False, dry_run=False)
