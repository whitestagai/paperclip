#!/usr/bin/env python3
"""Wirksamkeitskontrolle: was ist aus den 200 re-gestarteten (blocked->todo) Issues
geworden? Baseline = Zeitpunkt des Flips. Mailt das Ergebnis an Walter via n8n-Mailhub.
"""
import subprocess, json, urllib.request, os, sys

DIR = os.path.dirname(os.path.abspath(__file__))
IDS = [l.split(",")[0] for l in open(f"{DIR}/restarted-ids.csv") if l.strip()]
BASELINE = open(f"{DIR}/baseline.txt").read().strip()

WEBHOOK = "http://127.0.0.1:5678/webhook/mailhub/send"
def _load_mailhub_secret() -> str:
    """Secret aus der zentralen Secrets-Datei lesen (Rotation 03.08.2026, nicht mehr im Code)."""
    path = os.path.expanduser("~/.paperclip/instances/default/secrets/mailhub.env")
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("MAILHUB_SECRET="):
                return line.split("=", 1)[1].strip().strip('"')
    raise RuntimeError("MAILHUB_SECRET nicht gefunden in " + path)


SECRET = _load_mailhub_secret()
FROM, TO = "cto@whitestag.ai", "ws@whitestag.ai"

def q(sql):
    env = dict(os.environ, PGPASSWORD="paperclip")
    out = subprocess.run(["psql","-h","127.0.0.1","-p","54329","-U","paperclip","-d","paperclip",
                          "-tA","-F","\t","-c",sql], capture_output=True, text=True, env=env).stdout
    return [line.split("\t") for line in out.splitlines() if line.strip()]

idlist = ",".join(f"'{i}'" for i in IDS)

# 1) aktueller Status der 200
status_rows = q(f"SELECT status, count(*) FROM issues WHERE id IN ({idlist}) GROUP BY 1")
status = {r[0]: int(r[1]) for r in status_rows}

# 2) je Company: done vs. wieder blocked
comp_rows = q(f"""SELECT co.name, i.status, count(*)
  FROM issues i JOIN companies co ON co.id=i.company_id
  WHERE i.id IN ({idlist}) GROUP BY 1,2 ORDER BY 1,2""")

# 3) bewegt seit Baseline?
moved = q(f"SELECT count(*) FROM issues WHERE id IN ({idlist}) AND updated_at > '{BASELINE}'")
moved_n = int(moved[0][0]) if moved else 0

# 4) fleet-weite max_iterations seit Baseline (Loop wieder da?)
loops = q(f"""SELECT count(*) FROM heartbeat_runs
  WHERE error ILIKE '%iteration%' AND created_at > '{BASELINE}'""")
loops_n = int(loops[0][0]) if loops else 0
ram = q(f"""SELECT count(*) FROM heartbeat_runs
  WHERE error ILIKE '%insufficient system resources%' AND created_at > '{BASELINE}'""")
ram_n = int(ram[0][0]) if ram else 0

total = len(IDS)
done = status.get("done",0); inprog = status.get("in_progress",0)+status.get("in_review",0)
todo = status.get("todo",0); blocked = status.get("blocked",0); canc = status.get("cancelled",0)

def pct(n): return f"{100*n/total:.0f}%"

rows_html = "".join(
    f"<tr><td>{c}</td><td>{s}</td><td style='text-align:right'>{n}</td></tr>"
    for c,s,n in comp_rows)

html = f"""<div style="font-family:-apple-system,Segoe UI,sans-serif;max-width:640px;color:#1a1a1a">
<h2 style="border-bottom:2px solid #0066cc;padding-bottom:6px">Wirksamkeitskontrolle: 200 re-gestartete Issues</h2>
<p style="color:#666">Baseline (Flip blocked&rarr;todo): {BASELINE[:19]} &middot; Auswertung jetzt.</p>
<table style="border-collapse:collapse;width:100%;margin:12px 0">
<tr style="background:#f0f0f0"><th style="text-align:left;padding:6px">Ausgang</th><th style="text-align:right;padding:6px">Anzahl</th><th style="text-align:right;padding:6px">Anteil</th></tr>
<tr><td style="padding:6px">✅ done (durchgelaufen)</td><td style="text-align:right">{done}</td><td style="text-align:right">{pct(done)}</td></tr>
<tr><td style="padding:6px">🔧 in Arbeit (in_progress/review)</td><td style="text-align:right">{inprog}</td><td style="text-align:right">{pct(inprog)}</td></tr>
<tr><td style="padding:6px">⏳ noch todo (nicht aufgegriffen)</td><td style="text-align:right">{todo}</td><td style="text-align:right">{pct(todo)}</td></tr>
<tr><td style="padding:6px">⛔ wieder blocked</td><td style="text-align:right">{blocked}</td><td style="text-align:right">{pct(blocked)}</td></tr>
<tr><td style="padding:6px">🚫 cancelled</td><td style="text-align:right">{canc}</td><td style="text-align:right">{pct(canc)}</td></tr>
</table>
<p><b>{moved_n}</b> der 200 wurden seit dem Flip angefasst (Agenten haben reagiert).</p>
<h3>Nebenbefund (Fleet, seit Baseline)</h3>
<ul>
<li>max_iterations-Schleifen: <b>{loops_n}</b> {'✅ (Schleifen-Fix greift)' if loops_n<5 else '⚠️ (noch Schleifen)'}</li>
<li>RAM-Guardrail-Fehler: <b>{ram_n}</b></li>
</ul>
<table style="border-collapse:collapse;width:100%;margin-top:8px;font-size:13px">
<tr style="background:#f0f0f0"><th style="text-align:left;padding:4px">Company</th><th style="text-align:left;padding:4px">Status</th><th style="text-align:right;padding:4px">n</th></tr>
{rows_html}
</table>
<p style="color:#888;font-size:12px;margin-top:16px">Automatischer Check &middot; blocked-restart-check &middot; Baseline {BASELINE[:16]}</p>
</div>"""

text = (f"200 re-gestartete Issues — Ausgang:\n"
        f"  done: {done} ({pct(done)}) | in Arbeit: {inprog} | todo: {todo} | wieder blocked: {blocked} | cancelled: {canc}\n"
        f"  {moved_n}/200 seit Flip angefasst.\n"
        f"  Fleet seit Baseline: max_iterations={loops_n}, RAM-Guardrail={ram_n}\n")

payload = json.dumps({"from":FROM,"to":TO,
    "subject":f"Wirksamkeitskontrolle Re-Start: {done}/{total} durchgelaufen, {blocked} wieder blocked",
    "text":text,"html":html,"attachments":[]}).encode()

req = urllib.request.Request(WEBHOOK, data=payload,
    headers={"Content-Type":"application/json","X-Mailhub-Secret":SECRET})
try:
    with urllib.request.urlopen(req, timeout=30) as r:
        print(f"gesendet ({r.status}): done={done} todo={todo} blocked={blocked} moved={moved_n} loops={loops_n}")
except Exception as e:
    print(f"FEHLER Mailversand: {e}", file=sys.stderr); sys.exit(2)
