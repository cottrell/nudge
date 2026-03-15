from pathlib import Path
import sys

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parent / "swarm"))

import apply as swarm_apply
import babysit_apply
from common import load_config


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
    assert pane.babysit.enabled is True
    assert pane.babysit.interval_secs == 123
    assert pane.babysit.prompt == "nudge gently"
    assert pane.babysit.prompt_file == prompt.resolve()


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
    monkeypatch.setattr(swarm_apply, "ensure_command", lambda cfg, pane, command, dry_run: calls.append(("command", pane, command, str(dry_run))))
    monkeypatch.setattr(swarm_apply.time, "sleep", lambda *_: None)

    swarm_apply.apply(cfg, dry_run=False)

    assert calls == [
        ("grid", "demo", "False"),
        ("monitor", "0.0", "claude", "False"),
        ("command", "0.0", "aiclaude", "False"),
        ("command", "0.1", "aicodex", "False"),
    ]


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
  "prompt": "old"
}
""")
    actions: list[tuple[str, ...]] = []

    monkeypatch.setattr(babysit_apply, "process_running", lambda pid: pid == 1234)
    monkeypatch.setattr(babysit_apply, "stop_worker", lambda cfg, pane, dry_run: actions.append(("stop", pane, str(dry_run))))
    monkeypatch.setattr(babysit_apply, "start_worker", lambda cfg, pane, interval, prompt, dry_run: actions.append(("start", pane, str(interval), prompt, str(dry_run))))

    babysit_apply.apply(cfg, dry_run=False)

    assert actions == [
        ("stop", "0.0", "False"),
        ("start", "0.0", "321", "please continue", "False"),
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

    swarm_apply.status(cfg)
    out = capsys.readouterr().out

    assert "session=demo window=grid exists=yes panes=1/1" in out
    assert "demo:0.0 cmd=claude monitor=idle babysit=on" in out
