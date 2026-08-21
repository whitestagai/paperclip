"""Der Waechter darf bei einer unlesbaren Quelle nie Entwarnung geben.

Ein Waechter, der ohne Daten "ok" meldet, ist schlimmer als keiner: er
erzeugt Vertrauen, das er nicht deckt. Genau so blieb der EBADF-Ausfall
sechs Wochen unentdeckt -- die LaunchAgents zeigten "running".
"""
import json
import subprocess
import sys
from pathlib import Path

HIER = Path(__file__).parent


def _lauf(env_zusatz):
    import os
    env = dict(os.environ)
    env.update(env_zusatz)
    r = subprocess.run([sys.executable, str(HIER / "waechter.py")],
                       capture_output=True, text=True, env=env, timeout=60)
    return json.loads(r.stdout), r.returncode


def test_unlesbare_job_datenbank_ist_ein_befund():
    doc, code = _lauf({"LINK_DETEKTOR_DB": "gibt-es-nicht-xyz"})
    assert doc["ok"] is False
    assert any("Job-Datenbank nicht lesbar" in p for p in doc["probleme"])
    assert code == 0, "der Waechter meldet den Ausfall, statt selbst zu sterben"


def test_fehlende_n8n_datenbank_ist_ein_befund():
    doc, _ = _lauf({"N8N_DB": "/tmp/gibt-es-nicht-xyz.sqlite"})
    assert doc["ok"] is False
    assert any("n8n-Datenbank nicht lesbar" in p for p in doc["probleme"])


def test_beide_quellen_weg_nennt_beide():
    doc, _ = _lauf({"LINK_DETEKTOR_DB": "gibt-es-nicht-xyz",
                    "N8N_DB": "/tmp/gibt-es-nicht-xyz.sqlite"})
    assert doc["ok"] is False
    assert len(doc["probleme"]) >= 2


def test_der_gesunde_lauf_gibt_zeilen_zum_zitieren():
    # Gegen die echten Quellen: der Agent soll Zahlen kopieren, nicht tippen.
    doc, _ = _lauf({})
    assert doc["zeilen"], "auch ohne Befund wird berichtet"
    assert "geprueft_am" in doc
