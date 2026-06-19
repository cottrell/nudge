#!/usr/bin/env python3
"""Poll a monitored tmux pane and nudge when idle.

Usage: babysit.py <session-or-target> [interval_secs] [long_nudge] [short_nudge]

  session-or-target  tmux session or pane target (e.g. claude_myproject_alice or
                     claude_myproject_alice:0.0)
  interval_secs      base poll interval, default 60
  long_nudge         sent once on startup, default 'Please continue.'
  short_nudge        sent on later idle nudges, defaults to long_nudge

Env vars:
  BABYSIT_MAX_NONIDLE_SECS  default 1800; force nudge after this many continuous
                            unknown/working/error seconds.  Set to 0 to disable.
  BABYSIT_STATE_FILE        path for JSON state output (read by swarm status)
  BABYSIT_AGENT             agent type: claude, codex, gemini, qwen, ...
  BABYSIT_STATS_EVERY       seconds between usage stat probes, default 300
"""
from __future__ import annotations

import json
import os
import socket as _socket
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

_ROOT_DIR = Path(__file__).resolve().parent
_TMUX_SEND = _ROOT_DIR / "tmux-send"

try:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent / "swarm"))
    from common import get_cached_provider_usage
except Exception:
    get_cached_provider_usage = None

# ── EMA scheduling (defaults; overridden by env vars set from YAML babysit config) ──
_ALPHA = float(os.environ.get("BABYSIT_EMA_ALPHA", 0.30))
_SAFETY = float(os.environ.get("BABYSIT_EMA_SAFETY", 0.92))
_K_VAR = float(os.environ.get("BABYSIT_EMA_K_VAR", 0.0))
_EMA_WARMUP = int(os.environ.get("BABYSIT_EMA_WARMUP", 3))
_MIN_WAIT = int(os.environ.get("BABYSIT_EMA_MIN_WAIT", 30))
_MAX_WAIT = int(os.environ.get("BABYSIT_EMA_MAX_WAIT", 1200))

# ── tmux / socket helpers ─────────────────────────────────────────────────────

def _normalise_target(t: str) -> str:
    if ":" not in t:
        return t + ":0.0"
    session, wp = t.split(":", 1)
    if "." not in wp:
        wp += ".0"
    return f"{session}:{wp}"


def _query_socket(sock_path: str) -> dict:
    try:
        with _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM) as s:
            s.settimeout(2.0)
            s.connect(sock_path)
            s.sendall(b"status")
            chunks = []
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    break
                chunks.append(chunk)
        return json.loads(b"".join(chunks))
    except Exception:
        return {}


def _send_message(target: str, msg: str) -> None:
    # Babysit must send literal commands (e.g. /stats, /clear) unchanged.
    subprocess.run([str(_TMUX_SEND), "--no-prefix", target, msg], check=False)


def _deliver(session: str, target: str, pane: str, msg: str, etype: str = "babysit") -> None:
    """Deliver a message. By default via the comms log (pushed to log, then drained by consumer on idle).
    Falls back to direct if via_log=false or log path fails.
    """
    if via_log:
        try:
            import sys
            from pathlib import Path
            swarm_dir = str(Path(__file__).parent / "swarm")
            if swarm_dir not in sys.path:
                sys.path.insert(0, swarm_dir)
            from common import log_send
            log_send(session, pane, msg, sender="babysitter", etype=etype)
            _drain_comms(session, target, pane)
            return
        except Exception:
            pass  # fall back
    _send_message(target, msg)


