import json, os, tempfile, pytest
from config import load_resident_set

HERE = os.path.dirname(__file__)

def test_loads_real_set():
    entries = load_resident_set(os.path.join(HERE, "resident-set.json"))
    assert len(entries) == 10
    keys = {(e["load_key"], e["device"]) for e in entries}
    # Seit 2026-10-21 ist die RTX aus der Farm (Coding-Rechner) — kein
    # Eintrag darf mehr auf sie zeigen.
    assert not any(d == "rtx" for _, d in keys)
    assert ("qwen/qwen3-coder-30b", "studio") in keys
    # PII-Proxy: Primaer google/gemma-4-12b (studio), Fallback gemma-4-31b-it-mlx
    # (macbook) — anderes Geraet. Faellt einer weg, blockiert der Proxy im
    # Stoerfall fail-closed und reisst Cloud-Agenten mit.
    assert ("google/gemma-4-12b", "studio") in keys
    assert ("gemma-4-31b-it-mlx", "macbook") in keys
    # qwen: Primaer whitestag-ai (5090), Fallback macbook.
    assert ("qwen3.6-35b-a3b-mlx", "macbook") in keys
    assert ("gemma-4-31b-it@q4_k_m", "whitestag-ai") in keys
    assert ("qwen3.6-35b-a3b", "whitestag-ai") in keys
    # Die ps_keys MUESSEN separat zugesichert werden: `keys` oben bildet
    # sich aus load_key (der Modelldatei), aber der Wert, der bei 37
    # Agenten als fallbackModel steht und ueber den sie den Node
    # ueberhaupt erreichen, ist der ps_key (der LM-Studio-Identifier).
    # Ein Tippfehler darin wird von NICHTS anderem gefunden —
    # modell-wacht liest resident-set.json nicht, nur soll-laufzeit.json.
    ps_keys = {(e["ps_key"], e["device"]) for e in entries}
    assert ("gemma-4-31b-it", "whitestag-ai") in ps_keys
    assert ("qwen3.6-35b-a3b", "whitestag-ai") in ps_keys
    assert ("qwen3.6-35b-a3b-mlx", "macbook") in ps_keys
    assert ("gemma-4-31b-it-mlx", "macbook") in ps_keys

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
