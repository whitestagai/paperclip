"""Der Ist-Zustand entsteht auch dann, wenn beide externen Quellen tot sind.

Die Telemetrie ist der wichtigere Teil des Dokuments. Ein Netzausfall darf
den Lauf nicht kippen -- sonst faellt die Routine wegen einer Nebenquelle aus.
"""
import json

import pytest

import collect_ist_zustand as cz


@pytest.fixture(autouse=True)
def _isolierte_ablehnungsliste(tmp_path, monkeypatch):
    """Verhindert Schreibzugriffe auf die echte state/-Ablehnungsliste.

    Dieses Repo ist der Live-Pfad, von dem die Wochenroutine tatsaechlich
    laeuft -- ein Testlauf darf ihn nicht veraendern. Jeder Test in dieser
    Datei bekommt standardmaessig eine isolierte Ziel-Datei statt der echten
    state/abgelehnte-modelle.json. Tests, die das Kopierverhalten selbst
    pruefen, ueberschreiben `cz.ABLEHNUNGEN` danach erneut mit ihrem eigenen
    `tmp_path` -- das ist redundant, aber unschaedlich.
    """
    monkeypatch.setattr(cz, "ABLEHNUNGEN", tmp_path / "abgelehnte-modelle.json")


def test_markt_ausfall_kippt_das_dokument_nicht(monkeypatch):
    monkeypatch.setattr(cz, "lade_key", lambda: None)
    monkeypatch.setattr(cz.market, "fetch_web",
                        lambda *a, **k: {"status": "nicht_verfuegbar",
                                         "frage": "x", "abgerufen_am": "2026-08-20",
                                         "quellen": [], "hinweis": None,
                                         "grund": "Connection refused"})
    markt = cz.sammle_markt(["gemma-4-31b-it-mlx"])
    assert markt["status"] == "nicht_verfuegbar"
    assert "kein API-Key" in markt["grund"]
    assert "Connection refused" in markt["grund"]


def test_eine_exception_im_marktteil_wird_gefangen(monkeypatch):
    def kaputt(*a, **k):
        raise RuntimeError("unerwartet")

    monkeypatch.setattr(cz.market, "fetch_aa", kaputt)
    markt = cz.sammle_markt(["gemma-4-31b-it-mlx"])
    assert markt["status"] == "nicht_verfuegbar"
    assert "RuntimeError" in markt["grund"]


def test_der_ausfall_traegt_dieselben_schluessel_wie_der_erfolgsfall(monkeypatch):
    """Auch der Notausgang liefert aa_stand und quelle -- als None.

    Der Brief macht "Quelle: Artificial Analysis, Stand <aa_stand>" zur
    Pflicht. Fehlte der Schluessel ganz, muesste der Agent an genau der
    Stelle raten, an der er es nicht darf.
    """
    def kaputt(*a, **k):
        raise RuntimeError("unerwartet")

    monkeypatch.setattr(cz.market, "fetch_aa", kaputt)
    markt = cz.sammle_markt(["gemma-4-31b-it-mlx"])
    for schluessel in ("status", "grund", "aa_stand", "quelle", "modelle",
                       "nicht_gelistet", "suche"):
        assert schluessel in markt, schluessel
    assert markt["aa_stand"] is None
    assert markt["quelle"] is None


def test_die_websuche_wird_kurz_gehalten(monkeypatch):
    """`suche` trug 19.470 von 98.824 Zeichen -- ein Fuenftel des Dokuments.

    Das Erfolgskriterium des Umbaus ist eine sinkende Iterationszahl des
    Agenten; ein aufgeblaehtes Dokument arbeitet dagegen.
    """
    gesehen = {}

    monkeypatch.setattr(cz, "lade_key", lambda: None)

    def merke(frage, **kwargs):
        gesehen.update(kwargs)
        return {"status": "ok", "frage": frage, "abgerufen_am": "2026-08-20",
                "quellen": [], "hinweis": None}

    monkeypatch.setattr(cz.market, "fetch_web", merke)
    cz.sammle_markt(["gemma-4-31b-it-mlx"])
    assert gesehen["zeichen"] <= 1500


def test_ablehnungsliste_wird_aus_der_vorlage_kopiert(tmp_path, monkeypatch):
    """Fehlt state/abgelehnte-modelle.json, wird sie aus der Vorlage angelegt.

    Ohne diese Kopie bliebe die Ablehnung von qwen3.8-27b (17.08.) fuer immer
    wirkungslos, weil lade_ablehnungen() bei einer fehlenden Datei
    unauffaellig {} liefert -- das Modell kaeme jede Woche neu zur Empfehlung.
    """
    ziel = tmp_path / "abgelehnte-modelle.json"
    monkeypatch.setattr(cz, "ABLEHNUNGEN", ziel)
    monkeypatch.setattr(cz, "lade_key", lambda: None)
    monkeypatch.setattr(cz.market, "fetch_web",
                        lambda *a, **k: {"status": "nicht_verfuegbar",
                                         "frage": "x", "abgerufen_am": "2026-08-20",
                                         "quellen": [], "hinweis": None,
                                         "grund": "Connection refused"})
    cz.sammle_markt(["gemma-4-31b-it-mlx"])
    assert ziel.exists()
    inhalt = json.loads(ziel.read_text())
    assert inhalt[0]["modell"] == "qwen3.8-27b"


