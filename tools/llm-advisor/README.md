# LLM Advisor
Analyse der LLM-Zuweisung (3 Companies) gegen neue MLX-Modelle.
Läuft wöchentlich montags 07:00 (Europe/Berlin) — Träger: Agent „LLM-Konfigurationsanalyst" (claude_local).
`evaluate_history.py` wertet rückwirkend aus, was aus früheren Vorschlägen wurde.
Der Prompt der Routine ist eine KOPIE von routine-brief.md in `routines.description`;
Änderungen am Brief müssen per PATCH /api/routines/<id> nachgezogen werden, sonst wirken sie nicht.
Spec: docs/superpowers/specs/2026-06-14-nightly-llm-advisor-design.md
Plan: docs/superpowers/plans/2026-06-14-nightly-llm-advisor.md
Einstieg: collect_ist_zustand.py → Agenten-Brief (routine-brief.md) → Mail.

## Marktdaten (`advisor/market.py`)

Zwei externe Quellen, beide von `collect_ist_zustand.py` geholt — das ist
**Schritt 1 des Agenten-Briefs**, kein Hintergrunddienst. Die Zahlen in
`state/ist-zustand.json` sind also genau so frisch wie der letzte Sammellauf;
fällt er aus, liest der Agent die Datei der Vorwoche. Deshalb prüft der Brief
`generated_at`, und deshalb hat jeder Abruf ein Zeitbudget (AA 60 s,
Websuche 30 s) — er liegt im selben Wallclock wie der Agentenlauf.

- **Artificial Analysis** (Free API, 100 Requests/24 h) — Qualitätsachse.
  Key in `~/.paperclip/instances/default/secrets/artificialanalysis.env` als
  `ARTIFICIALANALYSIS_API_KEY=…`. Fehlt er, meldet der Advisor
  `nicht_verfuegbar` und stellt keine Modellvorschläge.
- **Websuche-Dienst** `127.0.0.1:7789` — was es Neues gibt. Läuft live als
  LaunchAgent `de.whitestag.websuche` aus `~/.paperclip/scripts/websuche/`;
  Quelle ist `tools/websuche/` im Paperclip-Repo
  (`~/SynologyDrive/Mac/Claude Code MAC/Paperclip`), von dort deployed.

**Zahlen: rendern und prüfen — beide Hälften, wie in `evidence.py`.**
`markt_zeile()` baut je Modell den fertigen Satz (Indizes, Variante,
Quellenangabe mit Stand); er hängt als `model_market.modelle[<key>].zeile` im
JSON und wird übernommen, nicht formuliert. `verify_market_claims()` prüft den
fertigen Berichtstext dagegen und bindet jede Zahl an **ein** Modell — das,
dessen Name ihr zuletzt vorausging, in Markdown-Tabellen das der eigenen Zeile.

**Warum nicht im Agenten:** Der Träger läuft auf `lmstudio_local` und hat kein
WebSearch-Werkzeug; der Brief verlangte es trotzdem bis 20.08. Außerdem ist
das Wallclock-Budget knapp — Recherche im Agenten kostet Iterationen.

**Ablehnungsliste:** `state/abgelehnte-modelle.json` (Vorlage unter
`state-vorlagen/`, weil `state/` gitignored ist). Ohne sie empfiehlt der
Advisor jede Woche erneut Modelle, die praktisch schon verworfen wurden.
