import json
import time
from pathlib import Path
import pytest

from swarm.presence import (
    TmuxClientInfo,
    evaluate_presence,
    format_idle,
    load_override,
    save_override,
)


def test_format_idle():
    assert format_idle(45) == "45s"
    assert format_idle(60) == "1m"
    assert format_idle(90) == "1m 30s"
    assert format_idle(3600) == "1h"
    assert format_idle(3665) == "1h 1m"


def test_load_and_save_override(tmp_path: Path):
    override_file = tmp_path / "presence.json"

    # Default missing
    mode, until = load_override(override_file)
    assert mode is None
    assert until is None

    # Save pinned mode
    save_override(override_file, "in")
    mode, until = load_override(override_file)
    assert mode == "in"
    assert until is None

    # Save with until in future
    now = time.time()
    save_override(override_file, "out", until=now + 100)
    mode, until = load_override(override_file)
    assert mode == "out"
    assert until == pytest.approx(now + 100, rel=1e-2)

    # Save with until in past (expired)
    save_override(override_file, "out", until=now - 10)
    mode, until = load_override(override_file)
    assert mode is None
    assert until is None
    assert not override_file.exists()

    # Setting auto keeps explicit local auto mode
    save_override(override_file, "auto")
    assert override_file.exists()
    mode, _ = load_override(override_file)
    assert mode == "auto"

    # Reset to global/clear removes file
    save_override(override_file, "global")
    assert not override_file.exists()


def test_evaluate_presence_auto_no_clients(tmp_path: Path):
    g_file = tmp_path / "global.json"
    status = evaluate_presence(
        session_name="swarm1",
        clients=[],
        global_path=g_file,
    )
    assert status.effective == "out"
    assert status.global_eval.state == "out"
    assert status.global_eval.mode == "auto"
    assert "no tmux clients attached" in status.global_eval.source
    assert status.local.mode == "global"


def test_evaluate_presence_auto_with_clients(tmp_path: Path):
    g_file = tmp_path / "global.json"
    now = 1000.0
    clients = [
        TmuxClientInfo(session="swarm1", last_activity=900),  # idle 100s
        TmuxClientInfo(session="other", last_activity=950),   # idle 50s
    ]

    # Idle within 900s timeout -> IN
    status = evaluate_presence(
        session_name="swarm1",
        idle_timeout=900,
        clients=clients,
        now=now,
        global_path=g_file,
    )
    assert status.effective == "in"
    assert status.global_eval.state == "in"
    assert status.global_eval.idle_seconds == 50
    assert status.local.mode == "global"

    # Idle beyond timeout -> OUT
    status_idle = evaluate_presence(
        session_name="swarm1",
        idle_timeout=30,  # 30s timeout, but idle is 50s
        clients=clients,
        now=now,
        global_path=g_file,
    )
    assert status_idle.effective == "out"
    assert status_idle.global_eval.state == "out"
    assert status_idle.global_eval.idle_seconds == 50


def test_evaluate_presence_global_override(tmp_path: Path):
    g_file = tmp_path / "global.json"
    l_file = tmp_path / "local.json"
    save_override(g_file, "out")

    # Even with an active client right now, global pinned to out overrides
    clients = [TmuxClientInfo(session="swarm1", last_activity=1000)]
    status = evaluate_presence(
        session_name="swarm1",
        clients=clients,
        now=1000.0,
        global_path=g_file,
        local_path=l_file,
    )
    assert status.effective == "out"
    assert status.global_eval.state == "out"
    assert status.global_eval.source.startswith("pinned: out")


def test_evaluate_presence_local_override_precedence(tmp_path: Path):
    g_file = tmp_path / "global.json"
    l_file = tmp_path / "local.json"

    # Global is pinned OUT, but local is pinned IN
    save_override(g_file, "out")
    save_override(l_file, "in")

    status = evaluate_presence(
        session_name="swarm1",
        clients=[],
        global_path=g_file,
        local_path=l_file,
    )
    assert status.effective == "in"
    assert status.local.state == "in"
    assert status.global_eval.state == "out"


