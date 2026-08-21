"""Wirksamkeitsmessung: was wurde aus einem Befund? (WHI-3389)

102 Vorschlaege lagen im State, 20 als `implemented` markiert, und niemand
hatte je geprueft ob einer geholfen hat. Ohne dieses Signal kann die
Qualitaet der Befunde systematisch nicht steigen: es gibt nichts, woran
sich die Schmerzschwelle korrigieren liesse.

Reine Funktionen -- DB-Zugriff steht getrennt am Ende der Datei, nach dem
Muster von telemetry.py (fetch_rows vs. aggregate_runs).
"""
from advisor.db import DSN
from advisor.signals import CONFIG_CODES, MODEL_CODES, UPSTREAM_CODES

# Welche Fehlercodes zu einer Ursachenklasse gehoeren. `adapter` teilt sich
# die Codes mit `model` -- der Unterschied liegt im Adapter, nicht im Code.
CODES_BY_CAUSE = {
    "config": CONFIG_CODES,
    "model": MODEL_CODES,
    "adapter": MODEL_CODES,
    "upstream": UPSTREAM_CODES,
}

# Altvorschlaege tragen kein `cause` (die Klassen gibt es erst seit dem
# 31.07.) -- fuer sie zaehlt jeder Fehlercode.
ALL_CODES = tuple(set(CONFIG_CODES + MODEL_CODES + UPSTREAM_CODES))

# Eine Rate aus wenigen Laeufen ist keine Aussage -- dieselbe
# Datenbasis-Anforderung wie bei der Schmerzschwelle in signals.py.
MIN_RUNS_FOR_VERDICT = 10

# Ein Rueckgang gilt als Wirkung, wenn sich die Klassenrate mindestens
# halbiert. Grob mit Absicht: nebenlaeufige Ursachen kann die Messung nicht
# ausschliessen (der llm_error-Sturm des CMO endete am 22.07. von selbst),
# sie ist ein Indiz, kein Beweis.
IMPROVEMENT_FACTOR = 0.5

# Umgekehrt: steigt die Rate nach einem Eingriff um mehr als die Haelfte,
# ist das eine eigene Aussage. Der rueckwirkende Lauf zeigte CEO
# 0.14 -> 0.88 und VP Engineering 0.88 -> 0.62 beide als "wirkungslos" --
# eine gemeinsame Klasse verschleiert die Faelle, die zaehlen (WHI-3389).
DETERIORATION_FACTOR = 1.5


def class_rate(runs, codes):
    """Anteil der Laeufe, die an einem Code dieser Klasse scheiterten.

    Absolute Fehlerzahlen sind unbrauchbar, weil die Zahl der Laeufe je
    Fenster schwankt. `None` heisst: zu duenne Datenbasis fuer ein Urteil.
    """
    total = len(runs)
    if total < MIN_RUNS_FOR_VERDICT:
        return None
    hit = sum(1 for r in runs if r.get("error_code") in codes)
    return round(hit / total, 4)


def classify_outcome(before, after, changed):
    """Was wurde aus einem Befund?

    `behoben`        Aenderung erfolgt, Rate halbiert -- Diagnose war richtig
    `wirkungslos`    Aenderung erfolgt, Rate blieb    -- Diagnose war falsch
    `verschlechtert` Aenderung erfolgt, Rate stieg um die Haelfte
    `ignoriert`      keine Aenderung, Fehler bestehen
    `rauschen`       keine Aenderung, Fehler weg      -- Befund war unnoetig
    `unklar`         zu duenne Datenbasis

    `wirkungslos` und `rauschen` sind die Lernsignale: haeufen sich
    `rauschen`-Faelle, sitzt die Schmerzschwelle zu niedrig; haeufen sich
    `wirkungslos`-Faelle, ist die Ursachenzuordnung in signals.py falsch.
    """
    if before is None or after is None or before <= 0:
        return "unklar"
    improved = after <= before * IMPROVEMENT_FACTOR
    if not changed:
        # Ohne Eingriff gibt es nichts, dem sich eine Verschlechterung
        # zuschreiben liesse -- der Befund blieb schlicht liegen.
        return "rauschen" if improved else "ignoriert"
    if improved:
        return "behoben"
    return "verschlechtert" if after >= before * DETERIORATION_FACTOR else "wirkungslos"


