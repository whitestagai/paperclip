# Phase B1 — AGENTS.md Boilerplate entkoppeln

**Datum:** 2026-06-12
**Status:** Design (genehmigt, bereit für Planung)
**Company:** WHITESTAG (`9cebf3cf-efe8-4597-a400-f06488900a87`)

## Kontext & Ausgangsbefund

Die lokalen LM-Studio-Agenten konsumieren **keinen** Paperclip-`SKILL.md`-Inhalt — das
Adapter-Plugin (`opensource/paperclip-adapter-lmstudio/src/server/execute.ts`,
`buildSystemPrompt`) baut den Prompt nur aus festem Vorspann + `agentInstructions` +
**AGENTS.md** (`## Agent Persona`). AGENTS.md ist damit der einzige garantiert wirksame
per-Agent-Wissenskanal.

Audit der 24 AGENTS.md: ~80 % des Inhalts ist **identisches Boilerplate** (Fast-Exit-Gate,
Abschluss-Mail, Deliverable-Regeln, Pre-Flight, Dokument-Ablage, Frontmatter-Spec,
Memory/Lernen, Tabellen-Deliverables), wortgleich in jeder Datei. Nur ~30–60 Zeilen sind
rollenspezifisch. Für die kleinen Modelle bedeutet das: jeder Heartbeat ~150 Zeilen
redundante Prozedur, das Rollensignal geht unter.

**Teil des B-Programms:** B1 (dieser Spec) = Boilerplate entkoppeln. B2 = Knowledge-Loop
reparieren. B3 = Business-Domänen-Wissen füllen. B1 ist unabhängig und zuerst.

## Ziel

Geteiltes Boilerplate aus allen 24 AGENTS.md in **eine** kanonische, **kondensierte**
Quelle ziehen; jede AGENTS.md wird aus `[Rolle] + [Common]` generiert. Ergebnis:
Single Source of Truth für Boilerplate, ~halber Prozedur-Ballast pro Heartbeat,
Rollensignal weiter oben. **Kein Control-Plane-/Adapter-Umbau.**

Gewählter Ansatz: **Single-Source + Kondensieren + Generieren** (nicht: geteilter
Prompt-Kanal — es existiert kein sauberer leerer company-geteilter Kanal; der
`promptTemplate`-Weg ist „legacy"/`clearLegacyPromptTemplate`).

## Architektur

```
agents-instructions/
  _common.md              # kanonische Boilerplate-Vorlage mit Platzhaltern
  roles/<agent>.role.md   # nur rollenspezifischer Inhalt (24 Dateien)
  agents-manifest.json    # agentId, name, reportsTo, urlKey pro Agent
  build-agents-md.py      # Generator (4 Modi)
```

**Zusammensetzung pro Agent (Reihenfolge wie heute):**

```
[Fast-Exit-Gate]      (aus _common — muss oben stehen, ordnungskritisch)
[# Name + Rolle …]    (aus role.md)
[Boilerplate-Rest]    (aus _common: Mail, Deliverable, Frontmatter, Pfade, Memory, Tabellen)
```

`_common.md` enthält Platzhalter (`{{agent_name}}`, `{{reports_to}}`), die der Generator
pro Agent aus `agents-manifest.json` füllt (Mail-Skript-Name, `paperclip_agent` im
Frontmatter etc.).

## Common vs. Role

**`_common.md` (geteilt, kondensiert):** Fast-Exit-Gate, Sprache-Regel, Abschluss-Mail an
Walter, Deliverable-als-Issue-Dokument + Pre-Flight-Check, Dokument-Ablage + „absolute
Pfade"-Regel, Frontmatter-Spec, Gedächtnis-&-Lernen, Tabellen-Deliverables,
Marken-Kurzreferenz.

**`<agent>.role.md` (einzigartig):** `# Name`, „Deine Verantwortung", „Arbeitsweise",
rollenspezifische Document-Keys, WHITESTAG-Kontext der Rolle, „Verfügbare Skills",
Berichtslinie.

**Scope-Grenze:** Role-Inhalte werden aus den bestehenden AGENTS.md **1:1 extrahiert und
übernommen** — nicht neu geschrieben/geschärft (das ist ein separater späterer Pass).
B1 entkoppelt und kondensiert ausschließlich das Boilerplate.

## Kondensierung

| Block | heute | Ziel |
|---|---|---|
| Frontmatter-Spec | ~30 Z | YAML + 2-Zeilen-Notiz (~12 Z) |
| Abschluss-Mail an Walter | ~30 Z | ~12 Z |
| Deliverable + Pre-Flight | ~35 Z | ~15 Z |
| Dokument-Ablage + absolute Pfade | ~25 Z | ~12 Z |
| Memory/Lernen + Tabellen | ~20 Z | ~14 Z |

`_common.md`: ~150 → ~65 Zeilen. AGENTS.md gesamt: ~95–125 Z statt 190–490 Z.
Substanz (alle Pflicht-Regeln, Pfade, Skript-Aufrufe) bleibt erhalten — nur Verbosität fällt.

## Generator & Schreibweg

Schreibweg (managed-Modus-konform): `PUT /api/agents/:id/instructions-bundle/file`
mit `{ "path": "AGENTS.md", "content": <zusammengesetzt> }`.
Lesen/Backup: `GET /api/agents/:id/instructions-bundle/file?path=AGENTS.md`.

**Generator `build-agents-md.py` — 4 Modi:**

- `--backup` — alle 24 aktuellen AGENTS.md sichern (timestamped JSON).
- `--dry-run` — pro Agent Diff alt→neu (Zeilenzahl + Vorschau), nichts geschrieben.
- `--apply` — pro Agent `[role + gefülltes common]` zusammensetzen, via PUT schreiben.
- `--verify` — zurücklesen, prüfen: Common-Block (normalisiert) bei allen identisch,
  Role-Markierung (`# <Name>`) vorhanden, keine offenen `{{platzhalter}}`.

**Seeding (einmalig, vor allem anderen):** Extraktions-Schritt zieht die
rollenspezifischen Abschnitte aus jeder aktuellen AGENTS.md nach `roles/<agent>.role.md`
(menschlich prüfbar, bevor `--apply` läuft).

## Sicherheit / Reversibilität

- Backup vor `--apply` (voller Rollback via PUT der gesicherten Inhalte).
- Idempotent (gleiche Quelle → gleicher Output).
- `_common.md` + `roles/*.role.md` + Manifest versioniert im Repo (Single Source of Truth).
- Da Role 1:1 extrahiert wird, zeigt der Dry-Run primär das Schrumpfen des Boilerplate.

## Nicht-Ziele (B1)

- Kein Neuschreiben/Schärfen der Role-Inhalte (separater Pass).
- Kein Knowledge-Loop-Fix (B2), kein neues Domänen-Wissen (B3).
- Kein Adapter-/Control-Plane-Code-Umbau (Ansatz 2 = optionales späteres Upgrade).
- HomePod-Test-Agent + Nicht-WHITESTAG-Agenten unangetastet.

## Erfolgskriterien

- 24 AGENTS.md werden aus Single-Source generiert; `--verify` grün.
- Common-Boilerplate existiert genau einmal (`_common.md`), Wert-Platzhalter korrekt gefüllt.
- Jede AGENTS.md spürbar kürzer (Ziel ~halber Boilerplate-Umfang), Role-Inhalt vollständig erhalten.
- Backup vorhanden, Rollback dokumentiert.
