"""Detect active model in live tmux pane captures or fallback to launch config."""
from __future__ import annotations

import json
from pathlib import Path
import re

try:
    from .session_ids import process_tree, cmdline_of
except ImportError:
    from session_ids import process_tree, cmdline_of

# Match patterns in agent TUIs
# Antigravity (agy): e.g. "Gemini 3.8 Flash · low" or "Gemini 3.8 Flash" at right of status line
_AGY_MODEL_RE = re.compile(
    r"(?:^|\s{2,})((?:Gemini|Claude|GPT|Argon|Grok)[^\n·\│]+(?:\s*·\s*(?:high|medium|low))?)\s*$",
    re.I,
)

# Codex: e.g. "  GPT-6-Sol low · ~/dev/nudge" or "  GPT-6-Luna low · ~/dev/nudge"
_CODEX_MODEL_RE = re.compile(
    r"^\s*((?:GPT|o\d|codex)[^\n·]+(?:\s+(?:high|medium|low))?)\s*·\s*~",
    re.I,
)

# Grok: e.g. "╰────── Grok 4.7 (medium) · always-approve ─╯" or "nudge │ Grok 4.7 │ 1% ctx"
_GROK_BOX_RE = re.compile(
    r"───\s*(Grok[^\n·─]+(?:\s*\([^)]+\))?)\s*·",
    re.I,
)
_GROK_BAR_RE = re.compile(
    r"│\s*(Grok\s+[0-9a-zA-Z\.\-]+(?:\s*\([^)]+\))?)\s*│",
    re.I,
)

# Claude: header banner e.g. "▝▜██████▀  Opus 5 with medium effort · Claude Pro"
_CLAUDE_HEADER_RE = re.compile(
    r"▝▜██████▀\s+([^\n·]+(?:\s+with\s+[^\n·]+effort)?)\s*·\s*Claude",
    re.I,
)

# Aider: e.g. "Model: openrouter/google/gemini-2.5-flash" or "Model: gpt-4o"
_AIDER_MODEL_RE = re.compile(
    r"^\s*Model:\s*(\S+)",
    re.I,
)


def extract_live_model_from_screen(agent: str | None, text: str | None) -> str | None:
    """Extract the active model string from pane captured text for a given agent."""
    if not text:
        return None
    agent = (agent or "").strip().lower()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return None

    bottom_slice = lines[-12:]

    if agent in ("agy", "antigravity"):
        for line in reversed(bottom_slice):
            m = _AGY_MODEL_RE.search(line)
            if m:
                val = m.group(1).strip()
                if not any(skip in val.lower() for skip in ["press up to", "tip:", "ctrl+"]):
                    return val

    elif agent == "codex":
        for line in reversed(bottom_slice):
            m = _CODEX_MODEL_RE.search(line)
            if m:
                return m.group(1).strip()

    elif agent == "grok":
        for line in reversed(bottom_slice):
            m = _GROK_BOX_RE.search(line)
            if m:
                return m.group(1).strip()
            m = _GROK_BAR_RE.search(line)
            if m:
                return m.group(1).strip()

    elif agent == "claude":
        for line in lines:
            m = _CLAUDE_HEADER_RE.search(line)
            if m:
                return m.group(1).strip()

    elif agent == "aider":
        for line in reversed(lines):
            m = _AIDER_MODEL_RE.search(line)
            if m:
                return m.group(1).strip()

    # Generic fallback across patterns
    for line in reversed(bottom_slice):
        for rx in (_CODEX_MODEL_RE, _GROK_BOX_RE, _GROK_BAR_RE):
            m = rx.search(line)
            if m:
                return m.group(1).strip()
        m = _AGY_MODEL_RE.search(line)
        if m and not any(skip in m.group(1).lower() for skip in ["press up to", "tip:", "ctrl+"]):
            return m.group(1).strip()

    for line in lines:
        m = _CLAUDE_HEADER_RE.search(line)
        if m:
            return m.group(1).strip()

    return None


def extract_live_model_from_process(agent: str | None, pid: int | None) -> str | None:
    """Fallback extraction from process tree / session metadata when screen is scrolled past."""
    if not pid:
        return None
    agent = (agent or "").strip().lower()
    proc_root = Path("/proc")

    tree = process_tree(pid, proc_root) if pid else []

    # Claude: check ~/.claude/sessions/<pid>.json and its active jsonl
    if agent == "claude":
        for p in tree:
            session_file = Path.home() / f".claude/sessions/{p}.json"
            if session_file.is_file():
                try:
                    data = json.loads(session_file.read_text())
                    sid = data.get("sessionId")
                    cwd = data.get("cwd", "")
                    if sid and cwd:
                        slug = cwd.replace("/", "-")
                        jsonl = Path.home() / f".claude/projects/{slug}/{sid}.jsonl"
                        if jsonl.is_file():
                            with open(jsonl, "rb") as f:
                                f.seek(0, 2)
                                size = f.tell()
                                f.seek(max(0, size - 16384))
                                chunk = f.read().decode("utf-8", errors="ignore")
                                for line in reversed(chunk.splitlines()):
                                    if "requestedModel" in line or '"model":' in line:
                                        rec = json.loads(line)
                                        m = rec.get("requestedModel") or rec.get("message", {}).get("model")
                                        if m:
                                            clean = m.replace("claude-", "").replace("-", " ").title()
                                            effort = rec.get("effort")
                                            return f"{clean} ({effort})" if effort else clean
                except Exception:
                    pass

    # Process tree argv fallback: look for --model / -m
    try:
        for p in tree:
            cmd = cmdline_of(p, proc_root)
            if not cmd:
                continue
            for i, arg in enumerate(cmd):
                if arg in ("--model", "-m") and i + 1 < len(cmd):
                    return cmd[i + 1]
    except Exception:
        pass

    return None


def extract_live_model(agent: str | None, text: str | None, pid: int | None = None) -> str | None:
    """Extract model from screen capture, or fallback to session/process inspection."""
    m = extract_live_model_from_screen(agent, text)
    if m:
        return m
    if pid:
        return extract_live_model_from_process(agent, pid)
    return None
