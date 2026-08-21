"""State-Datei: merkt vorgeschlagene Modelle + Walters Entscheidungen."""
import json
from pathlib import Path

STATE = Path(__file__).resolve().parent.parent / "state" / "llm-advisor-state.json"


def load_state():
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {"proposals": []}


def _key(p):
    return (p.get("agent", ""), p.get("to_model", ""))


def diff_proposals(prev_state, current):
    """Gibt nur Vorschläge zurück, die neu sind (nicht schon pending/rejected/accepted)."""
    known = {_key(p) for p in prev_state.get("proposals", [])}
    return [p for p in current if _key(p) not in known]


def validate_proposals(proposals, agents, model_keys):
    """Trennt Vorschlaege in (valid, rejected) gegen den Live-Zustand.

    - `agents`: Live-Roster, Liste mit mind. {name, agent_id}.
    - `model_keys`: Menge real verfuegbarer Modell-IDs (/v1/models bzw. on-disk).

    Ein Vorschlag ist valid, wenn sein `agent` (Name) einem Live-Agenten
    entspricht, `to_model` in `model_keys` liegt UND — falls der Vorschlag
    ein `from_model` nennt und der Live-Agent ein `model`-Feld traegt — das
    `from_model` mit dem tatsaechlich laufenden Modell uebereinstimmt.
    Valide werden mit `agent_id` angereichert; abgelehnte tragen ein
    `reason`-Feld.

    Der from_model-Abgleich faengt Drift ab: ein Vorschlag, der von einem
    falschen Ist-Modell ausgeht, hat auch eine wertlose Begruendung
    (Telemetrie/Schmerzpunkt gehoeren dann zu einem anderen Modell) und
    darf nicht gemailt/freigegeben werden.
    """
    by_name = {a["name"]: a for a in agents}
    valid, rejected = [], []
    for p in proposals:
        agent = by_name.get(p.get("agent"))
        if agent is None:
            rejected.append({**p, "reason": f"unknown agent: {p.get('agent')!r}"})
            continue
        if p.get("to_model") not in model_keys:
            rejected.append({**p, "reason": f"unknown model: {p.get('to_model')!r}"})
            continue
        from_model = p.get("from_model")
        live_model = agent.get("model")
        if from_model and live_model and from_model != live_model:
            rejected.append({
                **p,
                "reason": (
                    f"from_model drift: proposal says {from_model!r} "
                    f"but agent runs {live_model!r}"
                ),
            })
            continue
        valid.append({**p, "agent_id": agent["agent_id"]})
    return valid, rejected


def record_proposals(prev_state, new_proposals, generated_at):
    merged = list(prev_state.get("proposals", []))
    for p in new_proposals:
        merged.append({**p, "decision": "pending", "first_seen": generated_at})
    prev_state["proposals"] = merged
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(prev_state, ensure_ascii=False, indent=2))
    return prev_state
