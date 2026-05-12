**Domain:** {{DOMAIN_TITLE}}
**Quellen:**
{{SOURCES_LIST}}

**Vault-Pfad für diese Domain:**
`{{VAULT_DOMAIN_PATH}}`

## Auftrag

Recherchiere, was sich bei {{DOMAIN_TITLE}} seit dem letzten Update geändert hat. Konzentriere dich auf Neuerungen mit **operativem Impact** — also Features/Changes, die wir in unseren Workflows nutzen könnten oder die bestehende Workflows brechen.

## Schreib-Regeln

1. **Dedup zuerst:** Liste existierende Files unter `{{VAULT_DOMAIN_PATH}}`. Wenn ein Topic schon existiert → bestehende Datei updaten (im Frontmatter `updated: {{TODAY}}` setzen), keine neue Datei anlegen.
2. **Quality-Gate:** Schreibe nur, wenn die Information *non-obvious / surprising / actionable* ist. Generische Release-Listen ohne operative Konsequenz nicht schreiben — Issue auf `done` mit Comment "no new actionable knowledge".
3. **Frontmatter-Pflicht:**
   ```yaml
   ---
   name: <Titel>
   description: <ein Satz>
   type: knowledge
   domain: {{DOMAIN_SLUG}}
   agent: online-recherche
   created: {{TODAY}}
   sources:
     - <url>
   ---
   ```
4. **MEMORY.md aktualisieren:** Nach jedem Knowledge-File-Write den Domain-Index in `{{VAULT_DOMAIN_PATH}}/MEMORY.md` aktualisieren (neuen Eintrag in "Aktive Einträge").

## Constraints

- Max {{MAX_TURNS}} Turns, Max {{TIMEOUT_SEC}} Sek.
- Web-Recherche erlaubt (WebFetch/WebSearch).
- Wenn unsicher → kein Eintrag besser als ein schlechter Eintrag.
- Bei Tool-Error oder unklarer Anweisung: Comment mit `LESSON-CANDIDATE: <kurz>` setzen, der nächtliche Reibungs-Sweep destilliert daraus eine Lesson.
