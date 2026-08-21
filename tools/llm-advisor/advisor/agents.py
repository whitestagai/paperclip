"""Liest Agent→Modell-Zuweisung und leitet Profile ab."""
from advisor.classify import capability_class
from advisor.db import DSN

_QUERY = """
SELECT a.id::text, a.company_id::text, a.name, a.role, a.adapter_type,
       a.adapter_config->>'model'         AS model,
       a.adapter_config->>'fallbackModel' AS fallback_model,
       NULLIF(a.adapter_config->>'maxIterations', '')::int    AS max_iterations,
       NULLIF(a.adapter_config->>'timeoutMs', '')::bigint     AS timeout_ms,
       NULLIF(a.adapter_config->>'contextLength', '')::int    AS context_length,
       -- Lauf-Grenze der claude_local-Agenten. maxIterations liest deren
       -- Adapter nicht (siehe advisor.signals.TURN_LIMIT_ADAPTER), ohne
       -- dieses Feld bliebe der Hinweis inhaltsleer.
       NULLIF(a.adapter_config->>'maxTurnsPerRun', '')::int    AS max_turns_per_run
FROM agents a
WHERE a.status <> 'terminated'
ORDER BY a.company_id, a.name
"""


def fetch_agent_rows():
    import psycopg
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute(_QUERY)
        return cur.fetchall()


def agent_profiles(rows):
    profs = []
    for (agent_id, company_id, name, role, adapter_type, model,
         fallback_model, max_iterations, timeout_ms, context_length,
         max_turns_per_run) in rows:
        profs.append({
            "agent_id": agent_id,
            "company_id": company_id,
            "name": name,
            "role": role,
            "adapter_type": adapter_type,
            "model": model,
            "is_local": adapter_type == "lmstudio_local",
            "capability": capability_class((role or "") + " " + (name or ""), model or ""),
            # Config-Grenzen: ohne sie ist max_iterations/timeout nicht
            # deutbar und jeder Vorschlag laeuft auf einen Modellwechsel
            # hinaus (WHI-3362).
            "fallback_model": fallback_model,
            "max_iterations": max_iterations,
            "timeout_ms": timeout_ms,
            "context_length": context_length,
            "max_turns_per_run": max_turns_per_run,
        })
    return profs