def _drain_comms(session: str, target: str, pane: str) -> None:
    """Consume from the comms log (direct to pane + broadcasts) and deliver when the pane is ready.
    Uses per-pane cursors so independent from babysit nudging.
    """
    try:
        import sys
        from pathlib import Path
        swarm_dir = str(Path(__file__).parent / "swarm")
        if swarm_dir not in sys.path:
            sys.path.insert(0, swarm_dir)
        from common import get_pending_events, advance_cursor, get_pending_broadcasts, advance_broadcast_cursor
    except Exception as e:
        print(f"  comms import failed: {e}")
        return

    # direct messages for this exact pane
    try:
        pending = get_pending_events(session, pane)
        last_id = 0
        for eid, ts, snd, typ, payload, meta in pending:
            print(f"  comms: deliver direct eid={eid} to {target}")
            _send_message(target, payload)
            last_id = eid
        if pending and last_id > 0:
            advance_cursor(session, pane, last_id)
    except Exception as e:
        print(f"  comms direct error: {e}")

    # broadcasts written to __broadcast__ (per-pane cursor to avoid cross-pane interference)
    try:
        bcasts = get_pending_broadcasts(session, pane)
        last_id = 0
        for eid, ts, snd, typ, payload, meta in bcasts:
            print(f"  comms: deliver broadcast eid={eid} to {target}")
            _send_message(target, payload)
            last_id = eid
        if bcasts and last_id > 0:
            advance_broadcast_cursor(session, pane, last_id)
    except Exception as e:
        print(f"  comms broadcast error: {e}")


def _log_nudge(session: str, target: str, reason: str, msg: str) -> None:
    log_file = os.environ.get("BABYSIT_LOG_FILE") or "nudge.log"
    long_f = os.environ.get("BABYSIT_LONG_PROMPT_FILE", "")
    short_f = os.environ.get("BABYSIT_SHORT_PROMPT_FILE", "")
    
    if reason in ("startup", "restore"):
        f_info = f"({long_f})" if long_f else ""
    elif reason in ("idle", "forced_unknown", "forced_working", "forced_error"):
        f_info = f"({short_f})" if short_f else ""
    else:
        f_info = ""

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    summary = msg.replace("\n", " ").strip()
    if len(summary) > 60:
        summary = summary[:57] + "..."
    line = f"{ts} | {session:20} | {target:16} | {reason:15} | {summary:60} {f_info}\n"
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


def _write_state(
    path: str | None,
    target: str,
    interval: int,
    last_state: str,
    last_action: str,
    last_nudge_at: int,
    nonidle_since: int,
    next_poll_at: int,
    next_force_at: int,
    ema: dict | None = None,
) -> None:
    if not path:
        return
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    d: dict = {
        "target": target,
        "interval_secs": interval,
        "last_monitor_state": last_state,
        "last_action": last_action,
        "last_nudge_at": last_nudge_at,
        "nonidle_since": nonidle_since if nonidle_since > 0 else None,
        "next_poll_at": next_poll_at,
        "next_force_nudge_at": next_force_at,
    }
    if ema:
        d["ema"] = ema
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(d) + "\n")
    tmp.replace(p)


