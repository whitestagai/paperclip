"""Befundform je Ursachenklasse (WHI-3389).

Wenn das einzige Werkzeug ein Modellwechsel ist, sieht jedes Problem wie ein
falsches Modell aus -- am 31.07. wurden deshalb drei Vorschlaege gestellt,
von denen zwei technisch gar nicht ausfuehrbar waren.

Die Ausgabeform folgt jetzt der Ursache, und eine konkrete Aktion gibt es
nur, wo sie ausfuehrbar UND belegbar ist. `upstream` und `adapter` sind
Befunde ohne Handlungsempfehlung: das Zustaendige liegt ausserhalb der
Agenten-Konfiguration (Kontingent, Aufrufrate, Prompt-Groesse,
Erreichbarkeit).
"""
from advisor.evidence import evidence_line

REPORTABLE = ("config", "model", "upstream", "adapter")


def _action(profile):
    """Die ausfuehrbare Aktion zu einem Befund -- oder None."""
    signals = profile["signals"]
    cause = signals["cause"]
    if cause == "config":
        return {
            "kind": "config",
            "hint": (f"maxIterations={profile.get('max_iterations')} pruefen "
                     f"(PATCH /api/agents/{profile['agent_id']})"),
        }
    if cause == "model" and signals.get("model_change_allowed"):
        return {"kind": "model", "from_model": profile.get("model")}
    return None


def build_findings(profiles, window_days):
    """Aus annotierten Agentenprofilen die meldbaren Befunde bilden.

    Gefiltert wird nach `cause` und `actionable` -- beides kommt
    deterministisch aus advisor/signals.py und wird hier nicht neu bewertet.
    """
    out = []
    for p in profiles:
        signals = p.get("signals") or {}
        if signals.get("cause") not in REPORTABLE or not signals.get("actionable"):
            continue
        telemetry = p.get("telemetry") or {}
        top = telemetry.get("top_errors") or []
        out.append({
            "agent_id": p.get("agent_id"),
            "agent_name": p.get("name"),
            # "Vault-Maintainer" und "Link-Detektor" existieren je zweimal
            # (WHITESTAG + Clara Sound) -- ohne Company ist ein Befund
            # nicht eindeutig einem Agenten zuzuordnen.
            "company_id": p.get("company_id"),
            "cause": signals["cause"],
            "evidence": evidence_line(telemetry, window_days),
            "dominant": top[0]["sample"] if top else "",
            "action": _action(p),
        })
    return out
