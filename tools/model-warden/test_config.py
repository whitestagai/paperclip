import json, os, tempfile, pytest
from config import load_resident_set

HERE = os.path.dirname(__file__)

def test_loads_real_set():
    entries = load_resident_set(os.path.join(HERE, "resident-set.json"))
    assert len(entries) == 11
    keys = {(e["load_key"], e["device"]) for e in entries}
    # coder-next lebt NUR auf der RTX (Tages-Boost). Der MacBook-Nacht-Fallback
    # wurde per Real-Test 2026-07-25 widerlegt (Guardrail p1 UND p4) -> coder-30b (Studio).
    assert ("qwen/qwen3-coder-next", "macbook") not in keys
    assert ("qwen/qwen3-coder-next", "rtx") in keys
    assert ("qwen/qwen3-coder-30b", "studio") in keys
    # Fallback-Klassifikator des PII-Proxys: MUSS auf der RTX liegen, also auf
    # einem anderen Geraet als das Primaermodell (studio). Faellt dieser Eintrag
    # weg, hat der Proxy im Stoerfall wieder keinen Fallback.
    assert ("google/gemma-4-12b-qat", "rtx") in keys
    assert ("google/gemma-4-12b", "studio") in keys
    # Fallback-Geraet beider Agentenfamilien seit 2026-10-06. Fallen diese
    # Eintraege weg, haben 25 gemma-Agenten ihren Fallback wieder auf
    # demselben Geraet wie das Primaermodell.
    assert ("gemma-4-31b-it@q4_k_m", "whitestag-ai") in keys
    assert ("abiray/qwen3.6-35b-a3b", "whitestag-ai") in keys

def test_rejects_unknown_device(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text(json.dumps({"devices": ["studio"], "models": [
        {"device": "moon", "ps_key": "x", "load_key": "x", "ctx": 10, "parallel": 4, "when": "always"}]}))
    with pytest.raises(ValueError):
        load_resident_set(str(p))

def test_rejects_missing_field(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text(json.dumps({"devices": ["studio"], "models": [
        {"device": "studio", "load_key": "x", "ctx": 10, "parallel": 4, "when": "always"}]}))
    with pytest.raises(ValueError):
        load_resident_set(str(p))
