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
import re
import socket as _socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


# ── EMA scheduling ────────────────────────────────────────────────────────────
_ALPHA = 0.30        # EMA smoothing
_SAFETY = 0.92       # leave an 8 % quota cushion at reset
_K_VAR = 0.0         # variance weight; raise to 0.5–1.0 for conservative mode
_EMA_WARMUP = 3      # nudges before EMA replaces fixed interval
_MIN_WAIT = 30       # hard floor (seconds)
_MAX_WAIT = 20 * 60  # hard ceiling (seconds)

_STATS_CMD: dict[str, str] = {
    "claude": "/usage",
    "codex": "/status",
    "gemini": "/stats",
    "qwen": "/stats",
}

# ── usage parsing (mirrors topology.py) ──────────────────────────────────────
_LINE_PATTERNS = [
    (re.compile(r'(\w+)\s+limit:.*?(\d+)%\s+left', re.IGNORECASE), 'labeled_left'),
    (re.compile(r'(\d+)%\s+left', re.IGNORECASE), 'pct_left'),
    (re.compile(r'(\d+)%\s+used', re.IGNORECASE), 'pct_used'),
    (re.compile(r'(\d+\.?\d*)\s*/\s*(\d+\.?\d*)\s*hours', re.IGNORECASE), 'hours_used'),
    (re.compile(r'\b(\d+)%\s+\d{1,2}:\d{2}\s+(?:AM|PM)', re.IGNORECASE), 'pct_used'),
]
_RESET_RE = re.compile(r'resets\s+(.+)', re.IGNORECASE)


def _parse_reset_ts(s: str) -> int | None:
    if not s:
        return None
    now = datetime.now()
    s = re.sub(r'\s*\([^)]*\)', '', s).strip()

    m = re.match(r'(\d{1,2}):(\d{2})\s+on\s+(\d{1,2})\s+(\w+)', s)
    if m:
        hour, minute, day, mon = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)
        for yr in (now.year, now.year + 1):
            try:
                dt = datetime.strptime(f"{day} {mon} {yr} {hour}:{minute}", "%d %b %Y %H:%M")
                if dt.timestamp() > now.timestamp():
                    return int(dt.timestamp())
            except ValueError:
                pass

    m = re.match(r'(\w+)\s+(\d{1,2}),?\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?', s, re.IGNORECASE)
    if m:
        mon, day = m.group(1), int(m.group(2))
        hour, minute = int(m.group(3)), int(m.group(4) or 0)
        ampm = (m.group(5) or '').lower()
        if ampm == 'pm' and hour != 12:
            hour += 12
        elif ampm == 'am' and hour == 12:
            hour = 0
        for yr in (now.year, now.year + 1):
            try:
                dt = datetime.strptime(f"{day} {mon} {yr} {hour}:{minute}", "%d %b %Y %H:%M")
                if dt.timestamp() > now.timestamp():
                    return int(dt.timestamp())
            except ValueError:
                pass
    return None


def _parse_usage_from_text(text: str) -> list[dict]:
    limits: list[dict] = []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        entry: dict | None = None
        for pat, kind in _LINE_PATTERNS:
            m = pat.search(line)
            if not m:
                continue
            try:
                if kind == 'labeled_left':
                    entry = {"label": m.group(1).lower(), "pct": int(m.group(2))}
                elif kind == 'pct_left':
                    entry = {"label": "", "pct": int(m.group(1))}
                elif kind == 'pct_used':
                    entry = {"label": "", "pct": max(0, 100 - int(m.group(1)))}
                elif kind == 'hours_used':
                    used, total = float(m.group(1)), float(m.group(2))
                    if total > 0:
                        entry = {"label": "", "pct": round((1.0 - used / total) * 100)}
            except (ValueError, ZeroDivisionError):
                pass
            if entry:
                search_lines = [line] + ([lines[i + 1]] if i + 1 < len(lines) else [])
                reset = ""
                for sl in search_lines:
                    rm = _RESET_RE.search(sl)
                    if rm:
                        reset = rm.group(1).strip().rstrip('│╯╰ ')
                        while reset.endswith(')') and reset.count('(') < reset.count(')'):
                            reset = reset[:-1].rstrip()
                        break
                entry["reset"] = reset
                entry["reset_ts"] = _parse_reset_ts(reset) or 0
                limits.append(entry)
                break
    labeled = [l for l in limits if l["label"]]
    return labeled if labeled else limits


def _probe_usage(target: str, cmd: str) -> tuple[float | None, float | None]:
    """Send stats command, wait, capture pane, parse. Returns (min_pct, soonest_reset_ts)."""
    subprocess.run(["tmux", "send-keys", "-t", target, "-l", "--", cmd], check=False)
    time.sleep(0.1)
    subprocess.run(["tmux", "send-keys", "-t", target, "C-m"], check=False)
    time.sleep(2)
    r = subprocess.run(["tmux", "capture-pane", "-t", target, "-p"], capture_output=True, text=True)
    limits = _parse_usage_from_text(r.stdout)
    if not limits:
        return None, None
    pcts = [lim["pct"] for lim in limits if lim.get("pct") is not None]
    resets = [lim["reset_ts"] for lim in limits if lim.get("reset_ts")]
    return (min(pcts) if pcts else None), (min(resets) if resets else None)


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
    if os.environ.get("TMUX"):
        r = subprocess.run(
            ["tmux", "display-message", "-p", "#S:#{window_index}.#{pane_index}"],
            capture_output=True, text=True,
        )
        sender = r.stdout.strip()
        if sender:
            msg = f"{sender}: {msg}"
    subprocess.run(["tmux", "send-keys", "-t", target, "-l", "--", msg], check=False)
    time.sleep(0.1)
    subprocess.run(["tmux", "send-keys", "-t", target, "C-m"], check=False)


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
    stats_every = int(os.environ.get("BABYSIT_STATS_EVERY", 300))

    stats_cmd = _STATS_CMD.get(agent, "")
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
        _send_message(target, long_nudge)
        pct_at_nudge = current_pct  # None until first probe
        nudge_sent_ts = time.time()
        nudge_count += 1
        _write_state(state_file, target, interval, "", "startup_nudge", now, 0, now + interval, 0)

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
            # probe usage on a throttled schedule
            if stats_cmd and (now_f - stats_last_probe) >= stats_every:
                print(f"{ts} {session} probing usage ({stats_cmd})")
                new_pct, new_reset_ts = _probe_usage(target, stats_cmd)
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
                _send_message(target, "/clear")
                time.sleep(1.0)
                _send_message(target, long_nudge)
            else:
                _send_message(target, short_nudge)
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
                _send_message(target, short_nudge)
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
                _send_message(target, short_nudge)
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
