import json
import os

from evict_main import run

JETZT = 1_800_000_000_000
HIER = os.path.dirname(os.path.abspath(__file__))
SET = os.path.join(HIER, "resident-set.json")


def ps(*modelle):
    return lambda: json.dumps(list(modelle))


def modell(key, **kw):
    basis = {
        "type": "llm", "modelKey": key, "identifier": key,
        "deviceIdentifier": None, "ttlMs": None, "status": "idle", "queued": 0,
        "lastUsedTime": JETZT - 3_600_000, "sizeBytes": 20_000_000_000,
        "contextLength": 262144,
    }
    basis.update(kw)
    return basis


class Unloader:
    def __init__(self, rc=0, ausgabe=""):
        self.gerufen = []
        self._rc, self._ausgabe = rc, ausgabe

    def __call__(self, identifier):
        self.gerufen.append(identifier)
        return self._rc, self._ausgabe


def test_entlaedt_karteileiche_und_meldet_den_gewinn():
    u = Unloader()
    r = run(ps(modell("qwen/qwen3.6-35b-a3b")), u, SET, JETZT)
    assert u.gerufen == ["qwen/qwen3.6-35b-a3b"]
    assert r["entladen"] == ["qwen/qwen3.6-35b-a3b"]
    assert r["frei_gb"] == 20.0


def test_soll_modell_aus_dem_resident_set_bleibt():
    u = Unloader()
    r = run(ps(modell("google/gemma-4-12b")), u, SET, JETZT)
    assert u.gerufen == []
    assert r["entladen"] == []


def test_probelauf_ruehrt_nichts_an():
    u = Unloader()
    r = run(ps(modell("qwen/qwen3.6-35b-a3b")), u, SET, JETZT, trocken=True)
    assert u.gerufen == []
    assert r["entladen"] == ["qwen/qwen3.6-35b-a3b"]   # geplant, nicht getan


def test_fehlgeschlagenes_entladen_wird_gemeldet_nicht_verschluckt():
    u = Unloader(rc=1, ausgabe="model not found")
    r = run(ps(modell("qwen/qwen3.6-35b-a3b")), u, SET, JETZT)
    assert r["entladen"] == []
    assert "model not found" in r["fehlgeschlagen"][0]
    assert r["frei_gb"] == 0


def test_uebersicht_begruendet_jedes_behaltene_modell():
    r = run(ps(modell("google/gemma-4-12b"),
               modell("fremdes", deviceIdentifier="rtx-1")), Unloader(), SET, JETZT)
    text = "\n".join(r["uebersicht"])
    assert "steht im Soll" in text
    assert "anderen Geraet" in text


def test_leere_liste_ist_kein_fehler():
    r = run(lambda: "[]", Unloader(), SET, JETZT)
    assert r["entladen"] == [] and r["fehlgeschlagen"] == [] and r["geladen"] == 0


def test_versteht_auch_die_objekt_form_von_lms_ps():
    u = Unloader()
    r = run(lambda: json.dumps({"models": [modell("qwen/qwen3.6-35b-a3b")]}),
            u, SET, JETZT)
    assert r["entladen"] == ["qwen/qwen3.6-35b-a3b"]


# --- Log-Zeilen ------------------------------------------------------------

from evict_main import log_zeilen

def _ergebnis(**kw):
    basis = {"zeitpunkt": "2026-09-19T10:00:00", "geladen": 6, "entladen": [],
             "fehlgeschlagen": [], "frei_gb": 0.0, "trocken": False,
             "uebersicht": ["  a  bleibt: steht im Soll"]}
    basis.update(kw)
    return basis


def test_ruhiger_lauf_bleibt_eine_zeile():
    """Alle 10 Minuten 6 Zeilen waeren 860 Zeilen am Tag."""
    zeilen = log_zeilen(_ergebnis())
    assert len(zeilen) == 1
    assert "nichts zu tun" in zeilen[0]


def test_bei_aktion_steht_die_begruendung_im_log():
    zeilen = log_zeilen(_ergebnis(entladen=["x"], frei_gb=33.8))
    assert any("steht im Soll" in z for z in zeilen)
    assert any("33.8 GB frei" in z for z in zeilen)


def test_fehler_stehen_immer_drin():
    zeilen = log_zeilen(_ergebnis(fehlgeschlagen=["x: kaputt"]))
    assert any("FEHLER" in z for z in zeilen)


def test_ausfuehrlich_zeigt_alles_auch_ohne_aktion():
    assert len(log_zeilen(_ergebnis(), ausfuehrlich=True)) > 1
