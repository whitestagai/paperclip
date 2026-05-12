**Reibungs-Runs vom {{YESTERDAY}}:**

{{RUN_LIST}}

## Auftrag

Für jeden Reibungs-Run oben:

1. Hole das vollständige Activity-Log via `GET /api/runs/<run-id>/activity` und Comments via `GET /api/issues/<issue-id>/comments`.
2. Destilliere in **3-5 Sätzen**: *Was ist passiert? Warum? Was sollte der Agent beim nächsten Mal anders machen?*
3. Schreibe das Lesson nach `{{VAULT_LESSONS_PATH_PATTERN}}` mit Frontmatter:
   ```yaml
   ---
   name: <kurzer Titel>
   description: <ein Satz>
   type: lesson
   agent: <agent-slug>
   company: <company-slug>
   created: {{TODAY}}
   sources:
     - run://<run-id>
   ---
   ```
4. Aktualisiere die Agent-MEMORY.md (`{{VAULT_AGENT_PATH_PATTERN}}/MEMORY.md`) — füge Lesson-Eintrag oben in der Lessons-Liste hinzu.

## Sub-Step nach allen Lessons: Context-Bundle-Sync

Für jeden Agent in (whitestag, health):

- Kopiere `<vault-agent-pfad>/MEMORY.md` → `<instructions-path>/MEMORY.md`
- Erstelle `<instructions-path>/recent-lessons.md`: Top-5 Lessons der letzten 14 Tage, Volltext
- Erstelle `<instructions-path>/relevant-knowledge.md`: Headlines (aus `Skill-Wissen/<domain>/MEMORY.md`, nur "Aktive Einträge"-Liste, kein Volltext) für jede verlinkte Domain im Agent-MEMORY

## Constraints

- Wenn `trigger_run_statuses` leer ist und keine Reibungs-Runs gefunden → Issue auf `done` mit Comment "no friction yesterday, nothing to learn".
- Max {{MAX_RUNS}} Runs pro Sweep (neueste zuerst).
- Vault nicht gemounted → Issue auf `blocked` mit Comment "Vault not mounted, skipping". Kein Schreiben.
- Quality-Gate gilt auch hier: keine generischen Lessons ("Aufgabe ist gescheitert" ohne Lerngehalt) — solche Runs werden ohne Eintrag übersprungen.
