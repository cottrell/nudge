from swarm.models import extract_live_model

def test_extract_live_model_agy():
    capture = """
    ● Explored 1 file (topology.py)
    ────────────────────────────────────────────────────────────────────────────────────────────────────────────
    >
    ────────────────────────────────────────────────────────────────────────────────────────────────────────────
      Press up to edit queued messages                                                    Gemini 3.8 Flash · low
    """
    assert extract_live_model("agy", capture) == "Gemini 3.8 Flash · low"
    assert extract_live_model("antigravity", capture) == "Gemini 3.8 Flash · low"

def test_extract_live_model_codex():
    capture = """
      >_ OpenAI Codex (v0.166.0)
         ~/dev/nudge
      permissions: YOLO mode
    › Ask Codex to do anything
      GPT-6-Sol low · ~/dev/nudge
      ← for agents · ? for shortcuts
    """
    assert extract_live_model("codex", capture) == "GPT-6-Sol low"

    capture_luna = """
      >_ OpenAI Codex (v0.166.0)
         ~/dev/nudge
      permissions: YOLO mode
    › Ask Codex to do anything
      GPT-6-Luna low · ~/dev/nudge
      ? for shortcuts                                                                  ⚠ 1 warning · f2 to view
    """
    assert extract_live_model("codex", capture_luna) == "GPT-6-Luna low"

def test_extract_live_model_claude():
    capture_opus = """
     ▐▛███▛█   Claude Code v2.1.314
    ▝▜██████▀  Opus 5 with medium effort · Claude Pro
     ▝▝   ▝▝   ~/dev/nudge
    ────────────────────────────────────────────────────────────────────────────────────────────────────────────
    ❯ Try "how do I log an error?"
    """
    assert extract_live_model("claude", capture_opus) == "Opus 5 with medium effort"

    capture_haiku = """
     ▐▛███▛█   Claude Code v2.1.314
    ▝▜██████▀  Haiku 5.5 · Claude Pro
     ▝▝   ▝▝   ~/dev/nudge
    """
    assert extract_live_model("claude", capture_haiku) == "Haiku 5.5"

def test_extract_live_model_grok():
    capture_grok = """
     main ~/dev/nudge                                                                 1.8K / 256K │ [Dashboard]
     ╭────────────────────────────────────────────────────────────────────────────────────────────────────────╮
     │ ❯                                                                                                      │
     ╰─────────────────────────────────────────────────────────────────── Grok 4.7 (medium) · always-approve ─╯
     nudge │ Grok 4.7 │ 1% ctx
     Ctrl+x:shortcuts
    """
    assert extract_live_model("grok", capture_grok) in ("Grok 4.7 (medium)", "Grok 4.7")

def test_extract_live_model_none_when_empty():
    assert extract_live_model("agy", "") is None
    assert extract_live_model(None, None) is None
    assert extract_live_model("claude", "just random text without header\nhello") is None
