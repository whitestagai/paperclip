import json, pathlib
from advisor.resources import parse_models, budget_report, parse_device_names

FIX = pathlib.Path(__file__).parent / "fixtures"

def _load(name):
    return json.loads((FIX / name).read_text())

def test_parse_models_extracts_size_and_quant():
    models = parse_models(_load("lms_ls.json"))
    assert any(m["model_key"] for m in models)
    m = models[0]
    assert m["size_gb"] > 0
    assert "quant" in m

def test_loaded_model_reports_its_context_length():
    # WHI-3348: das Zielmodell war mit 65k geladen, die Quelle mit 98k --
    # ohne dieses Feld ist der Kontext-Verlust unsichtbar.
    loaded = parse_models(_load("lms_ps.json"))
    m = next(m for m in loaded if m["model_key"] == "qwen3.6-35b-a3b-mlx")
    assert m["context_length"] == 262144
    assert m["max_context_length"] == 262144


def test_local_model_is_always_on():
    loaded = parse_models(_load("lms_ps.json"))
    m = next(m for m in loaded if m["device_id"] is None)
    assert m["device"] == "Local"
    assert m["always_on"] is True


def test_remote_model_gets_its_device_name_and_policy():
    # WHI-3348: genau dieses Modell wurde vorgeschlagen -- es liegt auf der
    # RTX, die nachts aus ist.
    names = parse_device_names((FIX / "lms_ps_table.txt").read_text())
    raw = [{"type": "llm", "modelKey": "google/gemma-4-31b-qat",
            "identifier": "google/gemma-4-31b-qat", "sizeBytes": 18851800193,
            "deviceIdentifier": "3f6d2489f519c745243a6c4daa0334d5",
            "contextLength": 65024, "maxContextLength": 262144}]
    m = parse_models(raw, device_names=names)[0]
    assert m["device"] == "RTX Pro 6000"
    assert m["always_on"] is False


def test_unknown_remote_device_defaults_to_not_always_on():
    # Fail-safe: ein unbekanntes Fremdgeraet gilt als NICHT durchgaengig
    # verfuegbar, damit ein Vorschlag eher gewarnt als stillschweigend
    # durchgewunken wird.
    m = parse_models([{"type": "llm", "modelKey": "x", "sizeBytes": 1,
                       "deviceIdentifier": "deadbeefdeadbeef"}], device_names={})[0]
    assert m["always_on"] is False
    assert "deadbeef" in m["device"]


def test_parse_device_names_maps_identifier_to_device_column():
    names = parse_device_names((FIX / "lms_ps_table.txt").read_text())
    assert names["gemma-4-31b-it-mlx"] == "MacbookM5Mx128"
    assert names["google/gemma-4-31b-qat"] == "RTX Pro 6000"


def test_budget_report_caps_at_limit():
    models = parse_models(_load("lms_ls.json"))
    loaded = parse_models(_load("lms_ps.json"))
    rep = budget_report(models, loaded, limit_gb=110.0)
    assert rep["limit_gb"] == 110.0
    assert rep["loaded_gb"] >= 0
    assert rep["disk_gb"] >= rep["loaded_gb"]
    assert rep["free_loadable_gb"] == round(110.0 - rep["loaded_gb"], 2)

def test_budget_excludes_remote_linked_gpu():
    # Regression: ein remote-gelinktes GPU-Modell (deviceIdentifier gesetzt)
    # darf NICHT gegen das 110-GB-Mac-Budget gezaehlt werden.
    all_models = [
        {"model_key": "gemma", "size_gb": 33.8, "device_id": None},
        {"model_key": "ud", "size_gb": 68.1, "device_id": "3f6d2489f519c745243a6c4daa0334d5"},
    ]
    loaded = all_models
    rep = budget_report(all_models, loaded, limit_gb=110.0)
    assert rep["loaded_gb"] == 33.8          # nur Mac-lokal
    assert rep["over_limit"] is False        # 154 GB waere faelschlich KRITISCH
    assert rep["remote_loaded_gb"] == 68.1   # GPU separat ausgewiesen
    assert rep["remote_keys"] == ["ud"]
    assert "ud" not in rep["loaded_keys"]
