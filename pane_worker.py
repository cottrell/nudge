#!/usr/bin/env python3
"""Shared per-pane state machine used by the compatibility worker and supervisor."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

_ROOT_DIR = Path(__file__).resolve().parent
_TMUX_SEND = _ROOT_DIR / "tmux-send"
try:
    sys.path.insert(0, str(_ROOT_DIR / "swarm"))
    from common import get_cached_provider_usage, query_monitor_socket
except Exception:
    get_cached_provider_usage = None
    from common import query_monitor_socket

_quota_refresh: set[str] = set()
_quota_lock = threading.Lock()


def _ensure_quota_refresh(agent: str, interval: int) -> None:
    if agent not in ("claude", "codex", "agy") or not get_cached_provider_usage:
        return
    with _quota_lock:
        if agent in _quota_refresh:
            return
        _quota_refresh.add(agent)
    def refresh() -> None:
        while True:
            time.sleep(max(60, interval - 60))
            try: get_cached_provider_usage(agent, ttl=0, force=True)
            except Exception: pass
    threading.Thread(target=refresh, daemon=True, name=f"quota-refresh-{agent}").start()


def _normalise_target(target: str) -> str:
    if ":" not in target:
        return target + ":0.0"
    session, pane = target.split(":", 1)
    return f"{session}:{pane if '.' in pane else pane + '.0'}"


def load_spec(path: Path, cached: tuple[int, dict | None] | None) -> tuple[dict | None, tuple[int, dict | None] | None]:
    try:
        mtime = path.stat().st_mtime_ns
    except OSError:
        return None, None
    if cached and cached[0] == mtime:
        return cached[1], cached
    try:
        spec = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        spec = None
    return spec, (mtime, spec)


def _query_socket(path: str) -> dict:
    try:
        session, pane = path.removeprefix("/tmp/").removesuffix(".sock").split("_", 1)
    except ValueError:
        return {}
    return query_monitor_socket(session, pane)


def _send_message(target: str, msg: str, simulate: bool = False) -> None:
    if simulate: return
    subprocess.run([str(_TMUX_SEND), "--no-prefix", target, msg], check=False)


def _drain_comms(session: str, target: str, pane: str, simulate: bool = False, spec: dict | None = None) -> None:
    try:
        from common import (advance_broadcast_cursor, advance_cursor, get_pending_broadcasts,
                            get_pending_events, log_ack)
        if spec is None:
            stem = f"babysit-{pane.replace('.', '-')}"
            spec_path = Path("/tmp/nudge-swarm") / session / f"{stem}.json"
            if spec_path.exists():
                try:
                    spec = json.loads(spec_path.read_text())
                except Exception:
                    pass

        pending = get_pending_events(session, pane)
        for eid, *_rest, payload, _meta in pending:
            _send_message(target, payload, simulate); log_ack(session, pane, eid, pane, target)
        if pending: advance_cursor(session, pane, pending[-1][0])
        bcasts = get_pending_broadcasts(session, pane)
        for eid, *_rest, payload, meta in bcasts:
            if spec is not None:
                agent = spec.get("agent")
                if not agent:
                    continue
                monitor = spec.get("monitor")
                if monitor is None:
                    monitor = True
                include_nonmonitored = False
                if meta:
                    try:
                        meta_dict = json.loads(meta) if isinstance(meta, str) else meta
                        if isinstance(meta_dict, dict):
                            include_nonmonitored = meta_dict.get("include_nonmonitored", False)
                    except Exception:
                        pass
                if not include_nonmonitored and not monitor:
                    continue
            _send_message(target, payload, simulate); log_ack(session, pane, eid, "__broadcast__", target)
        if bcasts: advance_broadcast_cursor(session, pane, bcasts[-1][0])
    except Exception as exc:
        print(f"comms error {session}:{pane}: {exc}", flush=True)


def _deliver(session: str, target: str, pane: str, msg: str, etype: str = "babysit",
             via_log: bool | None = None, simulate: bool = False) -> None:
    if simulate: return
    if via_log is None: via_log = os.environ.get("BABYSIT_VIA_LOG", "1") == "1"
    if via_log:
        try:
            from common import log_send
            log_send(session, pane, msg, sender="babysitter", etype=etype)
            _drain_comms(session, target, pane, simulate)
            return
        except Exception: pass
    _send_message(target, msg, simulate)


def _log_nudge(session: str, target: str, reason: str, msg: str) -> None:
    path = os.environ.get("BABYSIT_LOG_FILE") or "nudge.log"
    try:
        with open(path, "a", encoding="utf-8") as log:
            log.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} | {session:20} | {target:16} | {reason:15} | {msg[:60]}\n")
    except OSError: pass


def _write_state(path: str | None, target: str, interval: int, state: str, action: str,
                 last_nudge: int, nonidle_since: int, next_poll: int, next_force: int,
                 next_nudge: int = 0, ema: dict | None = None) -> None:
    if not path: return
    out = {"target": target, "interval_secs": interval, "last_monitor_state": state,
           "last_action": action, "last_nudge_at": last_nudge,
           "nonidle_since": nonidle_since or None, "next_poll_at": next_poll,
           "next_force_nudge_at": next_force, "next_nudge_at": next_nudge}
    if ema: out["ema"] = ema
    dest = Path(path); dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp"); tmp.write_text(json.dumps(out) + "\n"); tmp.replace(dest)


class PaneWorker:
    """Stateful original pane loop, advanced one non-blocking poll at a time."""
    def __init__(self, session: str, pane: str, state_file: str | None = None):
        self.session, self.pane, self.target = session, pane, f"{session}:{pane}"
        self.state_file = state_file
        self.last_poll = 0.0; self.nonidle_since = 0; self.next_nudge_at = 0
        self.nudge_count = 0; self.mu = 5.0; self.sigma = 2.0
        self.pct_at_nudge = None; self.nudge_sent_ts = 0.0
        self.current_pct = None; self.current_reset_ts = None; self.stats_last_probe = 0.0
        self.initial_comms = True

    def _quota(self, spec: dict, now_f: float) -> None:
        agent = spec.get("agent", "")
        _ensure_quota_refresh(agent, int(spec.get("quota_probe_secs", 300)))
        if agent not in ("claude", "codex", "agy") or now_f - self.stats_last_probe < int(spec.get("quota_probe_secs", 300)):
            return
        try:
            result = get_cached_provider_usage(agent, ttl=30, force=False) if get_cached_provider_usage else {}
            limits = result.get("limits") or (result.get("parsed") or {}).get("limits") or []
            pcts = [x.get("pct") for x in limits if x.get("pct") is not None]
            resets = [x.get("reset_ts", 0) for x in limits if x.get("reset_ts", 0)]
            if pcts: self.current_pct = min(pcts); self.current_reset_ts = min(resets) if resets else None
        except Exception as exc:
            print(f"quota error {self.target}: {exc}", flush=True)
        self.stats_last_probe = now_f

    def _next_wait(self, spec: dict, now_f: float) -> int:
        alpha = float(spec.get("ema_alpha", .30)); k_var = float(spec.get("ema_k_var", 0))
        safety = float(spec.get("ema_safety", .92)); warmup = int(spec.get("ema_warmup", 3))
        if self.pct_at_nudge is not None and self.current_pct is not None and self.nudge_sent_ts:
            consumed = self.pct_at_nudge - self.current_pct
            if consumed > 0:
                self.mu = alpha * consumed + (1 - alpha) * self.mu
                self.sigma = alpha * abs(consumed - self.mu) + (1 - alpha) * self.sigma
        if self.nudge_count >= warmup and self.current_pct is not None and self.current_reset_ts and self.current_reset_ts > now_f:
            tau = max(self.current_reset_ts - now_f, 3600.) * (self.mu + k_var * self.sigma) / max(self.current_pct, 1.) / safety
            return int(max(int(spec.get("ema_min_wait", 30)), min(int(spec.get("ema_max_wait", 1200)), tau - (now_f - self.nudge_sent_ts))))
        return int(spec.get("interval_secs", 60))

    def tick(self, spec: dict, now_f: float | None = None) -> None:
        now_f = time.time() if now_f is None else now_f; now = int(now_f)
        interval = int(spec.get("interval_secs") or 5); poll = min(5, interval)
        if now_f - self.last_poll < poll: return
        self.last_poll = now_f
        self.state_file = spec.get("state_file") or self.state_file
        target = str(spec.get("target") or self.target); self.target = target
        simulate = bool(spec.get("simulate", False))
        _ensure_quota_refresh(str(spec.get("agent") or ""), int(spec.get("quota_probe_secs", 300)))
        if self.initial_comms:
            _drain_comms(self.session, target, self.pane, simulate=simulate, spec=spec)
            self.initial_comms = False
        state = _query_socket(f"/tmp/{self.session}_{self.pane}.sock").get("state", "")
        long_prompt = str(spec.get("long_prompt") or ""); short_prompt = str(spec.get("short_prompt") or long_prompt)
        if state in ("idle", ""): self.nonidle_since = 0
        elif not self.nonidle_since: self.nonidle_since = now
        force_at = self.nonidle_since + int(spec.get("max_nonidle_secs", 1800)) if long_prompt and self.nonidle_since else 0
        if state == "idle":
            _drain_comms(self.session, target, self.pane, simulate=simulate, spec=spec)
            if long_prompt or short_prompt:
                self._quota(spec, now_f)
                if not self.next_nudge_at:
                    msg, reason, etype = long_prompt, "startup", "babysit_startup"
                elif now >= self.next_nudge_at:
                    msg, reason, etype = short_prompt, "idle", "babysit"
                    if int(spec.get("clear_every") or 0) and self.nudge_count and self.nudge_count % int(spec["clear_every"]) == 0:
                        _log_nudge(self.session, target, "clear", "/clear")
                        _deliver(self.session, target, self.pane, "/clear", "clear", spec.get("via_log", True), simulate)
                        _log_nudge(self.session, target, "restore", long_prompt)
                        _deliver(self.session, target, self.pane, long_prompt, "babysit_restore", spec.get("via_log", True), simulate)
                        msg = ""
                else:
                    msg = ""
                if msg:
                    _log_nudge(self.session, target, reason, msg)
                    _deliver(self.session, target, self.pane, msg, etype, spec.get("via_log", True), simulate)
                if msg or (self.next_nudge_at and now >= self.next_nudge_at):
                    self.pct_at_nudge = self.current_pct; self.nudge_sent_ts = now_f; self.nudge_count += 1
                    self.next_nudge_at = now + self._next_wait(spec, now_f)
                ema = {"mu": round(self.mu, 3), "sigma": round(self.sigma, 3), "nudge_count": self.nudge_count}
                _write_state(self.state_file, target, interval, state, "idle_nudge" if long_prompt else "comms_idle",
                             now if long_prompt else 0, 0, now + poll, 0, self.next_nudge_at, ema)
            else:
                _write_state(self.state_file, target, interval, state, "comms_idle", now, 0, now + poll, 0)
            return
        if force_at and now >= force_at:
            _log_nudge(self.session, target, f"forced_{state or 'unknown'}", short_prompt)
            _deliver(self.session, target, self.pane, short_prompt, "babysit_forced", spec.get("via_log", True), simulate)
            self.nonidle_since = now; self.nudge_count += 1; self.next_nudge_at = now + interval
        _write_state(self.state_file, target, interval, state, f"wait_{state or 'unknown'}", 0,
                     self.nonidle_since, now + poll, force_at, self.next_nudge_at)


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: pane_worker.py <session-or-target> [interval] [long] [short]", file=sys.stderr); return 2
    target = _normalise_target(sys.argv[1]); session, pane = target.split(":", 1)
    interval = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    long = sys.argv[3] if len(sys.argv) > 3 else "Please continue."
    short = sys.argv[4] if len(sys.argv) > 4 else long
    worker = PaneWorker(session, pane, os.environ.get("BABYSIT_STATE_FILE"))
    spec = {"target": target, "interval_secs": interval, "long_prompt": long, "short_prompt": short,
            "clear_every": int(os.environ.get("BABYSIT_CLEAR_EVERY", 0)), "agent": os.environ.get("BABYSIT_AGENT", ""),
            "monitor": os.environ.get("BABYSIT_MONITOR", "1") == "1",
            "quota_probe_secs": int(os.environ.get("BABYSIT_STATS_EVERY", 300)),
            "ema_alpha": float(os.environ.get("BABYSIT_EMA_ALPHA", .30)), "ema_safety": float(os.environ.get("BABYSIT_EMA_SAFETY", .92)),
            "ema_k_var": float(os.environ.get("BABYSIT_EMA_K_VAR", 0)), "ema_warmup": int(os.environ.get("BABYSIT_EMA_WARMUP", 3)),
            "ema_min_wait": int(os.environ.get("BABYSIT_EMA_MIN_WAIT", 30)), "ema_max_wait": int(os.environ.get("BABYSIT_EMA_MAX_WAIT", 1200)),
            "max_nonidle_secs": int(os.environ.get("BABYSIT_MAX_NONIDLE_SECS", 1800))}
    spec_path = None
    if worker.state_file:
        state_path = Path(worker.state_file)
        spec_path = state_path.with_name(state_path.name.replace(".state.json", ".json"))
    spec_cache = None
    while True:
        if spec_path:
            loaded, spec_cache = load_spec(spec_path, spec_cache)
            if loaded is not None:
                spec = {**spec, **loaded}
        worker.tick(spec); time.sleep(1)


if __name__ == "__main__": raise SystemExit(main())
