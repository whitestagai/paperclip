"""Trockenlauf: blockierte Paperclip-Issues typisiert triagieren.

Schreibt NICHTS. Der Lauf zeigt nur, welche Issues das Gate automatisch
entscheiden wuerde und welche an einen Menschen gehen.

Aufruf:
    python3 triage.py --limit 30
    python3 triage.py --limit 30 --min-confidence 0.95
"""
from dataclasses import dataclass
from typing import Optional, List
import argparse, collections, json, os, re, statistics, subprocess, time, urllib.request

from decide import build_request, decide, Decision, TOP_LOGPROBS

LMSTUDIO = "http://192.168.2.181:1234/v1/chat/completions"
MODEL = "google/gemma-4-12b-qat"
MAX_DESC = 220

OPTIONS = {
    "A": "abbrechen — ueberholte Routine-Wiederholung, der Zeitpunkt ist vorbei",
    "B": "Symptom eines aufgegebenen Recovery-Versuchs; das eigentliche Ziel steht in origin_id",
    "C": "echte gestaute Arbeit — freigeben und bearbeiten lassen",
}
INSTRUCTIONS = (
    "Du triagierst blockierte Issues eines Agentensystems. Ordne das Issue genau einer "
    "Kategorie zu.\n" + "\n".join(f"{k} = {v}" for k, v in OPTIONS.items())
)


@dataclass
class Issue:
    id: str
    title: str
    origin_id: Optional[str]
    description: str
    age_days: int


def build_state(issue: Issue) -> str:
    """Den Zustand bauen, den das Modell zu sehen bekommt."""
    desc = re.sub(r"\s+", " ", issue.description or "").strip()
    desc = desc[:MAX_DESC] if desc else "(leer)"
    return (
        f"Titel: {issue.title}\n"
        f"Alter: {issue.age_days} Tage blockiert\n"
        f"origin_id: {'gesetzt' if issue.origin_id else 'nicht gesetzt'}\n"
        f"Beschreibung: {desc}"
    )


def summarize(decisions: List[Decision]) -> dict:
    """Den Trockenlauf auswerten: wie viel waere automatisch gelaufen?"""
    gruende = collections.Counter(d.reason for d in decisions if d.abstained)
    optionen = collections.Counter(d.option for d in decisions if not d.abstained)
    return {
        "gesamt": len(decisions),
        "entschieden": sum(1 for d in decisions if not d.abstained),
        "enthalten": sum(1 for d in decisions if d.abstained),
        "gruende": dict(gruende),
        "optionen": dict(optionen),
    }


def load_issues(limit: int) -> List[Issue]:
    sql = f"""SELECT id, title, coalesce(origin_id::text,''),
       coalesce(description,''), date_part('day', now()-created_at)::int
FROM issues WHERE status='blocked' ORDER BY created_at LIMIT {int(limit)};"""
    out = subprocess.run(
        ["psql", "-h", "localhost", "-p", "54329", "-U", "paperclip", "-d", "paperclip",
         "-t", "-A", "-R", "\x1e", "-F", "\x1f", "-c", sql],
        capture_output=True, text=True,
        # Lokale embedded-Postgres der Paperclip-Instanz; ueberschreibbar per Umgebung,
        # damit kein Zugang im Repo steht.
        env={"PGPASSWORD": os.environ.get("PAPERCLIP_DB_PASSWORD", "paperclip"),
             "PATH": "/usr/bin:/bin:/opt/homebrew/bin"},
    )
    if out.returncode != 0:
        raise SystemExit(f"psql fehlgeschlagen: {out.stderr.strip()[:300]}")
    issues = []
    for rec in out.stdout.split("\x1e"):
        if not rec.strip():
            continue
        f = rec.split("\x1f")
        if len(f) < 5:
            continue
        issues.append(Issue(f[0], f[1], f[2] or None, f[3], int(f[4] or 0)))
    return issues


def http_transport(req):
    r = urllib.request.Request(LMSTUDIO, data=json.dumps(req).encode(),
                               headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=60))


def ask(issue: Issue, min_conf: float, min_mass: float, transport=None):
    """Eine Entscheidung zu einem Issue holen.

    Der Zustand geht UNVERAENDERT an das Modell — kein Cache-Busting-Zeitstempel.
    Gemessen am 05.10.2026: ein angehaengter Zeitstempel verschob die Konfidenz
    desselben Issues von 0.82 auf 0.89 und kann damit die Schwelle kippen. Weil
    die Entscheidung bei gleicher Eingabe ohnehin deterministisch ist (40 Issues
    zweimal gelaufen, 0 Abweichungen), ist ein Cache-Treffer hier erwuenscht.
    """
    transport = transport or http_transport
    req = build_request(MODEL, build_state(issue), INSTRUCTIONS, list(OPTIONS))
    t0 = time.time()
    try:
        d = transport(req)
    except Exception as e:
        return Decision(None, 0.0, 0.0, {}, True, f"aufruf_fehlgeschlagen: {type(e).__name__}"), 0.0
    lp = d["choices"][0].get("logprobs")
    top = lp["content"][0]["top_logprobs"] if lp and lp.get("content") else None
    return decide(top, list(OPTIONS), min_conf, min_mass), time.time() - t0


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=30)
    p.add_argument("--min-confidence", type=float, default=0.9)
    p.add_argument("--min-mass", type=float, default=0.5)
    a = p.parse_args()

    issues = load_issues(a.limit)
    print(f"TROCKENLAUF — es wird nichts geschrieben. {len(issues)} Issues, Modell {MODEL}")
    print(f"Schwellen: Konfidenz >= {a.min_confidence}, Optionsmasse >= {a.min_mass}\n")
    print(f"{'Titel':<48} {'Opt':>4} {'Konf':>6} {'ms':>6}  Status")
    print("-" * 96)

    decisions, lat = [], []
    for it in issues:
        d, dt = ask(it, a.min_confidence, a.min_mass)
        decisions.append(d)
        if dt:
            lat.append(dt)
        status = "auto" if not d.abstained else f"MENSCH ({d.reason})"
        print(f"{it.title[:48]:<48} {str(d.option or '-'):>4} {d.confidence:>6.2f} {dt*1000:>6.0f}  {status}")

    s = summarize(decisions)
    print("-" * 96)
    print(f"gesamt {s['gesamt']} | automatisch entscheidbar {s['entschieden']} | an den Menschen {s['enthalten']}")
    print(f"Optionsverteilung (nur entschieden): {s['optionen']}")
    print(f"Enthaltungsgruende: {s['gruende']}")
    if lat:
        print(f"Latenz: median {statistics.median(lat)*1000:.0f} ms, max {max(lat)*1000:.0f} ms")


if __name__ == "__main__":
    main()