def _quota_bg_refresh(agent: str, interval: float) -> None:
    """Daemon thread: pre-warm quota cache so main-loop probes never stall."""
    while True:
        time.sleep(interval)
        if get_cached_provider_usage:
            try:
                get_cached_provider_usage(agent, ttl=0, force=True)
            except Exception:
                pass


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    target = _normalise_target(sys.argv[1])
    session = target.split(":")[0]
    window_pane = target.split(":")[1]
    interval = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    long_nudge = sys.argv[3] if len(sys.argv) > 3 else "Please continue."
    short_nudge = sys.argv[4] if len(sys.argv) > 4 else long_nudge

    max_nonidle = int(os.environ.get("BABYSIT_MAX_NONIDLE_SECS", 1800))
    state_file = os.environ.get("BABYSIT_STATE_FILE") or None
    agent = os.environ.get("BABYSIT_AGENT", "")
    clear_every = int(os.environ.get("BABYSIT_CLEAR_EVERY", 0))
    stats_every = int(os.environ.get("BABYSIT_STATS_EVERY", 300))
    via_log = os.environ.get("BABYSIT_VIA_LOG", "1") == "1"

    if agent in ("claude", "codex", "agy") and get_cached_provider_usage:
        refresh_interval = max(60.0, stats_every - 60.0)
        t = threading.Thread(target=_quota_bg_refresh, args=(agent, refresh_interval), daemon=True)
        t.start()

    sock = f"/tmp/{session}_{window_pane}.sock"

    r = subprocess.run(["tmux", "list-panes", "-t", target], capture_output=True)
    if r.returncode != 0:
        print(f"Target pane not found: {target}", file=sys.stderr)
        return 1

    print(f"Babysitting {session} via {target} (interval={interval}s)")
    if max_nonidle > 0:
        print(f"Max non-idle override after {max_nonidle}s")

    # EMA state — mu/sigma in units of "% quota consumed per nudge cycle"
    mu: float = 5.0
    sigma: float = 2.0
    nudge_count: int = 0
    pct_at_nudge: float | None = None   # pct recorded just before last nudge
    nudge_sent_ts: float = 0.0

    # last known usage (updated by probe)
    current_pct: float | None = None
    current_reset_ts: float | None = None

    nonidle_since: int = 0
    stats_last_probe: float = 0.0
    sleep_dur: float = float(interval)

    # startup nudge
    if long_nudge:
        now = int(time.time())
        print(f"{time.strftime('%H:%M:%S')} {session} startup babysit prompt")
        _log_nudge(session, target, "startup", long_nudge)
        _deliver(session, target, window_pane, long_nudge, etype="babysit_startup")
        pct_at_nudge = current_pct  # None until first probe
        nudge_sent_ts = time.time()
        nudge_count += 1
        _write_state(state_file, target, interval, "", "startup_nudge", now, 0, now + interval, 0)

    # initial comms drain (deliver anything that arrived before we started)
    _drain_comms(session, target, window_pane)

    while True:
        time.sleep(sleep_dur)
        now_f = time.time()
        now = int(now_f)
        ts = time.strftime("%H:%M:%S")

        data = _query_socket(sock)
        state = data.get("state", "")

        if state in ("idle", "rate_limited") or not state:
            nonidle_since = 0
        elif state in ("unknown", "working", "error"):
            if nonidle_since == 0:
                nonidle_since = now

        force_deadline = (nonidle_since + max_nonidle) if (max_nonidle > 0 and nonidle_since > 0) else 0
        next_force_at = force_deadline if state in ("unknown", "working", "error") else 0

        if state == "idle":
            # Comms consumption (independent of babysit nudges)
            _drain_comms(session, target, window_pane)

            # babysit logic only if we have prompts (i.e. babysit was enabled for this pane)
            if long_nudge or short_nudge:
                # probe quota on a throttled schedule using cli-based quota (non-intrusive)
                if agent in ("claude", "codex", "agy") and (now_f - stats_last_probe) >= stats_every:
                    print(f"{ts} {session} probing quota ({agent})")
                    new_pct = new_reset_ts = None
                    if get_cached_provider_usage:
                        try:
                            res = get_cached_provider_usage(agent, ttl=30, force=False)
                            limits = res.get("limits") or (res.get("parsed") or {}).get("limits") or []
                            if limits:
                                pcts = [lim.get("pct") for lim in limits if lim.get("pct") is not None]
                                resets = [lim.get("reset_ts", 0) for lim in limits if lim.get("reset_ts", 0)]
                                new_pct = min(pcts) if pcts else None
                                new_reset_ts = min(resets) if resets else None
                        except Exception as e:
                            print(f"  quota error: {e}")
                    if new_pct is not None:
                        current_pct, current_reset_ts = new_pct, new_reset_ts
                    stats_last_probe = now_f
                    now_f = time.time()
                    now = int(now_f)
                    ts = time.strftime("%H:%M:%S")

                # measure C (% consumed this cycle) and D (AI processing time)
                D = now_f - nudge_sent_ts if nudge_sent_ts > 0 else 0.0
                if pct_at_nudge is not None and current_pct is not None and nudge_sent_ts > 0:
                    C = pct_at_nudge - current_pct
                    if C > 0:
                        mu = _ALPHA * C + (1 - _ALPHA) * mu
                        sigma = _ALPHA * abs(C - mu) + (1 - _ALPHA) * sigma

                print(f"{ts} {session} is idle — nudging")
                if clear_every > 0 and nudge_count > 0 and (nudge_count % clear_every) == 0:
                    print(f"{ts} {session} clearing context (nudge_count={nudge_count})")
                    _log_nudge(session, target, "clear", "/clear")
                    _deliver(session, target, window_pane, "/clear", etype="clear")
                    time.sleep(1.0)
                    _log_nudge(session, target, "restore", long_nudge)
                    _deliver(session, target, window_pane, long_nudge, etype="babysit_restore")
                else:
                    _log_nudge(session, target, "idle", short_nudge)
                    _deliver(session, target, window_pane, short_nudge, etype="babysit")
                pct_at_nudge = current_pct
                nudge_sent_ts = now_f
                nudge_count += 1

                ema_ready = (
                    nudge_count >= _EMA_WARMUP
                    and current_pct is not None
                    and current_reset_ts is not None
                    and current_reset_ts > now_f
                )
                if ema_ready:
                    T = max(current_reset_ts - now_f, 3600.0)  # type: ignore[operator]
                    S = max(current_pct, 1.0)                   # type: ignore[arg-type]
                    tau = (T * (mu + _K_VAR * sigma)) / (S * _SAFETY)
                    sleep_dur = max(_MIN_WAIT, min(_MAX_WAIT, tau - D))
                    print(f"{ts} {session} EMA τ={tau:.0f}s D={D:.0f}s → sleep {sleep_dur:.0f}s"
                          f" (μ={mu:.2f}% σ={sigma:.2f}%)")
                else:
                    sleep_dur = float(interval)

                ema_state = {"mu": round(mu, 3), "sigma": round(sigma, 3), "nudge_count": nudge_count}
                _write_state(state_file, target, interval, state, "idle_nudge",
                             now, 0, now + int(sleep_dur), 0, ema_state)

        elif state == "unknown":
            if force_deadline > 0 and now >= force_deadline:
                print(f"{ts} {session} is unknown for {now - nonidle_since}s — nudging anyway")
                _log_nudge(session, target, "forced_unknown", short_nudge)
                _deliver(session, target, window_pane, short_nudge, etype="babysit_forced")
                nonidle_since = now
                nudge_count += 1
                sleep_dur = float(interval)
                _write_state(state_file, target, interval, state, "forced_nudge",
                             now, nonidle_since, now + interval, 0)
            else:
                print(f"{ts} {session} is unknown — waiting")
                sleep_dur = float(interval)
                _write_state(state_file, target, interval, state, "wait_unknown",
                             0, nonidle_since, now + interval, next_force_at)

        elif state == "rate_limited":
            print(f"{ts} {session} is rate_limited — waiting")
            sleep_dur = float(interval)
            _write_state(state_file, target, interval, state, "wait_rate_limited",
                         0, 0, now + interval, 0)

        elif state in ("working", "error"):
            if force_deadline > 0 and now >= force_deadline:
                print(f"{ts} {session} is {state} for {now - nonidle_since}s — nudging anyway")
                _log_nudge(session, target, f"forced_{state}", short_nudge)
                _deliver(session, target, window_pane, short_nudge, etype="babysit_forced")
                nonidle_since = now
                nudge_count += 1
                sleep_dur = float(interval)
                _write_state(state_file, target, interval, state, "forced_nudge",
                             now, nonidle_since, now + interval, 0)
            else:
                print(f"{ts} {session} is {state}")
                sleep_dur = float(interval)
                _write_state(state_file, target, interval, state, f"wait_{state}",
                             0, nonidle_since, now + interval, next_force_at)

        else:
            print(f"{ts} {session} is {state!r}")
            sleep_dur = float(interval)
            _write_state(state_file, target, interval, state, f"observe_{state}",
                         0, 0, now + interval, 0)


if __name__ == "__main__":
    raise SystemExit(main())
