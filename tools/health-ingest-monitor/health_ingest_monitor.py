#!/usr/bin/env python3
"""health_ingest_monitor.py — Frische-Wächter über den health-ingest-Datenpfad.

Motivation
----------
WHI-2559 blieb tagelang als Geister-Issue offen und CEO/CTO haben die (längst per
V10 gefixte) V9-Diagnose immer wieder per Mail an Walter wiederholt. Grund: die
lokalen LLM-Agenten können weder `psql` noch iCloud prüfen — sie kennen nur den
veralteten Issue-Text und *raten*. Dieser Wächter schließt genau diese Lücke:
er prüft den ECHTEN Zustand (Ground Truth) und eskaliert NUR bei tatsächlichem
Datenausfall — mit belegter Layer-Attribution, sodass kein Agent mehr raten muss.

Defense-in-Depth-Layer (in Fließrichtung):
  SOURCE          iPhone/Health-Export-App legt die Tagesdatei in iCloud ab
  MATERIALIZATION keep-warm.sh materialisiert dataless iCloud-Platzhalter lokal
  INGEST          n8n `health-ingest` liest + schreibt nach health.paperclip_health

Entscheidung: definitiver "CHO hat Daten"-Beleg = health_daily-Zeile für GESTERN.
Fehlt sie, wird der zuerst versagende Layer bestimmt und EIN idempotentes
Paperclip-Issue (pro Ausfall-Datum) an den n8n-Recovery-Agenten erstellt.
Erholt sich der Pfad (grün) und ein Issue ist offen -> wird es automatisch
als done geschlossen. Kein Mail-Spam, keine Rate-Schleife.

Read-only gegenüber iCloud + Postgres. Läuft via launchd
`de.whitestag.health-ingest-monitor` täglich.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import date, datetime, timedelta

# paperclip_client liegt im Eltern-Verzeichnis (~/.paperclip/scripts/)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paperclip_client as pc  # noqa: E402

HOME = os.path.expanduser("~")

# --- Konstanten ---------------------------------------------------------------
HEALTH_DIR = os.path.join(
    HOME,
    "Library/Mobile Documents/iCloud~com~ifunography~HealthExport"
    "/Documents/Daily Export Gesundheit",
)
FILE_RE = re.compile(r"^Gesundheitsdaten-(\d{4}-\d{2}-\d{2})\.json$")
RECENT_DAYS = 4  # Fenster, das health-ingest V10 aktiv liest

DB_HOST = "127.0.0.1"
DB_PORT = "5432"
DB_NAME = "health"
SCHEMA = "paperclip_health"
MAX_INGEST_AGE_H = 30  # frischestes Sample darf höchstens so alt sein

COMPANY_ID = "9cebf3cf-efe8-4597-a400-f06488900a87"  # WHITESTAG
RECOVERY_AGENT_ID = os.environ.get(
    "HEALTH_RECOVERY_AGENT_ID", "dfa8d0e2-d48a-4342-82c2-f7cf6de9d562"
)  # n8n-Betriebsingenieur (claude_local, unter CTO)
PCP_BASE = os.environ.get("PCP_API", pc.DEFAULT_BASE)

STATE_PATH = os.path.join(
    HOME, ".paperclip/instances/default/state/health-ingest-monitor.json"
)
LOG_PATH = os.path.join(
    HOME, ".paperclip/instances/default/logs/health-ingest-monitor.log"
)

PSQL = "/opt/homebrew/bin/psql"


# --- Logging ------------------------------------------------------------------
def log(level: str, msg: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')} [{level}] {msg}"
    print(line, file=sys.stderr if level == "ERROR" else sys.stdout)
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, "a") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


# --- State --------------------------------------------------------------------
def load_state(path: str = STATE_PATH) -> dict:
    try:
        with open(path) as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state: dict, path: str = STATE_PATH) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(state, fh, indent=2)
    os.replace(tmp, path)


# --- iCloud-Quelle scannen (IO) ----------------------------------------------
def is_dataless(fp: str) -> bool:
    """True, wenn die Datei ein nicht-materialisierter iCloud-Platzhalter ist."""
    try:
        out = subprocess.run(
            ["ls", "-ldO", fp], capture_output=True, text=True, timeout=15
        ).stdout
        return "dataless" in out
    except (subprocess.SubprocessError, OSError):
        return False


def scan_source(directory: str = HEALTH_DIR, today: date | None = None) -> dict:
    today = today or date.today()
    cutoff = today - timedelta(days=RECENT_DAYS)
    res = {
        "dir_exists": os.path.isdir(directory),
        "newest_date": None,      # str YYYY-MM-DD oder None
        "recent_files": [],       # [(date_str, path)] im RECENT_DAYS-Fenster
        "dataless_recent": [],    # Pfade dataless im Fenster
        "total_files": 0,
    }
    if not res["dir_exists"]:
        return res
    try:
        names = os.listdir(directory)
    except OSError:
        res["dir_exists"] = False
        return res
    newest = None
    for name in names:
        m = FILE_RE.match(name)
        if not m:
            continue
        res["total_files"] += 1
        dstr = m.group(1)
        if newest is None or dstr > newest:
            newest = dstr
        try:
            d = date.fromisoformat(dstr)
        except ValueError:
            continue
        if d >= cutoff:
            fp = os.path.join(directory, name)
            res["recent_files"].append((dstr, fp))
            if is_dataless(fp):
                res["dataless_recent"].append(fp)
    res["newest_date"] = newest
    return res


# --- Postgres abfragen (IO) ---------------------------------------------------
def _psql(sql: str) -> str:
    """Führt SQL read-only aus, gibt Roh-stdout (tab-getrennt) zurück."""
    proc = subprocess.run(
        [PSQL, "-h", DB_HOST, "-p", DB_PORT, "-d", DB_NAME, "-tAF", "\t", "-c", sql],
        capture_output=True, text=True, timeout=30,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"psql rc={proc.returncode}: {proc.stderr.strip()}")
    return proc.stdout.strip()


def query_db() -> dict:
    daily_max = _psql(f"SELECT MAX(date)::text FROM {SCHEMA}.health_daily;")
    max_ing = _psql(
        f"SELECT COALESCE(MAX(ingested_at)::text,'') FROM {SCHEMA}.health_samples;"
    )
    runs = _psql(
        "SELECT date::text||'\t'||status||'\t'||COALESCE(samples_written::text,'0') "
        f"FROM {SCHEMA}.health_ingest_runs ORDER BY date DESC LIMIT 6;"
    )
    latest_runs = []
    for ln in runs.splitlines():
        parts = ln.split("\t")
        if len(parts) >= 3:
            latest_runs.append(
                {"date": parts[0], "status": parts[1], "samples": int(parts[2] or 0)}
            )
    return {
        "daily_max_date": daily_max or None,
        "max_ingested_at": max_ing or None,
        "latest_runs": latest_runs,
    }


def ingested_age_hours(max_ingested_at: str | None, now: datetime | None = None) -> float | None:
    if not max_ingested_at:
        return None
    now = now or datetime.now()
    try:
        # Postgres liefert z.B. "2026-07-19 00:00:24.186856+02"
        s = max_ingested_at.strip()
        # tz-offset abschneiden für naive Vergleich (server-lokal)
        s = re.sub(r"[+-]\d{2}(:?\d{2})?$", "", s).strip()
        ts = datetime.fromisoformat(s)
        return (now - ts).total_seconds() / 3600.0
    except ValueError:
        return None


# --- Entscheidung (reine Funktion) -------------------------------------------
def classify(source: dict, db: dict, today: date | None = None) -> dict:
    """Bestimmt state (green/red) und bei red den zuerst versagenden Layer.

    Definitiver "CHO hat Daten"-Beleg: health_daily-Zeile für GESTERN vorhanden.
    """
    today = today or date.today()
    yesterday = (today - timedelta(days=1)).isoformat()
    today_s = today.isoformat()

    daily_max = db.get("daily_max_date")
    has_yesterday_daily = daily_max is not None and daily_max >= yesterday

    if has_yesterday_daily:
        return {
            "state": "green",
            "layer": None,
            "target_date": yesterday,
            "reason": f"health_daily reicht bis {daily_max} (>= gestern {yesterday}).",
        }

    # RED — Layer bestimmen (erster versagender Schritt in Fließrichtung).
    newest = source.get("newest_date")
    has_source = newest is not None and newest >= yesterday
    dataless = source.get("dataless_recent") or []

    if not source.get("dir_exists"):
        layer = "SOURCE"
        reason = f"iCloud-Export-Verzeichnis nicht lesbar: {HEALTH_DIR}"
    elif not has_source:
        layer = "SOURCE"
        reason = (
            f"Keine Tagesdatei für gestern ({yesterday}). Neueste Datei: "
            f"{newest or 'keine'}. -> Health-Export-App/iPhone liefert nicht "
            f"(KEIN Workflow-Bug)."
        )
    elif dataless:
        layer = "MATERIALIZATION"
        reason = (
            f"Quelldatei für gestern vorhanden, aber {len(dataless)} Datei(en) im "
            f"{RECENT_DAYS}-Tage-Fenster sind dataless (nicht materialisiert). "
            f"keep-warm.sh greift nicht."
        )
    else:
        layer = "INGEST"
        reason = (
            f"Quelldatei für gestern ({yesterday}) vorhanden und materialisiert, "
            f"aber health_daily reicht nur bis {daily_max or 'NULL'}. "
            f"n8n health-ingest schreibt nicht in die DB."
        )

    return {
        "state": "red",
        "layer": layer,
        "target_date": yesterday,
        "reason": reason,
    }


def build_issue(verdict: dict, source: dict, db: dict) -> tuple[str, str]:
    layer = verdict["layer"]
    tgt = verdict["target_date"]
    owner_hint = {
        "SOURCE": "Datenquelle (iPhone / Health-Export-App). Kein n8n-/DB-Bug — "
                  "ggf. Walter informieren, aber erst nach Verifikation.",
        "MATERIALIZATION": "iCloud-Materialisierung auf der Mac Studio "
                           "(launchd `de.whitestag.icloud-health-keepwarm`).",
        "INGEST": "n8n-Workflow `health-ingest V10` (0wu9MeDHTxTgIwmo) bzw. "
                  "Ziel-DB `health.paperclip_health`.",
    }[layer]
    title = f"health-ingest Frische-Ausfall ({layer}) — keine Daten für {tgt}"
    runs = db.get("latest_runs") or []
    runs_str = "  ".join(
        f"{r['date']}:{r['status']}/{r['samples']}" for r in runs
    ) or "(keine)"
    lines = [
        "## Automatischer Frische-Wächter — verifizierter Ausfall",
        "",
        f"**Zuerst versagender Layer:** `{layer}`",
        f"**Betroffenes Datum:** {tgt}",
        f"**Zuständig:** {owner_hint}",
        "",
        f"**Befund:** {verdict['reason']}",
        "",
        "**Ground-Truth-Evidenz (gemessen auf der Mac Studio):**",
        f"- health_daily max date: `{db.get('daily_max_date')}`",
        f"- health_samples max ingested_at: `{db.get('max_ingested_at')}`",
        f"- letzte ingest_runs (date:status/samples): {runs_str}",
        f"- Quell-Verzeichnis lesbar: {source.get('dir_exists')}, "
        f"neueste Datei: `{source.get('newest_date')}`, "
        f"Dateien im {RECENT_DAYS}-Tage-Fenster: {len(source.get('recent_files') or [])}, "
        f"davon dataless: {len(source.get('dataless_recent') or [])}",
        "",
        "_Dies ist ein **verifizierter** Ausfall (nicht geraten). Bitte den oben "
        "genannten Layer gezielt beheben. Nach Behebung schließt der Wächter dieses "
        "Issue automatisch, sobald wieder Tagesdaten fließen._",
    ]
    return title, "\n".join(lines)


# --- Paperclip PATCH-Helfer (schließt bei Erholung) --------------------------
def update_issue_done(base: str, token: str, issue_id: str, comment: str) -> None:
    import urllib.error
    import urllib.request

    req = urllib.request.Request(
        f"{base}/api/issues/{issue_id}",
        data=json.dumps({"status": "done", "comment": comment}).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {token}"},
        method="PATCH",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            r.read()
    except urllib.error.HTTPError as e:
        raise pc.ApiError(f"HTTP {e.code} PATCH {issue_id}") from e
    except Exception as e:  # noqa: BLE001
        raise pc.ApiError(f"PATCH failed {issue_id}: {e}") from e


# --- Orchestrierung -----------------------------------------------------------
def run(dry_run: bool = False) -> int:
    log("INFO", "run start")
    source = scan_source()
    try:
        db = query_db()
    except (RuntimeError, OSError) as e:
        log("ERROR", f"DB-Abfrage fehlgeschlagen: {e}")
        return 1

    verdict = classify(source, db)
    age = ingested_age_hours(db.get("max_ingested_at"))
    log("INFO", f"state={verdict['state']} layer={verdict['layer']} "
                f"daily_max={db.get('daily_max_date')} ingest_age_h="
                f"{'%.1f' % age if age is not None else 'n/a'} :: {verdict['reason']}")

    state = load_state()
    open_issue = state.get("open_issue_id")
    token = os.environ.get("PCP_TOKEN", "") or pc.load_token()

    if verdict["state"] == "green":
        # Erholung: offenes Geister-Issue automatisch schließen.
        if open_issue and not dry_run:
            comment = (
                "## Frische-Wächter: Datenpfad erholt\n\n"
                f"health_daily reicht wieder bis `{db.get('daily_max_date')}` "
                f"(>= gestern). Ausfall behoben — Issue automatisch geschlossen.\n"
            )
            try:
                update_issue_done(PCP_BASE, token, open_issue, comment)
                log("INFO", f"offenes Issue {open_issue} als done geschlossen (Erholung)")
            except pc.ApiError as e:
                log("ERROR", f"Auto-Close fehlgeschlagen: {e}")
        save_state({"last_state": "green", "open_issue_id": None,
                    "stale_date": None, "layer": None})
        return 0

    # RED
    stale_date = verdict["target_date"]
    already = (state.get("last_state") == "red"
               and state.get("stale_date") == stale_date
               and state.get("layer") == verdict["layer"]
               and open_issue)
    if already:
        log("INFO", f"Ausfall bereits gemeldet (Issue {open_issue}, {stale_date}, "
                    f"{verdict['layer']}) — kein Duplikat.")
        return 0

    title, desc = build_issue(verdict, source, db)
    if dry_run:
        log("INFO", f"[dry-run] würde Issue anlegen: {title}")
        print(title)
        print(desc)
        return 0

    try:
        issue_id = pc.create_issue(
            PCP_BASE, token, COMPANY_ID,
            title=title, description=desc,
            assignee_agent_id=RECOVERY_AGENT_ID or None,
            priority="high",
        )
    except pc.ApiError as e:
        log("ERROR", f"Issue-Erstellung fehlgeschlagen: {e}")
        return 1
    log("INFO", f"Issue {issue_id} erstellt ({verdict['layer']}, {stale_date})")
    save_state({"last_state": "red", "open_issue_id": issue_id,
                "stale_date": stale_date, "layer": verdict["layer"]})
    return 0


def _parse_args(argv):
    p = argparse.ArgumentParser(description="health-ingest Frische-Wächter")
    p.add_argument("--once", action="store_true", help="Ein Durchlauf (Default)")
    p.add_argument("--dry-run", action="store_true",
                   help="Prüfen + loggen, nichts in Paperclip schreiben")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    return run(dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
