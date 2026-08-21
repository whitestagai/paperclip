#!/usr/bin/env python3
"""Holt den Ist-Zustand des Link-Detektors und bewertet ihn.

Aufruf: `/usr/bin/python3 waechter.py` -- gibt JSON auf stdout aus.

Zwei Quellen, weil die Kette zwei unabhaengig ausfallende Haelften hat:
- Postgres `link_detektor`, Tabelle `ld.job_queue` (v11-Daemon)
- SQLite `~/.n8n/database.sqlite` (Workflow `Link-Detektor V10.2`, taeglich 01:00)

**Fail-closed:** Eine nicht erreichbare Quelle ist selbst ein Befund, nie ein
stilles "alles in Ordnung". Ein Waechter, der bei kaputter Datenbank Ruhe
meldet, ist schlimmer als keiner -- er erzeugt Vertrauen, das er nicht deckt.

Python 3.9 -- launchd faehrt /usr/bin/python3.
"""
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta

from pruefung import bewerte

DB = os.environ.get("LINK_DETEKTOR_DB", "link_detektor")
N8N_DB = os.path.expanduser(
    os.environ.get("N8N_DB", "~/.n8n/database.sqlite"))
N8N_WORKFLOW = "Link-Detektor V10.2"


class QuelleFehlt(Exception):
    """Eine Datenquelle liess sich nicht lesen."""


def _psql(sql):
    r = subprocess.run(
        ["psql", "-h", "localhost", "-U", os.environ.get("USER", ""), "-d", DB,
         "-A", "-t", "-F", "|", "-c", sql],
        capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise QuelleFehlt("psql %s: %s" % (DB, (r.stderr or "").strip()[:200]))
    return [z for z in r.stdout.strip().splitlines() if z]


def _zeit(roh):
    """Postgres-Zeitstempel ohne Zeitzone einlesen; leer -> None."""
    roh = (roh or "").strip()
    if not roh:
        return None
    roh = roh.split("+")[0].split(".")[0]
    return datetime.strptime(roh, "%Y-%m-%d %H:%M:%S")


def hole_daemon():
    """Kennzahlen des v11-Daemons aus `ld.job_queue`."""
    zeilen = _psql(
        "select coalesce(to_char(max(finished_at) filter (where status='done'),"
        " 'YYYY-MM-DD HH24:MI:SS'), ''),"
        " count(*) filter (where enqueued_at > now() - interval '7 days'),"
        " count(*) filter (where enqueued_at > now() - interval '7 days'"
        "                  and status='error'),"
        " coalesce(to_char(min(started_at) filter (where status='running'),"
        " 'YYYY-MM-DD HH24:MI:SS'), '')"
        " from ld.job_queue;")
    if not zeilen:
        raise QuelleFehlt("ld.job_queue lieferte keine Zeile")
    teile = zeilen[0].split("|")
    return {
        "letzter_done": _zeit(teile[0]),
        "jobs_7t": int(teile[1] or 0),
        "fehler_7t": int(teile[2] or 0),
        "laengster_running": _zeit(teile[3]),
    }


def hole_n8n():
    """Letzter erfolgreicher Lauf des produktiven Workflows."""
    if not os.path.exists(N8N_DB):
        raise QuelleFehlt("n8n-Datenbank fehlt: %s" % N8N_DB)
    try:
        # Nur lesen: n8n haelt die Datei offen, ein Schreibzugriff waere Unfug.
        con = sqlite3.connect("file:%s?mode=ro" % N8N_DB, uri=True, timeout=10)
        try:
            r = con.execute(
                "select max(e.startedAt) from execution_entity e"
                " join workflow_entity w on w.id = e.workflowId"
                " where w.name = ? and e.status = 'success'",
                (N8N_WORKFLOW,)).fetchone()
        finally:
            con.close()
    except sqlite3.Error as e:
        raise QuelleFehlt("n8n-Datenbank: %s" % e)
    if not r or not r[0]:
        return None
    roh = str(r[0]).split(".")[0].replace("T", " ")
    try:
        return datetime.strptime(roh, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        raise QuelleFehlt("n8n-Zeitstempel unlesbar: %r" % r[0])


def main():
    jetzt = datetime.now()
    probleme_vorab = []
    daemon = {"letzter_done": None, "jobs_7t": 0, "fehler_7t": 0,
              "laengster_running": None}
    n8n = None

    try:
        daemon = hole_daemon()
    except (QuelleFehlt, subprocess.SubprocessError, ValueError) as e:
        probleme_vorab.append("Job-Datenbank nicht lesbar: %s" % e)
    try:
        n8n = hole_n8n()
    except (QuelleFehlt, subprocess.SubprocessError, ValueError) as e:
        probleme_vorab.append("n8n-Datenbank nicht lesbar: %s" % e)

    befund = bewerte(jetzt, letzter_n8n_erfolg=n8n, **daemon)

    # Eine unlesbare Quelle ueberstimmt jedes "ok": ohne Daten gibt es keine
    # Entwarnung. Die Bewertung darunter bleibt sichtbar, damit erkennbar
    # ist, was trotzdem geprueft werden konnte.
    probleme = probleme_vorab + list(befund.probleme)
    print(json.dumps({
        "geprueft_am": jetzt.isoformat(timespec="seconds"),
        "ok": not probleme,
        "probleme": probleme,
        "zeilen": befund.zeilen,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # noqa: BLE001 -- der Waechter selbst darf nicht stumm sterben
        print(json.dumps({
            "ok": False,
            "probleme": ["Waechter abgebrochen: %s: %s" % (type(e).__name__, e)],
            "zeilen": [],
        }, ensure_ascii=False, indent=2))
        sys.exit(1)
