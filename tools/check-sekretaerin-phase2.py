#!/usr/bin/env python3
"""Nachkontrolle der Phase-2-Umstellung der Sekretärin (2026-07-20).

Prüft den jüngsten Routine-Lauf gegen die vier neuen Regeln:
  1. Abschluss auf in_review (nicht done), Assignee = Walter
  2. Kein Doppel-Posten (keine zwei Triage-Tabellen im selben Issue)
  3. Kein max_iterations/llm_error-Abbruch mehr
  4. Bei erkannter Störung: Subtask statt bloßer Empfehlung

Read-only. Aufruf: python3 check-sekretaerin-phase2.py [--since YYYY-MM-DD]
"""
import argparse
import subprocess
import sys
from datetime import date, timedelta

AGENT = "e24b8d9d-143e-4141-b413-4361aa618771"
WALTER = "18r34Ghx5N0LHRptMCT6Fp1WaoGqhvc9"
PSQL = ["/opt/homebrew/bin/psql", "-h", "localhost", "-p", "54329", "-U", "paperclip",
        "-d", "paperclip", "-At", "-F", "\x1f"]


def q(sql):
    r = subprocess.run(PSQL + ["-c", sql], capture_output=True, text=True,
                       env={"PGPASSWORD": "paperclip", "PATH": "/usr/bin:/bin:/usr/local/bin"})
    if r.returncode != 0:
        sys.exit(f"psql-Fehler: {r.stderr.strip()}")
    return [ln.split("\x1f") for ln in r.stdout.strip().splitlines() if ln]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--since", default=str(date.today() - timedelta(days=1)))
    a = p.parse_args()

    rows = q(f"""
        SELECT identifier, title, status,
               coalesce(assignee_user_id,''), coalesce(assignee_agent_id::text,''), id
        FROM issues
        WHERE (assignee_agent_id='{AGENT}' OR assignee_user_id='{WALTER}')
          AND created_at >= '{a.since}'
        ORDER BY created_at DESC LIMIT 20;""")

    rows = [r for r in rows if "Triage" in r[1] or "Termin" in r[1] or "Kontakte" in r[1]]
    if not rows:
        print(f"Keine Routine-Issues seit {a.since} gefunden.")
        return

    ok = True
    for ident, title, status, auser, aagent, iid in rows[:5]:
        print(f"\n=== {ident} — {title}")
        print(f"    Status: {status}")

        # Regel 1
        if status == "done":
            print("    [FEHLER] auf 'done' geschlossen — muss 'in_review' sein"); ok = False
        elif status == "in_review":
            print("    [OK] in_review")
            if auser != WALTER:
                print(f"    [FEHLER] assigneeUserId='{auser}' statt Walter"); ok = False
            if aagent:
                print(f"    [WARN] assigneeAgentId noch gesetzt ({aagent[:8]}…)")
        elif status == "blocked":
            print("    [WARN] blocked — Grund unten prüfen")

        # Regel 2: Doppel-Posten
        cs = q(f"""SELECT author_type, left(body,4000) FROM issue_comments
                   WHERE issue_id='{iid}' ORDER BY created_at;""")
        tri = [c for c in cs if len(c) > 1 and "## Triage" in c[1]]
        if len(tri) > 1:
            print(f"    [FEHLER] {len(tri)} Triage-Tabellen im selben Issue (Doppel-Posten)"); ok = False
        elif tri:
            print("    [OK] genau eine Triage-Tabelle")

        # Regel 3: Abbrüche
        for c in cs:
            if len(c) > 1 and c[0] == "system" and ("max_iterations" in c[1] or "llm_error" in c[1]):
                kind = "max_iterations" if "max_iterations" in c[1] else "llm_error"
                print(f"    [FEHLER] Abbruch: {kind}"); ok = False

        # Regel 4: Subtasks
        kids = q(f"""SELECT identifier, status, title FROM issues
                     WHERE parent_id='{iid}';""")
        # Auto-Recovery-Subtasks von Paperclip zaehlen nicht als Delegation
        own = [k for k in kids if not k[2].startswith("Recover stalled issue")]
        auto = len(kids) - len(own)
        for k in own:
            print(f"    [OK] Delegation: {k[0]} ({k[1]}) — {k[2][:50]}")
        if auto:
            print(f"    [WARN] {auto} Auto-Recovery-Subtask(s) — keine eigene Delegation")
        if not own:
            print("    [INFO] keine Delegation (nur relevant, wenn eine Störung erkannt wurde)")

    print("\n" + ("ERGEBNIS: alle geprüften Regeln eingehalten."
                  if ok else "ERGEBNIS: Regelverstoesse gefunden — siehe [FEHLER] oben."))


if __name__ == "__main__":
    main()
