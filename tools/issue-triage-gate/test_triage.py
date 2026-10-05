"""Tests fuer die Issue-Triage-Anwendung des Entscheidungs-Gates."""
import pytest
from decide import Decision, ABSTAIN_LOW_CONFIDENCE, ABSTAIN_NO_LOGPROBS
from triage import build_state, summarize, Issue


def issue(**kw):
    base = dict(id="i-1", title="Titel", origin_id=None, description="", age_days=5)
    base.update(kw)
    return Issue(**base)


# --- Was das Modell vom Issue sieht ---

def test_state_nennt_ob_origin_gesetzt_ist():
    """origin_id trennt Recovery-Symptome von echter Arbeit — muss im Zustand stehen."""
    mit = build_state(issue(origin_id="x-9"))
    ohne = build_state(issue(origin_id=None))
    assert "origin_id: gesetzt" in mit
    assert "origin_id: nicht gesetzt" in ohne


def test_state_nennt_das_alter():
    assert "19 Tage" in build_state(issue(age_days=19))


def test_state_markiert_leere_beschreibung_statt_sie_zu_verschweigen():
    assert "(leer)" in build_state(issue(description=""))


def test_state_kuerzt_ausufernde_beschreibungen():
    s = build_state(issue(description="x" * 5000))
    assert len(s) < 1200, "der Zustand muss klein bleiben, sonst wird die Entscheidung verrauscht"


def test_state_entfernt_zeilenumbrueche_aus_der_beschreibung():
    """Mehrzeilige Beschreibungen sollen die Feldstruktur des Zustands nicht zerreissen."""
    s = build_state(issue(description="Zeile1\n\nZeile2\r\nZeile3"))
    body = s.split("Beschreibung:", 1)[1]
    assert "\n" not in body.strip()


# --- Auswertung des Trockenlaufs ---

def test_summarize_trennt_entschieden_von_enthalten():
    ds = [
        Decision("A", 0.95, 1.0, {}, False),
        Decision("B", 0.59, 1.0, {}, True, ABSTAIN_LOW_CONFIDENCE),
        Decision(None, 0.0, 0.0, {}, True, ABSTAIN_NO_LOGPROBS),
    ]
    s = summarize(ds)
    assert s["gesamt"] == 3
    assert s["entschieden"] == 1
    assert s["enthalten"] == 2


def test_summarize_zaehlt_die_enthaltungsgruende_getrennt():
    """Ein fehlendes Logprob ist ein technischer Defekt, eine schwache Konfidenz nicht."""
    ds = [
        Decision(None, 0.0, 0.0, {}, True, ABSTAIN_NO_LOGPROBS),
        Decision("B", 0.5, 1.0, {}, True, ABSTAIN_LOW_CONFIDENCE),
        Decision("C", 0.6, 1.0, {}, True, ABSTAIN_LOW_CONFIDENCE),
    ]
    s = summarize(ds)
    assert s["gruende"][ABSTAIN_NO_LOGPROBS] == 1
    assert s["gruende"][ABSTAIN_LOW_CONFIDENCE] == 2


def test_summarize_verteilt_die_entschiedenen_optionen():
    ds = [
        Decision("A", 0.95, 1.0, {}, False),
        Decision("A", 0.97, 1.0, {}, False),
        Decision("C", 0.99, 1.0, {}, False),
        Decision("B", 0.5, 1.0, {}, True, ABSTAIN_LOW_CONFIDENCE),
    ]
    s = summarize(ds)
    assert s["optionen"] == {"A": 2, "C": 1}, "Enthaltungen zaehlen nicht als Option"


def test_summarize_haelt_leere_eingabe_aus():
    s = summarize([])
    assert s["gesamt"] == 0
    assert s["entschieden"] == 0


# --- Der Zustand darf nicht nachtraeglich verunreinigt werden ---

def test_ask_sendet_genau_den_gebauten_zustand():
    """Ein Cache-Busting-Zeitstempel im Zustand verschiebt die Konfidenz messbar
    (0.89 mit, 0.82 ohne) und kann die Schwellenentscheidung kippen."""
    from triage import ask
    gesehen = {}

    def transport(req):
        gesehen["req"] = req
        return {"choices": [{"logprobs": {"content": [{"top_logprobs": [
            {"token": "A", "logprob": -0.01}]}]}, "message": {"content": "A"}}]}

    it = issue(title="T", description="D", age_days=3)
    ask(it, 0.9, 0.5, transport=transport)
    gesendet = gesehen["req"]["messages"][-1]["content"]
    assert gesendet == build_state(it), "der Zustand muss unveraendert beim Modell ankommen"
