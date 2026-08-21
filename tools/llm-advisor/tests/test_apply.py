import pytest
from advisor.apply import apply_model_change


def _fakes(agent=None, models=("qwen/qwen3-coder-30b",)):
    """Baut in-memory Fakes fuer die drei externen Raender."""
    state = {"agent": agent}

    def get_agent(agent_id):
        return state["agent"]

    def patch_agent(agent_id, body):
        cfg = dict((state["agent"] or {}).get("adapterConfig", {}))
        cfg.update(body["adapterConfig"])
        state["agent"] = {**(state["agent"] or {}), "adapterConfig": cfg}
        return state["agent"]

    def list_models():
        return set(models)

    return get_agent, patch_agent, list_models, state


def test_applies_model_and_verifies():
    agent = {"id": "vpe-id", "adapterConfig": {"model": "qwen3.6-35b-a3b"}}
    get_agent, patch_agent, list_models, state = _fakes(agent)
    res = apply_model_change("vpe-id", "qwen/qwen3-coder-30b",
                             get_agent=get_agent, patch_agent=patch_agent, list_models=list_models)
    assert res["model"] == "qwen/qwen3-coder-30b"
    assert state["agent"]["adapterConfig"]["model"] == "qwen/qwen3-coder-30b"


def test_rejects_unknown_model_without_patching():
    agent = {"id": "vpe-id", "adapterConfig": {"model": "qwen3.6-35b-a3b"}}
    get_agent, patch_agent, list_models, state = _fakes(agent)
    with pytest.raises(ValueError, match="model"):
        apply_model_change("vpe-id", "made-up",
                           get_agent=get_agent, patch_agent=patch_agent, list_models=list_models)
    # nichts veraendert
    assert state["agent"]["adapterConfig"]["model"] == "qwen3.6-35b-a3b"


def test_rejects_unknown_agent():
    get_agent, patch_agent, list_models, state = _fakes(agent=None)
    with pytest.raises(ValueError, match="agent"):
        apply_model_change("ghost-id", "qwen/qwen3-coder-30b",
                           get_agent=get_agent, patch_agent=patch_agent, list_models=list_models)
