#!/usr/bin/env python3
"""Vault-Maintainer Heartbeat-Check — deterministische Prüfung der nächtlichen Vault-Pflege.

Wird vom n8n-Betriebsingenieur in der Routine „Vault-Maintainer Heartbeat-Check"
genau einmal aufgerufen. Das Skript prüft, kommentiert und setzt den Status selbst;
der Agent gibt nur die letzte Zeile wieder.

Warum ein Skript statt Anweisungen: Der Agent läuft über den PII-Proxy, und der
pseudonymisiert Teile von UUIDs. Am 29.10.2026 tippte das Modell die Company-ID als
`9cebf3cf-efe8-4597-a400-f380f89fa87` — die API antwortete mit „Agent key cannot
access another company", und der Check meldete „blocked". Hier fasst kein Modell
eine ID an. Dazu kommt ein Kontext, der schon beim Start bei ~165k Tokens steht:
jeder eingesparte Zug zählt.

Umgebung (setzt der claude_local-Adapter): PAPERCLIP_API_URL, PAPERCLIP_API_KEY,
PAPERCLIP_TASK_ID, PAPERCLIP_RUN_ID.
"""
import json
import os
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

COMPANY = "9cebf3cf-efe8-4597-a400-f06488900a87"
VAULT_MAINTAINER = "3067ea1d-5050-4032-aff5-1f759f544160"
PFLEGE_ROUTINE = "4ef43254-ad97-46c7-9a93-f39d2a5cfad5"
DIESE_ROUTINE = "972e3c2c-7052-4fa7-9868-c8f86c8773f3"
STATUS_JSON = Path.home() / ".paperclip/logs/vault-tagger-last.json"
TAGGER_LOG = Path.home() / ".paperclip/logs/vault-tagger.log"
BERLIN = ZoneInfo("Europe/Berlin")
OFFEN = "todo,in_progress,in_review,blocked"

API = os.environ.get("PAPERCLIP_API_URL", "http://127.0.0.1:3100").rstrip("/")
KEY = os.environ.get("PAPERCLIP_API_KEY", "")
TASK = os.environ.get("PAPERCLIP_TASK_ID", "")
RUN = os.environ.get("PAPERCLIP_RUN_ID", "")


def api(method, path, body=None):
    headers = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}
    if RUN:
        headers["X-Paperclip-Run-Id"] = RUN
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as res:
        raw = res.read().decode()
    return json.loads(raw) if raw.strip() else None


def berlin_datum(utc_text):
    return datetime.fromisoformat(utc_text.replace("Z", "+00:00")).astimezone(BERLIN).date()


def pruefe_tagger(heute):
    """A und B: Status-JSON des launchd-Dienstes de.whitestag.vault-tagger."""
    if not STATUS_JSON.exists():
        return ("A", False, f"`{STATUS_JSON}` fehlt"), ("B", False, "kein Lauf")
    st = json.loads(STATUS_JSON.read_text(encoding="utf-8"))
    ts, code, fertig = st.get("timestamp", ""), st.get("exit_code"), st.get("fertig", "")
    a_ok = bool(ts) and berlin_datum(ts) == heute and code == 0
    b_ok = "fail=0" in fertig
    return (
        ("A", a_ok, f"timestamp `{ts}` (Berlin {berlin_datum(ts) if ts else '?'}), exit_code `{code}`"),
        ("B", b_ok, f"`{fertig or 'keine Fertig-Zeile'}`"),
    )


def pruefe_pflege_issue(heute):
    """C: jüngstes Issue der Routine „Obsidian-Vault Frontmatter-Pflege"."""
    issues = api("GET", f"/api/companies/{COMPANY}/issues?originKind=routine_execution&originId={PFLEGE_ROUTINE}&limit=1") or []
    if not issues:
        return ("C", False, "kein Issue der Frontmatter-Pflege gefunden")
    i = issues[0]
    tag = berlin_datum(i["createdAt"])
    ok = tag == heute and i["status"] in ("done", "in_review")
    return ("C", ok, f"{i['identifier']} `{i['status']}`, angelegt {tag}")


