#!/usr/bin/env python3
"""Rueckwirkende Auswertung: hat der Advisor je etwas verbessert? (WHI-3389)

Die Altvorschlaege tragen kein `cause` (die Ursachenklassen gibt es erst seit
dem 31.07.) und nur 21 von 102 eine `agent_id` -- der Rest wird ueber den
Namen gejoint. Nicht aufloesbare Faelle zaehlen als `unklar`, nie als Erfolg.
"""
import datetime as dt
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from advisor.state import load_state
from advisor.agents import fetch_agent_rows, agent_profiles
from advisor.outcomes import (evaluate, fetch_config_revisions,
                              fetch_runs_for_window, resolve_agent_id)

WINDOW = 14


def collect_findings(proposals, profiles, decision="implemented"):
    """Angewendete Altvorschlaege in die Befundform bringen."""
    findings = []
    for p in proposals:
        if p.get("decision") != decision or not p.get("first_seen"):
            continue
        findings.append({
            "agent_id": p.get("agent_id") or resolve_agent_id(profiles, p.get("agent")),
            "agent_name": p.get("agent"),
            "cause": None,
            "first_seen": str(p["first_seen"])[:10],
            "to_model": p.get("to_model"),
        })
    return findings


def main():
    state = load_state()
    proposals = state.get("proposals", [])
    proposals = list(proposals.values()) if isinstance(proposals, dict) else proposals
    profiles = agent_profiles(fetch_agent_rows())

    findings = collect_findings(proposals, profiles)
    unresolved = [f for f in findings if not f["agent_id"]]

    revisions = fetch_config_revisions(days=180)
    runs = {}
    for f in findings:
        if not f["agent_id"]:
            continue
        day = dt.date.fromisoformat(f["first_seen"])
        key = (f["agent_id"], f["first_seen"])
        if (*key, "vorher") in runs:
            continue  # identischer Agent + Stichtag: Fenster schon geholt
        runs[(*key, "vorher")] = fetch_runs_for_window(
            f["agent_id"], str(day - dt.timedelta(days=WINDOW)), str(day))
        runs[(*key, "nachher")] = fetch_runs_for_window(
            f["agent_id"], str(day), str(day + dt.timedelta(days=WINDOW)))

    results = evaluate(findings, runs, revisions, window_days=WINDOW)

    print(f"{len(findings)} angewendete Vorschlaege, Fenster +/-{WINDOW} Tage")
    if unresolved:
        print(f"davon {len(unresolved)} ohne aufloesbaren Agenten: "
              f"{', '.join(sorted({f['agent_name'] or '?' for f in unresolved}))}")
    print()
    for r in sorted(results, key=lambda x: x["finding"]["first_seen"]):
        f = r["finding"]
        name = (f["agent_name"] or "?")[:24]
        print(f"  {f['first_seen']}  {name:<26} {r['outcome']:<12} "
              f"{r['before']} -> {r['after']}")
    print("\nBilanz:", dict(Counter(r["outcome"] for r in results)))


if __name__ == "__main__":
    raise SystemExit(main())
