from advisor.agents import agent_profiles

ROWS = [
    # (agent_id, company_id, name, role, adapter_type, model,
    #  fallback_model, max_iterations, timeout_ms, context_length,
    #  max_turns_per_run)
    ("a1", "c1", "VP Engineering", "engineering", "lmstudio_local",
     "qwen2.5-coder-14b-instruct-mlx@8bit", "gemma-4-31b-it-mlx", 12, 300000, None, None),
    ("a2", "c1", "Büroleitung 2", "office", "claude_local",
     None, None, None, None, None, 80),
]


def test_local_agent_has_capability_and_local_flag():
    profs = agent_profiles(ROWS)
    vp = next(p for p in profs if p["name"] == "VP Engineering")
    assert vp["agent_id"] == "a1"
    assert vp["adapter_type"] == "lmstudio_local"
    assert vp["is_local"] is True
    assert vp["capability"] == "coding"


def test_claude_agent_marked_cloud():
    profs = agent_profiles(ROWS)
    bl = next(p for p in profs if p["name"] == "Büroleitung 2")
    assert bl["is_local"] is False
    assert bl["model"] in (None, "")


def test_profile_carries_the_adapter_limits():
    # WHI-3362: ohne diese Felder sieht der Advisor die eigentliche Ursache
    # von max_iterations/timeout nicht und schlaegt Modellwechsel vor.
    vp = next(p for p in agent_profiles(ROWS) if p["name"] == "VP Engineering")
    assert vp["max_iterations"] == 12
    assert vp["timeout_ms"] == 300000
    assert vp["fallback_model"] == "gemma-4-31b-it-mlx"
    assert vp["context_length"] is None


def test_profile_carries_the_turn_limit_of_claude_local_agents():
    """maxTurnsPerRun ist der einzige Wert, den der claude-local-Adapter als
    Lauf-Grenze liest. Ohne ihn im Profil kann signals.py nur "unbekannt"
    melden -- und der Hinweis wird wertlos."""
    profs = agent_profiles(ROWS)
    bl = next(p for p in profs if p["name"] == "Büroleitung 2")
    assert bl["max_turns_per_run"] == 80
    vp = next(p for p in profs if p["name"] == "VP Engineering")
    assert vp["max_turns_per_run"] is None
