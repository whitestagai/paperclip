"""Liest heartbeat_runs aus der Paperclip-DB und aggregiert Fehler je Agent."""
import re
from collections import defaultdict

from advisor.db import DSN

_ERROR_CODES = (
    "max_iterations", "timeout", "llm_unreachable", "llm_error",
    "adapter_failed", "process_lost",
    # Gegenstelle: Rate-Limit / Anmeldung. Bis WHI-3389 nicht gezaehlt,
    # obwohl claude_transient_upstream der zweithaeufigste Code ist.
    "claude_transient_upstream", "claude_auth_required",
)

# Wie viele Klartext-Cluster je Agent gemeldet werden.
TOP_ERRORS = 5

_QUERY = """
SELECT r.company_id::text, r.agent_id::text, a.name,
       r.error_code, r.status,
       EXTRACT(EPOCH FROM (r.finished_at - r.started_at)) AS duration_s,
       r.error
FROM heartbeat_runs r
JOIN agents a ON a.id = r.agent_id
WHERE r.created_at > now() - (%s || ' days')::interval
"""

# Variable Teile, die dieselbe Ursache sonst in lauter Einzelfaelle zerlegen.
_NOISE = (
    (re.compile(r"https?://\S+"), "<url>"),
    (re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
                re.IGNORECASE), "<id>"),
    (re.compile(r"\b[0-9a-f]{4,}(?:-[0-9a-f]+)+\b", re.IGNORECASE), "<id>"),
    (re.compile(r"\d+"), "<n>"),
    (re.compile(r"\s+"), " "),
)

_SIGNATURE_LEN = 160


def error_signature(text):
    """Reduziert eine Fehlermeldung auf ihre wiedererkennbare Form.

    `adapter_failed` steht je nach Adapter fuer Timeout, Rate-Limit oder
    Prompt-Ueberlauf. Erst der Klartext trennt diese Faelle -- aber nur,
    wenn Zahlen, IDs und URLs vorher raus sind (WHI-3389).
    """
    sig = (text or "").strip()
    for pattern, repl in _NOISE:
        sig = pattern.sub(repl, sig)
    return sig.strip()[:_SIGNATURE_LEN]


def fetch_rows(days: int = 7):
    import psycopg
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute(_QUERY, (str(days),))
        return cur.fetchall()


def aggregate_runs(rows):
    by_agent = defaultdict(lambda: {"total_runs": 0, "succeeded": 0,
                                    "_dur_sum": 0.0, "_dur_n": 0})
    # (agent_id, error_code, signature) -> {"count": n, "sample": erster Text}
    clusters = defaultdict(lambda: defaultdict(lambda: {"count": 0, "sample": ""}))
    for company_id, agent_id, name, error_code, status, duration_s, error in rows:
        a = by_agent[agent_id]
        a["company_id"] = company_id
        a["agent_id"] = agent_id
        a["agent_name"] = name
        a["total_runs"] += 1
        if status == "succeeded":
            a["succeeded"] += 1
        if error_code in _ERROR_CODES:
            a[error_code] = a.get(error_code, 0) + 1
        if duration_s is not None:
            a["_dur_sum"] += float(duration_s)
            a["_dur_n"] += 1
        # Nur echte Fehllaeufe clustern -- ein `error`-Text an einem
        # erfolgreichen Run sagt nichts ueber eine Stoerung aus.
        if status != "succeeded" and error:
            sig = error_signature(error)
            if sig:
                c = clusters[agent_id][(error_code, sig)]
                c["count"] += 1
                if not c["sample"]:
                    c["sample"] = " ".join(error.split())[:_SIGNATURE_LEN]
    out = []
    for a in by_agent.values():
        for code in _ERROR_CODES:
            a.setdefault(code, 0)
        n = a.pop("_dur_n")
        s = a.pop("_dur_sum")
        a["avg_duration_s"] = (s / n) if n else 0.0
        a["fail_rate"] = round(1 - a["succeeded"] / a["total_runs"], 3) if a["total_runs"] else 0.0
        found = clusters.get(a["agent_id"], {})
        a["top_errors"] = [
            {"code": code, "signature": sig, "count": c["count"], "sample": c["sample"]}
            for (code, sig), c in sorted(found.items(), key=lambda kv: -kv[1]["count"])
        ][:TOP_ERRORS]
        out.append(a)
    return out