def find_config_change(revisions, agent_id, since):
    """Die erste Konfigurationsaenderung dieses Agenten nach `since`.

    Spaetere Aenderungen werden bewusst ignoriert: es zaehlt die Reaktion
    auf den Befund, nicht was Wochen danach noch geschah.
    """
    candidates = [
        r for r in revisions
        if r.get("agent_id") == agent_id and str(r.get("created_at", "")) > str(since)
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda r: str(r["created_at"]))


def resolve_agent_id(profiles, name):
    """Agent-ID zu einem Namen -- nur wenn der Name eindeutig ist.

    "Vault-Maintainer" und "Link-Detektor" existieren je zweimal (WHITESTAG
    und Clara Sound). Ein Namens-Join wuerde stillschweigend den falschen
    Agenten treffen und die Messung einem Unbeteiligten zuschreiben. Im
    Zweifel lieber `unklar` als ein falsch zugeordnetes Urteil.
    """
    hits = [p["agent_id"] for p in profiles if p.get("name") == name]
    return hits[0] if len(hits) == 1 else None


def evaluate(findings, runs_by_agent, revisions, window_days=14):
    """Haelt jeden Befund gegen das, was danach geschah.

    `runs_by_agent` ist ein Dict
    {(agent_id, first_seen, "vorher"|"nachher"): [runs]}.

    Der Stichtag gehoert in den Schluessel: derselbe Agent kann mehrere
    Befunde zu verschiedenen Zeitpunkten haben, und jeder braucht sein
    eigenes Fenster. Ohne den Stichtag ueberschreibt der zuletzt
    aufgebaute Eintrag alle frueheren (WHI-3389).

    Gemessen wird nur die Codegruppe der jeweiligen Ursache -- ein
    config-Befund darf nicht durch zurueckgegangene Modellfehler geheilt
    aussehen.
    """
    out = []
    for f in findings:
        agent_id = f.get("agent_id")
        day = f.get("first_seen", "")
        codes = CODES_BY_CAUSE.get(f.get("cause")) or ALL_CODES
        before = class_rate(runs_by_agent.get((agent_id, day, "vorher"), []), codes)
        after = class_rate(runs_by_agent.get((agent_id, day, "nachher"), []), codes)
        change = find_config_change(revisions, agent_id, since=f.get("first_seen", ""))
        out.append({
            "finding": f,
            "outcome": classify_outcome(before, after, changed=bool(change)),
            "before": before,
            "after": after,
            "changed_at": str(change["created_at"]) if change else None,
            "window_days": window_days,
        })
    return out


# --- DB-Zugriff (ungetestet, reine Abfragen) --------------------------------

_REVISIONS_QUERY = """
SELECT agent_id::text, created_at, before_config, after_config, changed_keys
FROM agent_config_revisions
WHERE created_at > now() - (%s || ' days')::interval
ORDER BY created_at
"""

_WINDOW_QUERY = """
SELECT error_code FROM heartbeat_runs
WHERE agent_id = %s AND created_at >= %s::timestamptz
  AND created_at < %s::timestamptz
"""


def fetch_config_revisions(days=180):
    import psycopg
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute(_REVISIONS_QUERY, (str(days),))
        return [{"agent_id": a, "created_at": c.isoformat(),
                 "before_config": b, "after_config": af, "changed_keys": ck}
                for a, c, b, af, ck in cur.fetchall()]


def fetch_runs_for_window(agent_id, start, end):
    import psycopg
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute(_WINDOW_QUERY, (agent_id, start, end))
        return [{"error_code": code} for (code,) in cur.fetchall()]
