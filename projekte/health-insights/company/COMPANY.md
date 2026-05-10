---
name: Health Insights
description: Lokale Apple-Health-Analyse via Health Auto Export — privacy-first, alle Verarbeitung auf Walters Mac
slug: health-insights
schema: agentcompanies/v1
version: 0.1.0
license: MIT
authors:
  - name: Walter Schönenbröcher
goals:
  - Tägliches Health Briefing aus Apple-Health-Daten generieren
  - Q&A zu Schlaf, Training und Vitalwerten beantworten
  - Anomalien aus den Tagesdaten identifizieren und kommentieren
  - Wochenrückblick mit Trends erstellen
tags:
  - health
  - personal
  - local-llm
---

# Health Insights

Eine kleine, persönliche Hub-and-Spoke-Company, die Walters Apple-Health-Daten lokal auswertet. Alle Verarbeitung passiert auf seinem Mac — Daten verlassen das Gerät nie, das LLM läuft via LM Studio lokal.

## Workflow

Daten fließen so durch die Organisation:

1. **Datenpipeline (außerhalb der Company):** Apple Health → Health Auto Export (iPhone) → iCloud Drive → n8n-Workflow → Postgres + Obsidian-Markdown.
2. **CHO** (Chief Health Officer) ist der zentrale Hub. Er empfängt entweder die Daily-Briefing-Routine (cron) oder Q&A-Fragen vom User.
3. **Spezialisten** (Schlaf-, Trainings-, Vitals) bekommen Subtasks vom CHO, antworten in einem festen Format mit Kennzahlen + Empfehlung. Sie reden nie direkt miteinander — der CHO koordiniert.
4. **CHO** konsolidiert die Spezialisten-Antworten zu einem Briefing-Issue und einem Markdown-Block für den Obsidian-Tagesprotokoll.

## Datenzugriff

Alle Agenten haben lesenden Zugriff auf eine kleine Menge MCP-Tools, die Postgres-Aggregate liefern. Schreibrechte gibt es nur in eigene Issue-Outputs — kein Agent schreibt direkt in die DB.

## Phasen

Diese Company ist Teil eines mehrstufigen Rollouts (siehe [docs/superpowers/specs/2026-05-09-health-insights-company-design.md](../../docs/superpowers/specs/2026-05-09-health-insights-company-design.md)):

- Phase 1: Datenpipeline + diese Company-Struktur — *aktuell*
- Phase 2: Daily-Briefing-Routine + Markdown-Generierung
- Phase 3: Anomalie-Erkennung + Telegram-Notifications
- Phase 4: Weekly-Trend-Report
- Phase 5: Spracheingabe für Q&A

## Privacy

Keine Daten verlassen den Mac. Kein Cloud-LLM. Kein Telemetrie. Postgres läuft lokal auf `5432`, der MCP-Server bindet auf `localhost`, und der LLM-Adapter ist LM Studio.
