"""Befundform je Ursachenklasse (WHI-3389).

Wenn das einzige Werkzeug ein Modellwechsel ist, sieht jedes Problem wie ein
falsches Modell aus. Die Ausgabeform folgt deshalb der Ursache.
"""
from advisor.findings import build_findings


def _profile(name, cause, actionable=True, allowed=False, **kw):
    p = {
        "agent_id": "a-" + name, "name": name,
        "model": "gemma-4-31b-it-mlx", "max_iterations": 12,
        "telemetry": {"total_runs": 80, "succeeded": 20, "fail_rate": 0.75,
                      "llm_error": 40,
                      "top_errors": [{"code": "llm_error", "count": 40,
                                      "sample": "LM Studio API error 500"}]},
        "signals": {"cause": cause, "actionable": actionable,
                    "model_change_allowed": allowed,
                    "config_signals": {}, "model_signals": {"llm_error": 40},
                    "upstream_signals": {}},
    }
    p.update(kw)
    return p


def test_an_upstream_finding_never_carries_an_action():
    # Rate-Limit heilt kein Modellwechsel und keine Config-Aenderung.
    out = build_findings([_profile("n8n", "upstream")], window_days=7)
    assert out[0]["action"] is None
    assert out[0]["cause"] == "upstream"


def test_an_adapter_finding_never_carries_an_action():
    out = build_findings([_profile("Rechercheur", "adapter")], window_days=7)
    assert out[0]["action"] is None


def test_a_config_finding_carries_a_concrete_patch():
    out = build_findings([_profile("CHO", "config")], window_days=7)
    assert out[0]["action"]["kind"] == "config"
    assert "12" in out[0]["action"]["hint"]


def test_a_model_finding_carries_a_model_change_when_allowed():
    out = build_findings([_profile("CMO", "model", allowed=True)], window_days=7)
    assert out[0]["action"]["kind"] == "model"
    assert out[0]["action"]["from_model"] == "gemma-4-31b-it-mlx"


def test_a_model_cause_without_permission_carries_no_action():
    out = build_findings([_profile("CMO", "model", allowed=False)], window_days=7)
    assert out[0]["action"] is None


def test_findings_below_the_threshold_are_dropped():
    out = build_findings([_profile("CMO", "model", actionable=False)], window_days=7)
    assert out == []


def test_a_finding_without_a_cause_is_dropped():
    out = build_findings([_profile("Ruhig", "none")], window_days=7)
    assert out == []


def test_every_finding_carries_evidence_and_the_dominant_plaintext():
    out = build_findings([_profile("n8n", "upstream")], window_days=7)
    assert "llm_error=40x" in out[0]["evidence"]
    assert "LM Studio API error 500" in out[0]["dominant"]


def test_a_finding_without_plaintext_still_works():
    p = _profile("Leise", "model", allowed=True)
    p["telemetry"]["top_errors"] = []
    assert build_findings([p], window_days=7)[0]["dominant"] == ""


def test_a_finding_names_its_company():
    # "Vault-Maintainer" und "Link-Detektor" existieren je zweimal, in
    # WHITESTAG und Clara Sound. Ohne Company ist ein Befund mehrdeutig.
    p = _profile("Vault-Maintainer", "config", company_id="c-clara")
    assert build_findings([p], window_days=7)[0]["company_id"] == "c-clara"