def test_evaluate_presence_local_auto(tmp_path: Path):
    g_file = tmp_path / "global.json"
    l_file = tmp_path / "local.json"

    # Local is set to auto (scoped to session 'swarm1')
    save_override(l_file, "auto")

    now = 1000.0
    # Client for 'other' was active 5s ago, but client for 'swarm1' was active 2000s ago
    clients = [
        TmuxClientInfo(session="other", last_activity=995),
        TmuxClientInfo(session="swarm1", last_activity=100),
    ]

    status = evaluate_presence(
        session_name="swarm1",
        idle_timeout=900,
        clients=clients,
        now=now,
        global_path=g_file,
        local_path=l_file,
    )
    # Global would be IN (due to 'other' client at 995)
    assert status.global_eval.state == "in"
    # But local auto for swarm1 evaluates swarm1 clients (idle 900s) -> OUT
    assert status.effective == "out"
    assert status.local.state == "out"
    assert status.local.client_count == 1


def test_get_tmux_clients_mocked(monkeypatch):
    from unittest.mock import MagicMock
    import subprocess
    from swarm.presence import get_tmux_clients

    mock_run = MagicMock(return_value=subprocess.CompletedProcess(
        args=["tmux"],
        returncode=0,
        stdout="nudge 1791540000\nother 1791540100\n",
        stderr="",
    ))
    monkeypatch.setattr(subprocess, "run", mock_run)

    clients = get_tmux_clients()
    assert len(clients) == 2
    assert clients[0].session == "nudge"
    assert clients[0].last_activity == 1791540000
    assert clients[1].session == "other"
    assert clients[1].last_activity == 1791540100


def test_cli_presence_validation(capsys):
    from swarm import cli

    # Extra arguments error
    rc = cli.main(["presence", "local", "in", "extra"])
    assert rc == 1
    assert "too many arguments" in capsys.readouterr().err

    # Disallow --for without setting mode
    rc = cli.main(["presence", "--for", "1h"])
    assert rc == 1
    assert "--for cannot be specified" in capsys.readouterr().err

    # Invalid scope
    rc = cli.main(["presence", "foo", "in"])
    assert rc == 1
    assert "unknown presence scope" in capsys.readouterr().err


def test_cli_presence_roundtrip(tmp_path: Path, monkeypatch, capsys):
    from swarm import cli
    from swarm import presence
    from unittest.mock import MagicMock

    # Redirect global and local presence paths completely into tmp_path
    g_path = tmp_path / "presence_global.json"
    monkeypatch.setattr(presence, "GLOBAL_PRESENCE_PATH", g_path)
    monkeypatch.setattr(presence, "local_presence_path", lambda s: tmp_path / f"local_{s}.json")

    # Mock load_config to return an isolated session name
    isolated_cfg = MagicMock()
    isolated_cfg.session_name = "test_isolated_session"
    monkeypatch.setattr(cli, "load_config", lambda *args, **kwargs: isolated_cfg)

    # 1. Query initial state with JSON output
    rc = cli.main(["presence", "--json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["global"]["mode"] == "auto"

    # 2. Set global out
    rc = cli.main(["presence", "global", "out"])
    assert rc == 0
    assert "Set global presence to 'out'" in capsys.readouterr().out
    assert g_path.exists()

    # Query again and check JSON
    rc = cli.main(["presence", "--json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["effective"] == "out"
    assert out["global"]["mode"] == "out"

    # 3. Reset global to auto
    rc = cli.main(["presence", "global", "auto"])
    assert rc == 0
    assert "Set global presence to 'auto'" in capsys.readouterr().out
    assert not g_path.exists()

    # Query again
    rc = cli.main(["presence", "--json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["global"]["mode"] == "auto"

