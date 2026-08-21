"""Bewertung des Link-Detektor-Betriebs.

Der Ernstfall ist belegt: der v11-Daemon verarbeitete vom 21.06. bis zum
30.07.2026 SECHS WOCHEN lang keinen einzigen Job (45.000 Fehl-Jobs durch
`spawn EBADF`) -- und niemand merkte es, weil beide LaunchAgents brav
"running" zeigten und die Logs niemand liest. Genau diese Faelle muessen
hier pruefbar sein, denn im Betrieb treten sie hoffentlich nie ein.

Python 3.9 -- launchd faehrt /usr/bin/python3.
"""
from datetime import datetime, timedelta

from pruefung import bewerte

JETZT = datetime(2026, 8, 21, 8, 0)


def _lage(**kw):
    """Ein gesunder Betrieb; die Tests veraendern jeweils einen Aspekt."""
    basis = dict(
        letzter_done=JETZT - timedelta(minutes=30),
        jobs_7t=420,
        fehler_7t=3,
        laengster_running=None,
        letzter_n8n_erfolg=JETZT - timedelta(hours=7),
    )
    basis.update(kw)
    return bewerte(JETZT, **basis)


def test_gesunder_betrieb_meldet_nichts():
    b = _lage()
    assert b.ok is True
    assert b.probleme == []


def test_der_ebadf_fall_wird_erkannt():
    # Die Lage vom 30.07.: Jobs laufen rein, keiner wird fertig.
    b = _lage(letzter_done=JETZT - timedelta(days=42), jobs_7t=900, fehler_7t=900)
    assert b.ok is False
    assert any("Stillstand" in p for p in b.probleme)


def test_stillstand_erst_nach_sieben_tagen():
    # Der Watcher stellt nur bei Vault-Aenderungen ein. Eine ruhige Woche
    # (Urlaub, keine neuen Notizen) ist kein Defekt.
    assert _lage(letzter_done=JETZT - timedelta(days=6, hours=20)).ok is True
    assert _lage(letzter_done=JETZT - timedelta(days=7, hours=1)).ok is False


def test_gar_kein_done_job_ist_ein_befund():
    b = _lage(letzter_done=None)
    assert b.ok is False
    assert any("Stillstand" in p for p in b.probleme)


def test_hohe_fehlerquote_schlaegt_an():
    b = _lage(jobs_7t=100, fehler_7t=25)
    assert b.ok is False
    assert any("Fehlerquote" in p for p in b.probleme)


def test_geloeschte_dateien_sind_kein_alarm():
    # ENOENT-Rauschen: eine Notiz wird umbenannt, bevor ihr Job laeuft.
    # Real gemessen: 19 von 19.595 Jobs, also 0,1 Prozent.
    assert _lage(jobs_7t=500, fehler_7t=19).ok is True


def test_wenige_jobs_erzeugen_keine_quotenpanik():
    # Bei drei Jobs in der Woche waere ein einzelner Fehler schon 33 Prozent.
    # Unter der Mindestmenge zaehlt die Quote nicht.
    assert _lage(jobs_7t=3, fehler_7t=1).ok is True


def test_haengender_job_wird_gemeldet():
    # Ein Job dauert 70 bis 90 Sekunden. Zwei Stunden sind das Achtzigfache.
    b = _lage(laengster_running=JETZT - timedelta(hours=3))
    assert b.ok is False
    assert any("running" in p for p in b.probleme)


def test_frisch_laufender_job_ist_normal():
    assert _lage(laengster_running=JETZT - timedelta(minutes=2)).ok is True


def test_ausgefallener_n8n_workflow_wird_gemeldet():
    # V10.2 laeuft taeglich um 01:00; 48 Stunden decken einen verschobenen
    # Lauf ab, verschlucken aber keine ausgefallene Nacht.
    b = _lage(letzter_n8n_erfolg=JETZT - timedelta(hours=50))
    assert b.ok is False
    assert any("V10.2" in p for p in b.probleme)


def test_nie_gelaufener_n8n_workflow_wird_gemeldet():
    b = _lage(letzter_n8n_erfolg=None)
    assert b.ok is False
    assert any("V10.2" in p for p in b.probleme)


def test_mehrere_probleme_werden_alle_genannt():
    b = _lage(letzter_done=None, letzter_n8n_erfolg=None)
    assert len(b.probleme) == 2


def test_die_zeilen_tragen_immer_die_zahlen():
    # Der Agent uebernimmt diese Zeilen woertlich, statt Zahlen zu tippen --
    # dieselbe Konstruktion wie `evidence_line` beim LLM-Advisor.
    b = _lage(jobs_7t=420, fehler_7t=3)
    text = " ".join(b.zeilen)
    assert "420" in text and "3" in text
    assert b.zeilen, "auch der gesunde Fall wird berichtet, nicht nur gemeldet"