def pruefe_agent():
    """D: Agentenstatus des Vault-Maintainers."""
    a = api("GET", f"/api/agents/{VAULT_MAINTAINER}")
    return ("D", a.get("status") != "error", f"Vault-Maintainer `{a.get('status')}`")


def raeume_alte_laeufe():
    offen = api("GET", f"/api/companies/{COMPANY}/issues?originKind=routine_execution&originId={DIESE_ROUTINE}&status={OFFEN}") or []
    alte = [i for i in offen if i["id"] != TASK]
    for i in alte:
        # ohne comment — ein Kommentar würde den Assignee erneut wecken
        api("PATCH", f"/api/issues/{i['id']}", {"status": "cancelled"})
    return [i["identifier"] for i in alte]


def tagger_log_ende(n=20):
    try:
        out = subprocess.run(["tail", "-n", str(n), str(TAGGER_LOG)], capture_output=True, text=True, timeout=10)
        return out.stdout.rstrip()
    except Exception as e:  # nur Zusatzinfo, darf die Prüfung nicht kippen
        return f"(Log nicht lesbar: {e})"


HINWEISE = {
    "A": "`launchctl list de.whitestag.vault-tagger` und das Tagger-Log prüfen.",
    "B": "Fehlgeschlagene Dateien im Tagger-Log (`FEHLER`) ansehen.",
    "C": "Das Issue der Frontmatter-Pflege ansehen — der Vault-Maintainer hat nicht sauber abgeschlossen.",
    "D": f"Board: `POST /api/agents/{VAULT_MAINTAINER}/resume`.",
}


def main():
    if not KEY or not TASK:
        print("ERGEBNIS=fehler PAPERCLIP_API_KEY oder PAPERCLIP_TASK_ID fehlt — nur im Routine-Lauf aufrufen.")
        return 2

    heute = datetime.now(BERLIN).date()
    abgeraeumt = raeume_alte_laeufe()
    befunde = [*pruefe_tagger(heute), pruefe_pflege_issue(heute), pruefe_agent()]
    alles_ok = all(ok for _, ok, _ in befunde)
    status = "done" if alles_ok else "blocked"

    zeilen = [f"## Heartbeat-Check {heute} — {'OK' if alles_ok else 'NICHT OK'}", "",
              "| # | Prüfung | Wert | Ergebnis |", "|---|---|---|---|"]
    namen = {"A": "Tagger-Dienst", "B": "Tagger-Ergebnis", "C": "Pflege-Issue", "D": "Agent"}
    for k, ok, wert in befunde:
        zeilen.append(f"| {k} | {namen[k]} | {wert} | {'OK' if ok else '**NICHT OK**'} |")
    if not alles_ok:
        zeilen += ["", "**Zu prüfen:**"] + [f"- {k}: {HINWEISE[k]}" for k, ok, _ in befunde if not ok]
        if not befunde[0][1] or not befunde[1][1]:
            zeilen += ["", "Tagger-Log, letzte 20 Zeilen:", "```", tagger_log_ende(), "```"]
    if abgeraeumt:
        zeilen += ["", f"Alte offene Läufe abgebrochen: {', '.join(abgeraeumt)}"]
    zeilen += ["", "_Erzeugt von `~/.paperclip/scripts/vault-heartbeat-check/check.py`._"]

    api("POST", f"/api/issues/{TASK}/comments", {"body": "\n".join(zeilen)})
    api("PATCH", f"/api/issues/{TASK}", {"status": status})
    print(f"ERGEBNIS={status} " + " ".join(f"{k}={'ok' if ok else 'NICHT_OK'}" for k, ok, _ in befunde))
    return 0


if __name__ == "__main__":
    sys.exit(main())