def test_kaputte_vorlage_kippt_sammle_markt_nicht(tmp_path, monkeypatch):
    """Ein Kopierfehler jenseits von OSError darf den Marktteil nicht kippen.

    `ABLEHNUNGEN_VORLAGE.read_text()` nutzt die Locale-Kodierung. Eine von
    Hand kaputt kodierte Vorlage wirft `UnicodeDecodeError` -- eine
    `ValueError`-Unterklasse, kein `OSError` -- und ist damit ein
    realistischer Fall (Hand-Edit), kein Konstrukt. Der Kopierschritt muss
    deshalb INNERHALB des breiten `except Exception` in `sammle_markt`
    laufen; die eigene `except OSError`-Klausel des Kopierhelfers bleibt
    bewusst schmal.
    """
    ziel = tmp_path / "abgelehnte-modelle.json"
    kaputte_vorlage = tmp_path / "vorlage.json"
    kaputte_vorlage.write_bytes(b"\xff\xfe\xff")
    monkeypatch.setattr(cz, "ABLEHNUNGEN", ziel)
    monkeypatch.setattr(cz, "ABLEHNUNGEN_VORLAGE", kaputte_vorlage)
    monkeypatch.setattr(cz, "lade_key", lambda: None)
    monkeypatch.setattr(cz.market, "fetch_web",
                        lambda *a, **k: {"status": "nicht_verfuegbar",
                                         "frage": "x", "abgerufen_am": "2026-08-20",
                                         "quellen": [], "hinweis": None,
                                         "grund": "Connection refused"})
    markt = cz.sammle_markt(["gemma-4-31b-it-mlx"])
    assert markt["status"] == "nicht_verfuegbar"
    assert "UnicodeDecodeError" in markt["grund"]
    assert not ziel.exists()


def test_vorhandene_ablehnungsliste_bleibt_unangetastet(tmp_path, monkeypatch):
    """Eine bereits vorhandene Datei wird nie ueberschrieben.

    Sie traegt Walters spaetere Ablehnungen -- ein Ueberschreiben mit der
    Vorlage wuerde diese stillschweigend verwerfen.
    """
    ziel = tmp_path / "abgelehnte-modelle.json"
    ziel.write_text('[{"modell": "anderes-modell"}]')
    monkeypatch.setattr(cz, "ABLEHNUNGEN", ziel)
    monkeypatch.setattr(cz, "lade_key", lambda: None)
    monkeypatch.setattr(cz.market, "fetch_web",
                        lambda *a, **k: {"status": "nicht_verfuegbar",
                                         "frage": "x", "abgerufen_am": "2026-08-20",
                                         "quellen": [], "hinweis": None,
                                         "grund": "Connection refused"})
    cz.sammle_markt(["gemma-4-31b-it-mlx"])
    assert json.loads(ziel.read_text()) == [{"modell": "anderes-modell"}]


def test_auch_die_zugewiesenen_agentenmodelle_werden_bewertet(monkeypatch):
    """Der erste echte Lauf (21.08.) bewertete 26 von 40 Agenten nicht.

    `lm_keys` kam allein aus `models_on_disk`, also aus `lms ls` dieses
    Geraets. `gemma-4-31b-it-mlx` liegt aber auf dem MacBook und taucht dort
    nicht auf -- ausgerechnet das Modell von 22 Agenten hatte deshalb keine
    Marktzahlen. Bewertet wird, was die Agenten fahren, nicht nur was hier
    auf der Platte liegt.
    """
    gesehen = {}

    def fake_sammle(lm_keys):
        gesehen["keys"] = list(lm_keys)
        return {"status": "ok", "modelle": {}, "nicht_gelistet": [], "suche": None}

    monkeypatch.setattr(cz, "sammle_markt", fake_sammle)
    monkeypatch.setattr(cz, "fetch_rows", lambda days: [])
    monkeypatch.setattr(cz, "aggregate_runs", lambda rows: [])
    monkeypatch.setattr(cz, "fetch_agent_rows", lambda: [])
    monkeypatch.setattr(cz, "agent_profiles", lambda rows: [
        {"agent_id": "a1", "name": "CMO", "model": "gemma-4-31b-it-mlx"},
        {"agent_id": "a2", "name": "CTO", "model": "nur-auf-platte"},
        {"agent_id": "a3", "name": "DPO", "model": None},
    ])
    monkeypatch.setattr(cz, "fetch_device_names", lambda: {})
    monkeypatch.setattr(cz, "fetch_ls", lambda: "")
    monkeypatch.setattr(cz, "fetch_ps", lambda: "")
    monkeypatch.setattr(cz, "parse_models", lambda raw, device_names=None: [
        {"model_key": "nur-auf-platte"}])
    monkeypatch.setattr(cz, "budget_report", lambda a, l, limit_gb: {"loaded_gb": 0, "limit_gb": limit_gb})
    monkeypatch.setattr(cz, "annotate_profiles", lambda *a, **k: None)
    monkeypatch.setattr(cz, "evidence_line", lambda *a, **k: "")
    monkeypatch.setattr(cz, "OUT", cz.Path(str(cz.OUT) + ".test-tmp"))

    cz.main()
    cz.OUT.unlink()

    # Das Remote-Modell der Agenten ist dabei, das reine Plattenmodell auch,
    # und ein Agent ohne Zuweisung erzeugt keinen leeren Schluessel.
    assert "gemma-4-31b-it-mlx" in gesehen["keys"]
    assert "nur-auf-platte" in gesehen["keys"]
    assert None not in gesehen["keys"]
    assert gesehen["keys"] == sorted(set(gesehen["keys"]))
