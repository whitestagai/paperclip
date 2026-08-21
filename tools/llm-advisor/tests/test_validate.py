from advisor.state import validate_proposals

AGENTS = [
    {"name": "CTO", "agent_id": "cto-id", "company_id": "whi"},
    {"name": "VP Engineering", "agent_id": "vpe-id", "company_id": "whi"},
]
MODELS = {"qwen3.6-35b-a3b-mlx", "qwen/qwen3-coder-30b"}


def test_valid_proposal_passes_and_gets_agent_id():
    valid, rejected = validate_proposals(
        [{"agent": "VP Engineering", "to_model": "qwen/qwen3-coder-30b"}],
        AGENTS, MODELS,
    )
    assert rejected == []
    assert len(valid) == 1
    assert valid[0]["agent_id"] == "vpe-id"


def test_unknown_agent_is_rejected_with_reason():
    valid, rejected = validate_proposals(
        [{"agent": "Label Manager", "to_model": "qwen/qwen3-4b"}],
        AGENTS, MODELS,
    )
    assert valid == []
    assert len(rejected) == 1
    assert "agent" in rejected[0]["reason"].lower()


def test_unknown_model_is_rejected_with_reason():
    valid, rejected = validate_proposals(
        [{"agent": "CTO", "to_model": "totally-made-up-model"}],
        AGENTS, MODELS,
    )
    assert valid == []
    assert len(rejected) == 1
    assert "model" in rejected[0]["reason"].lower()


# --- from_model-Drift: Vorschlag basiert auf falschem Ist-Modell ---
AGENTS_WITH_MODEL = [
    {"name": "CTO", "agent_id": "cto-id", "company_id": "whi",
     "model": "qwen3.6-35b-a3b-mlx"},
    {"name": "VP Engineering", "agent_id": "vpe-id", "company_id": "whi",
     "model": "qwen/qwen3-coder-30b"},
]


def test_from_model_drift_is_rejected():
    # Agent laeuft real auf 35B MoE, Vorschlag behauptet qwen3-4b -> Drift.
    valid, rejected = validate_proposals(
        [{"agent": "CTO", "to_model": "qwen/qwen3-coder-30b",
          "from_model": "qwen/qwen3-4b"}],
        AGENTS_WITH_MODEL, MODELS,
    )
    assert valid == []
    assert len(rejected) == 1
    assert "from_model" in rejected[0]["reason"].lower()


def test_matching_from_model_passes():
    # from_model deckt sich mit dem live-Modell -> valid.
    valid, rejected = validate_proposals(
        [{"agent": "CTO", "to_model": "qwen/qwen3-coder-30b",
          "from_model": "qwen3.6-35b-a3b-mlx"}],
        AGENTS_WITH_MODEL, MODELS,
    )
    assert rejected == []
    assert len(valid) == 1
    assert valid[0]["agent_id"] == "cto-id"


def test_missing_from_model_is_not_treated_as_drift():
    # Ohne from_model kann kein Drift vorliegen -> valid.
    valid, rejected = validate_proposals(
        [{"agent": "CTO", "to_model": "qwen/qwen3-coder-30b"}],
        AGENTS_WITH_MODEL, MODELS,
    )
    assert rejected == []
    assert len(valid) == 1


def test_agent_without_model_field_skips_drift_check():
    # Roster ohne 'model' (aeltere Snapshots) -> Drift-Pruefung inaktiv.
    valid, rejected = validate_proposals(
        [{"agent": "CTO", "to_model": "qwen/qwen3-coder-30b",
          "from_model": "irgendwas"}],
        AGENTS, MODELS,
    )
    assert rejected == []
    assert len(valid) == 1
