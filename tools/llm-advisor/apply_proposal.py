#!/usr/bin/env python3
"""CLI-Einstieg: freigegebene Modell-Zuweisung deterministisch anwenden.

    apply_proposal.py <agent_id> <model>

Prueft <model> gegen /v1/models und <agent_id> gegen die API, setzt dann
adapterConfig.model per PATCH und verifiziert. Kein LLM im Spiel.
"""
from advisor.apply import main

if __name__ == "__main__":
    raise SystemExit(main())
