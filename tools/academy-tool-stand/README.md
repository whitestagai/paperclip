# KI-Tool-Stand — Pflege-Routine (noch nicht angelegt)

`routine.json` ist der fertige Body für `POST /api/companies/9cebf3cf-efe8-4597-a400-f06488900a87/routines`
(Board-Token nötig). Danach Trigger anlegen:

```
POST /api/routines/<routineId>/triggers
{ "kind": "schedule", "cronExpression": "0 6 1 */2 *", "timezone": "Europe/Berlin" }
```

Jeder zweite Monat am 1. um 06:00 → 59–62 Tage Abstand, sicher unter der 90-Tage-Grenze,
ab der das Lektorat jeden ACADEMY-Kurs mit GELB bewertet (Prüfpunkt [13]).

Datei: `~/Obsidian/WHITESTAG-Vault/WHITESTAG.ACADEMY/_KI-TOOL-STAND.md`, zuletzt 2026-10-16
von Hand aktualisiert. Ihr Abschnitt „Pflege" nennt diese Routine bereits als zuständig.
