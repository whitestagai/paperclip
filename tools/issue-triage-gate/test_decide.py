"""Tests fuer das typisierte Entscheidungs-Gate (Logit-Scoring statt Textgenerierung)."""
import math
import pytest
from decide import (
    build_request, extract_option_probs, decide,
    Decision, ABSTAIN_LOW_MASS, ABSTAIN_NO_LOGPROBS, ABSTAIN_LOW_CONFIDENCE,
)


def lp(token, prob):
    """Hilfsfunktion: ein top_logprobs-Eintrag mit gegebener Wahrscheinlichkeit."""
    return {"token": token, "logprob": math.log(prob)}


# --- Der Request: hier steckt die Falle, die mich zweimal erwischt hat ---

def test_request_schaltet_reasoning_ab():
    """Ohne reasoning_effort=none liefert LM Studio bei leerem content KEINE logprobs."""
    req = build_request("modell-x", "Zustand", "Anweisung", ["A", "B"])
    assert req["reasoning_effort"] == "none"


def test_request_fordert_logprobs_mit_genug_breite_an():
    req = build_request("modell-x", "Zustand", "Anweisung", ["A", "B"])
    assert req["logprobs"] is True
    assert req["top_logprobs"] >= 20


def test_request_generiert_nur_ein_token():
    req = build_request("modell-x", "Zustand", "Anweisung", ["A", "B"])
    assert req["max_tokens"] == 1
    assert req["temperature"] == 0


# --- Renormierung auf die erlaubten Optionen ---

def test_renormiert_auf_erlaubte_optionen():
    """Fremde Tokens fliegen raus, der Rest summiert auf 1."""
    top = [lp("A", 0.5), lp("Hallo", 0.3), lp("B", 0.2)]
    probs, mass = extract_option_probs(top, ["A", "B"])
    assert mass == pytest.approx(0.7)
    assert probs["A"] == pytest.approx(0.5 / 0.7)
    assert probs["B"] == pytest.approx(0.2 / 0.7)
    assert sum(probs.values()) == pytest.approx(1.0)


def test_summiert_dasselbe_label_in_mehreren_schreibweisen():
    """' A' und 'A' sind dieselbe Option — das Modell variiert das Leerzeichen."""
    top = [lp(" A", 0.4), lp("A", 0.3), lp("B", 0.3)]
    probs, mass = extract_option_probs(top, ["A", "B"])
    assert mass == pytest.approx(1.0)
    assert probs["A"] == pytest.approx(0.7)


def test_option_ohne_treffer_bekommt_null():
    top = [lp("A", 1.0)]
    probs, _ = extract_option_probs(top, ["A", "B", "C"])
    assert probs["B"] == 0.0
    assert probs["C"] == 0.0


# --- Das Gate: wann wird entschieden, wann abgegeben ---

def test_entscheidet_bei_klarer_lage():
    top = [lp("A", 0.95), lp("B", 0.05)]
    d = decide(top, ["A", "B"], min_confidence=0.9, min_mass=0.5)
    assert d.option == "A"
    assert d.confidence == pytest.approx(0.95)
    assert d.abstained is False


def test_gibt_unsichere_faelle_an_den_menschen():
    """0.59 war in der Messung ein echter Grenzfall — der darf nicht automatisch laufen."""
    top = [lp("A", 0.36), lp("B", 0.59), lp("C", 0.05)]
    d = decide(top, ["A", "B", "C"], min_confidence=0.9, min_mass=0.5)
    assert d.abstained is True
    assert d.reason == ABSTAIN_LOW_CONFIDENCE
    assert d.option == "B", "die Neigung bleibt sichtbar, auch wenn nicht entschieden wird"


def test_verweigert_wenn_das_modell_am_schema_vorbei_antwortet():
    """Liegt kaum Masse auf den erlaubten Optionen, ist die Verteilung nicht auswertbar."""
    top = [lp("Guten", 0.9), lp("A", 0.05), lp("B", 0.05)]
    d = decide(top, ["A", "B"], min_confidence=0.9, min_mass=0.5)
    assert d.abstained is True
    assert d.reason == ABSTAIN_LOW_MASS


def test_verweigert_ohne_logprobs():
    """Leeres content-Feld (Reasoning-Falle) -> keine Entscheidung, kein Rateschluss."""
    d = decide(None, ["A", "B"], min_confidence=0.9, min_mass=0.5)
    assert d.abstained is True
    assert d.reason == ABSTAIN_NO_LOGPROBS
    assert d.option is None


def test_abstain_ist_kein_stiller_default():
    """Eine Enthaltung darf nie als gueltige Entscheidung durchgehen."""
    d = decide(None, ["A", "B"])
    with pytest.raises(ValueError):
        d.require_option()
