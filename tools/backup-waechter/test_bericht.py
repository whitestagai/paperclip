#!/usr/bin/env python3
"""Tests des Tagesberichts. Aufruf: python3 -m pytest test_bericht.py -q

Der Bericht darf nie eine Zahl behaupten, die er nicht hat. Ein „unverändert"
im Zuwachs ist eine Aussage — steht es da, obwohl gar kein Vorlauf existiert,
liest Walter Ruhe, wo Unwissen ist.
"""
import json

import waechter


# --- Zuwachs ---------------------------------------------------------------

def test_ohne_vorlauf_kein_zuwachs():
    """Beim allerersten Bericht gibt es nichts zu vergleichen. Dann bleibt die
    Spalte leer, statt einen Zuwachs von null zu erfinden."""
    assert waechter._delta_text(5, None, "stk") == ""
    assert waechter._delta_text(12.0, None) == ""


def test_unveraendert_wird_ausgewiesen():
    """Ein Zuwachs von exakt null ist die interessanteste Zahl im Bericht:
    der Job laeuft, sichert aber nichts mehr. Er darf nicht verschwiegen
    werden, nur weil er unauffaellig aussieht."""
    assert waechter._delta_text(5, 5, "stk") == " (unverändert)"
    assert waechter._delta_text(12.0, 12.0) == " (unverändert)"


def test_zuwachs_mit_vorzeichen():
    assert waechter._delta_text(7, 5, "stk") == " (+2)"
    assert waechter._delta_text(3, 5, "stk") == " (-2)"
    assert waechter._delta_text(12.5, 10.0) == " (+2.5 GB)"


def test_winziger_gb_zuwachs_gilt_als_unveraendert():
    """Messrauschen im Megabyte-Bereich soll nicht als Veraenderung
    erscheinen."""
    assert waechter._delta_text(12.01, 12.0) == " (unverändert)"


# --- Snapshots je Schlagwort ----------------------------------------------

def test_zaehlt_je_schlagwort():
    snaps = [
        {"tags": ["claude-code"]},
        {"tags": ["claude-code"]},
        {"tags": ["system-secrets", "dateien"]},
        {"tags": []},
        {},
    ]
    ergebnis = waechter.zaehle_je_tag(snaps, ["claude-code", "system-secrets",
                                              "nas-projekte"])
    assert ergebnis == {"claude-code": 2, "system-secrets": 1,
                        "nas-projekte": 0}


def test_stummes_repo_liefert_keine_zahlen():
    """Wenn restic nicht antwortet, darf der Bericht keine Nullen zeigen —
    die laesen sich wie „alle Snapshots verschwunden"."""
    assert waechter.zaehle_je_tag(None, ["claude-code"]) == {}


# --- SSD-Kennzahlen --------------------------------------------------------

def test_ssd_kennzahlen_aus_statusdatei(tmp_path, monkeypatch):
    datei = tmp_path / "ssd-backup-last.json"
    datei.write_text(json.dumps({
        "stand": "ok", "zeit": "2026-09-04 03:31:00",
        "snapshots": 4, "belegt_kb": 23068672, "frei_kb": 1887436800,
        "fehlende_quellen": 0}), encoding="utf-8")
    monkeypatch.setattr(waechter, "SSD_STATUS", str(datei))
    k = waechter.ssd_kennzahlen()
    assert k["ssd_snapshots"] == 4
    assert k["ssd_belegt_kb"] == 23068672


def test_fehlende_ssd_statusdatei_ergibt_leer(tmp_path, monkeypatch):
    monkeypatch.setattr(waechter, "SSD_STATUS", str(tmp_path / "gibtsnicht"))
    assert waechter.ssd_kennzahlen() == {}


def test_kaputte_ssd_statusdatei_ergibt_leer(tmp_path, monkeypatch):
    datei = tmp_path / "kaputt.json"
    datei.write_text("{kein json", encoding="utf-8")
    monkeypatch.setattr(waechter, "SSD_STATUS", str(datei))
    assert waechter.ssd_kennzahlen() == {}


# --- Vorlauf ---------------------------------------------------------------

def test_vorheriger_stand_ohne_datei(tmp_path, monkeypatch):
    monkeypatch.setattr(waechter, "STATUS", str(tmp_path / "gibtsnicht"))
    assert waechter.vorheriger_stand() == {}


def test_vorheriger_stand_liest_kennzahlen(tmp_path, monkeypatch):
    datei = tmp_path / "waechter-last.json"
    datei.write_text(json.dumps({"stand": "ok",
                                 "kennzahlen": {"nc_used_gb": 19.1}}),
                     encoding="utf-8")
    monkeypatch.setattr(waechter, "STATUS", str(datei))
    assert waechter.vorheriger_stand()["nc_used_gb"] == 19.1


def test_alter_status_ohne_kennzahlen(tmp_path, monkeypatch):
    """Statusdateien aus der Zeit vor dem Bericht haben kein Kennzahlfeld.
    Der erste Lauf danach darf daran nicht scheitern."""
    datei = tmp_path / "alt.json"
    datei.write_text(json.dumps({"stand": "ok", "sicherungen_nas": 15}),
                     encoding="utf-8")
    monkeypatch.setattr(waechter, "STATUS", str(datei))
    assert waechter.vorheriger_stand() == {}


# --- HTML ------------------------------------------------------------------

def test_bericht_ohne_kennzahlen_ist_leer():
    assert waechter.baue_bericht({}, {}) == ""


def test_bericht_nennt_nur_vorhandene_schlagworte():
    """Ein Schlagwort, zu dem es keine Zahl gibt, gehoert nicht in die
    Tabelle — sonst steht dort eine Zeile ohne Aussage."""
    html = waechter.baue_bericht({"snaps": {"claude-code": 15}}, {})
    assert "Claude-Code-Ordner" in html
    assert "NAS-Projektordner" not in html


def test_bericht_zeigt_ssd_belegung():
    html = waechter.baue_bericht(
        {"ssd_snapshots": 4, "ssd_belegt_kb": 23068672,
         "ssd_frei_kb": 1887436800}, {})
    assert "4 Snapshots" in html
    assert "22.0 GB" in html


def test_html_kommt_ohne_kennzahlen_aus():
    """baue_html wird auch aus dem Alarmpfad und aus Tests ohne Kennzahlen
    gerufen — das darf nicht knallen."""
    befund = waechter.pruefung.Befund(ok=True, probleme=[], zeilen=["x"])
    html = waechter.baue_html(befund, 15, alarm=False)
    assert "alles grün" in html
