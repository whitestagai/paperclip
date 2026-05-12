---
title: Agent Nightly Learning — Knowledge- & Lessons-Loops
status: draft
date: 2026-05-11
scope: WHITESTAG + Health Insights Companies (Clara Sound bewusst ausgeschlossen — eigener Vault später)
---

## Ziel

Paperclip-Agenten sollen sich nachts kontinuierlich weiterbilden — sowohl durch **Recherche** zu Neuerungen in ihren Skill-Domains (z.B. neue Photoshop-Features, n8n-Releases, Adobe-CEP-Änderungen) als auch durch **Reflexion** über die Reibung des Tages (fehlgeschlagene Runs, gefangene Tool-Errors, Anti-Pattern).

Das gelernte Wissen wird so abgelegt, dass

- Walter es in Obsidian lesen und kuratieren kann,
- die Skills selbst **eingefroren bleiben** (kein automatisches Wachstum von SKILL.md-Files),
- jeder Agent es beim nächsten Run automatisch im Context sieht,
- Bloat durch Quality-Gates, Dedup, Decay und Hard-Budgets verhindert wird.

## Voraussetzungen

- Paperclip-Dev-Server läuft lokal (`ing.paperclip.dev` launchd-Service) auf Port `3100`.
- Online-Recherche-Agent läuft bereits auf `claude_local` mit `claude-sonnet-4-6` (siehe Chatverlauf `2026-05-11 Chatverlauf Recherche-Agent claude_local.md`), `heartbeat: false`, `wakeOnDemand: true`.
- Vault gemounted unter `/Volumes/WHITESTAG-ARCHIV/Obsidian/WHITESTAG-Vault/`. Bei nicht-gemountetem Vault: graceful degradation (alter Sync-Stand bleibt aktiv, kein Schreiben).
- **Auth:** Paperclip läuft in `deploymentMode: "authenticated"`. Externe Scripts authentifizieren sich per **Board-API-Key** (Bearer-Token, Format `pcp_board_<48 hex>`, TTL 30 Tage). Erzeugt über den CLI-Auth-Challenge-Flow: `POST /api/cli-auth/challenges` → returns `boardApiToken` und `approvalUrl` → Walter approved im Browser unter `/cli-auth/<id>?token=<secret>` → Token aktiv. Storage: `~/.paperclip/instances/default/agent-learning.secret` (chmod 600, KEY=VALUE-Format), gelesen via `source` im Trigger-Script, **nie** in der YAML-Config oder im Repo. Rotation: vor Ablauf neuen Challenge anlegen und Secret-File überschreiben.
- **Precondition vor Implementation:** Vault-Maintainer-Adapter zurück auf `lmstudio_local` umstellen (war versehentlich `claude_local`). PATCH `/api/agents/3067ea1d-5050-4032-aff5-1f759f544160` mit `adapterType: lmstudio_local` und entsprechender Modell-Config. (Konkrete Modell-Wahl: in der Plan-Phase festlegen — Walter hat ein lokales LM-Studio-MLX-Setup, Modell entscheidet sich nach Tool-Use-Fähigkeit.)

## Konstanten

| Schlüssel | Wert |
|---|---|
| WHITESTAG Company-ID | `9cebf3cf-efe8-4597-a400-f06488900a87` |
| Health Company-ID | `158c4959-4973-4cb0-8066-55ec0f35625e` |
| Clara Sound Company-ID | `0e426844-309c-4528-9aa5-90ff76790a51` (ausgeschlossen) |
| Online-Recherche Agent-ID | `d80fe6b9-b2ac-4d58-8525-8bbbb1d0caf7` (im WHITESTAG-Vault verifiziert) |
| Vault-Maintainer Agent-ID | `3067ea1d-5050-4032-aff5-1f759f544160` (WHITESTAG) |
| Paperclip API Base | `http://127.0.0.1:3100` |
| Board-API-Key Secret-File | `~/.paperclip/instances/default/agent-learning.secret` (chmod 600) |
| Vault-Root | `/Volumes/WHITESTAG-ARCHIV/Obsidian/WHITESTAG-Vault/` |
| Vault-Knowledge-Dir | `Paperclip/Skill-Wissen/` |
| Vault-Agenten-Dir | `Paperclip/Agenten/<company-slug>/<agent-slug>/` |
| Config-File | `~/.paperclip/instances/default/agent-learning.config.yaml` |
| Trigger-Script | `~/.paperclip/scripts/agent-learning-trigger.sh` |
| Instructions-Root pro Agent | `~/.paperclip/instances/default/companies/<co>/agents/<ag>/instructions/` |

## Architektur — zwei nächtliche Loops

```
KNOWLEDGE-LOOP  (Was gibt's Neues in der Domain?)
  Paperclip-Routine "Recherche-Pass" (Cron 01:00)
    └─ Trigger-Script liest Config, bestimmt heutige Domain-Liste (Wochentag-Rotation)
        └─ Erzeugt 1-2 Issues "Recherche: <skill-domain>"
            └─ assigned → Online-Recherche (claude_local, Sonnet 4.6)
                └─ schreibt nach: Vault/Paperclip/Skill-Wissen/<domain>/...md

LESSONS-LOOP  (Was lief gestern bei den Agenten schief?)
  Paperclip-Routine "Reibungs-Sweep" (Cron 02:00)
    └─ Trigger-Script erzeugt 1 Issue "Lessons aus Reibungs-Runs vom <gestern>"
        └─ assigned → Vault-Maintainer (lmstudio_local)
            ├─ filtert via API: Runs mit status in (failed, errored), letzte 24h,
            │  Companies whitestag + health
            ├─ destilliert pro Reibungs-Run 3-5 Sätze Lesson
            ├─ schreibt: Vault/Paperclip/Agenten/<co-slug>/<ag-slug>/lessons/...md
            └─ Sub-Step: syncht Context-Bundle in jeden Agent-Instructions-Ordner

CONSUMPTION  (Morgens, Agent wacht zu Task auf)
  Agent liest aus seinem instructionsRootPath (managed bundle mode):
    - AGENTS.md (Setup)
    - MEMORY.md (Index, max ~200 Zeilen)
    - recent-lessons.md (Top-5 letzte 14 Tage, Volltext)
    - relevant-knowledge.md (Headlines der Skill-Wissen-Domains, kein Volltext)
  Bei Bedarf: lädt Volltext aus Vault via Read-Tool
```

**Engine-Aufteilung:**

- **Online-Recherche** bleibt einziger Agent auf Claude (Sonnet 4.6 via `claude_local`). Recherche braucht Tool-Use + hochwertige Synthese — lokale Modelle zu brittle.
- **Vault-Maintainer** läuft auf `lmstudio_local` (lokales LLM via LM Studio). Reflexion über Run-Logs ist eher Pattern-Matching + Filterung, dafür reicht ein lokales Modell. Kein Token-Verbrauch gegen Claude-Max-Abo.
- Alle anderen Agenten (CEO, CTO, CMO, CRO, etc.) bleiben auf ihrem aktuellen Adapter.

**Volume-Disziplin (Schutz vor Claude-Max-Quota-Kollision):**

- Knowledge-Loop: **1-2 Domains pro Nacht**, rotierend (siehe Config). Jede Domain wöchentlich einmal frisch.
- Pro Recherche-Run hartes Limit: `maxTurnsPerRun: 30`, `timeoutSec: 600` (10 Min).
- Prompt: *„Nur was sich seit `<last-update>` geändert hat. Wenn nichts Neues mit operativem Impact: Issue auf `done` mit Comment 'no new actionable knowledge'."*

## Storage-Layout im Vault

### Zentrale Wissens-Schicht (eine pro Skill-Domain, geteilt)

```
Paperclip/Skill-Wissen/
  n8n/
    MEMORY.md                              ← Domain-Index, max ~200 Zeilen
    2026-05-n8n-1.92-neue-nodes.md
    2026-05-n8n-credential-changes.md
    _archive/                              ← decay-Pass schiebt hierher
  photoshop/
    MEMORY.md
    2026-05-photoshop-2026-features.md
  blender/
  mistika-vr/
  adobe-cep/
  pyatv/
  homepod-bridge/
  claude-api/
  paperclip-sdk/
  premiere/
  ...
```

### Agent-spezifische Schicht (pro Agent)

```
Paperclip/Agenten/
  whitestag/
    online-recherche/
      MEMORY.md                            ← Index: verlinkt Skill-Wissen + eigene Lessons
      lessons/
        2026-05-10-batch-export-timeout-workaround.md
        2026-05-08-n8n-webhook-auth-fix.md
        _archive/
      references/
        quellen.md                         ← URLs, Doku-Pointer
    vault-maintainer/
    cto/
    bild-und-video/
    cmo/
    ...
  health/
    <health-agenten>/
  _index.md                                ← Slug ↔ UUID ↔ Company mapping
```

**Bewusst ausgeschlossen:** Clara Sound — bekommt später eigenen Vault, keine Files unter `Paperclip/Agenten/clara-sound/` anlegen.

### Slug-Konvention

- Companies: `whitestag`, `health` (lowercase, kein Sonderzeichen)
- Agenten: lowercase kebab-case des Display-Namens. Beispiele:
  - `Online-Recherche` → `online-recherche`
  - `Vault-Maintainer` → `vault-maintainer`
  - `Bild & Video` → `bild-und-video`
  - `CTO` → `cto`

Slug ↔ UUID-Mapping wird von `agent-learning-trigger.sh` initial einmalig aus der Paperclip-API gezogen und in `Paperclip/Agenten/_index.md` geschrieben. Bei Hire eines neuen Agenten wird `_index.md` beim nächsten Trigger-Lauf aktualisiert (idempotent).

### Dateiname-Konvention

- Knowledge: `YYYY-MM-<domain-slug>-<topic-slug>.md`
- Lessons: `YYYY-MM-DD-<run-id-kurz>-<topic-slug>.md` (Datum = Tag des Sweeps, run-id-kurz = erste 8 Hex-Zeichen der Run-UUID)
- MEMORY.md: feste Filename
- _archive/: identische Filename-Konvention, nur in Sub-Folder

### Frontmatter (analog zu Walters bestehendem MEMORY.md-Pattern)

```yaml
---
name: n8n 1.92 — neue Nodes
description: Neue Native-Nodes seit n8n 1.92 (Bedrock, Snowflake, JIRA-Service-Mgmt)
type: knowledge        # knowledge | lesson | reference
domain: n8n            # nur bei type=knowledge
agent: online-recherche
company: whitestag     # nur bei type=lesson
created: 2026-05-11
updated: 2026-05-11    # bei Update durch Dedup-Pass
sources:
  - https://docs.n8n.io/release-notes/#n8n192
---

# n8n 1.92 — neue Nodes

… Inhalt …
```

### MEMORY.md (Agent-Index, max ~200 Zeilen)

```markdown
# Memory Index — Online-Recherche

## Eigene Lessons
- [Batch-Export-Timeout-Workaround](lessons/2026-05-10-…) — bei >500 Files muss …
- [n8n-Webhook-Auth-Fix](lessons/2026-05-08-…) — JWT-Header braucht Bearer-Prefix

## Skill-Wissen (verlinkt)
- [[Paperclip/Skill-Wissen/n8n/MEMORY|n8n-Domain]] — letzte Aktualisierung 2026-05-11
- [[Paperclip/Skill-Wissen/photoshop/MEMORY|Photoshop-Domain]] — letzte Aktualisierung 2026-05-09

## Referenzen
- [Quellen](references/quellen.md)
```

## Config-File

**Pfad:** `~/.paperclip/instances/default/agent-learning.config.yaml`

YAML statt JSON, damit Walter Kommentare hinterlegen kann. Beide Routinen lesen die Datei bei jedem Lauf frisch ein — kein Redeploy nötig nach Edit.

```yaml
# Agent Learning Loops — Config
# Walter darf hier alles anpassen. Routinen lesen die Datei bei jedem Lauf frisch ein.

vault:
  root: /Volumes/WHITESTAG-ARCHIV/Obsidian/WHITESTAG-Vault
  knowledge_dir: Paperclip/Skill-Wissen
  agents_dir: Paperclip/Agenten

companies:
  whitestag:
    id: 9cebf3cf-efe8-4597-a400-f06488900a87
    slug: whitestag
  health:
    id: 158c4959-4973-4cb0-8066-55ec0f35625e
    slug: health
# Clara Sound (0e426844-…) bewusst ausgeschlossen — eigener Vault später

knowledge_loop:
  routine_name: recherche-pass
  schedule: "0 1 * * *"          # täglich 01:00 lokal
  assignee_agent: online-recherche
  max_turns_per_run: 30
  timeout_sec: 600
  rotation:                      # jederzeit anpassbar
    mon: [n8n, photoshop]
    tue: [blender, mistika-vr]
    wed: [adobe-cep, premiere]
    thu: [pyatv, homepod-bridge]
    fri: [claude-api, paperclip-sdk]
    sat: []                      # frei (Catch-up / lange Tail-Themen)
    sun: []                      # frei (manuelle Anfragen)

lessons_loop:
  routine_name: reibungs-sweep
  schedule: "0 2 * * *"          # täglich 02:00 lokal
  assignee_agent: vault-maintainer
  lookback_hours: 24
  trigger_run_statuses: [failed, errored]
  always_pickup_marker: "LESSON-CANDIDATE"   # Override: Comments mit diesem
                                             # Prefix werden IMMER gesweept,
                                             # auch wenn Run-Status nicht failed
  max_runs_per_sweep: 10
  selection_order: newest_first              # bei >10 Reibungs-Runs: neueste zuerst
  skip_if_empty: true

decay_pass:
  schedule: "0 3 * * 0"          # sonntags 03:00 lokal
  knowledge_archive_after_days: 180
  lessons_archive_after_days: 90

budgets:
  memory_md_max_lines: 200       # pro Agent
  knowledge_files_per_domain: 30 # aktiv (Archiv unbegrenzt)
  lessons_per_agent: 50          # aktiv (Archiv unbegrenzt)
  context_bundle_max_tokens: 5000

domains:                         # Metadaten pro Knowledge-Domain
  n8n:
    title: "n8n Workflow Automation"
    sources:
      - https://docs.n8n.io/release-notes/
      - https://community.n8n.io/c/announcements/
    skill_refs: [whitestag-n8n-workflow]
  photoshop:
    title: "Adobe Photoshop"
    sources:
      - https://helpx.adobe.com/photoshop/release-note/photoshop-release-notes.html
    skill_refs: [adobe-automation]
  blender:
    title: "Blender 3D"
    sources:
      - https://www.blender.org/download/releases/
    skill_refs: [blender-scripting]
  mistika-vr:
    title: "Mistika VR"
    sources: []
    skill_refs: [mistika-vr-pipeline]
  adobe-cep:
    title: "Adobe CEP / UXP Extensions"
    sources:
      - https://github.com/Adobe-CEP/CEP-Resources/releases
    skill_refs: [adobe-automation]
  premiere:
    title: "Adobe Premiere Pro"
    sources:
      - https://helpx.adobe.com/premiere-pro/release-note/premiere-pro-release-notes.html
    skill_refs: []
  pyatv:
    title: "pyatv — Apple TV / HomePod direkt-streamen"
    sources:
      - https://pyatv.dev/
      - https://github.com/postlund/pyatv/releases
    skill_refs: []
  homepod-bridge:
    title: "HomePod-Bridge (Paperclip → HomePod Voice)"
    sources: []
    skill_refs: []
  claude-api:
    title: "Anthropic Claude API & SDK"
    sources:
      - https://docs.anthropic.com/en/release-notes
    skill_refs: [claude-api]
  paperclip-sdk:
    title: "Paperclip Plugin SDK"
    sources: []
    skill_refs: [paperclip, paperclip-create-plugin]
```

## Routinen & Trigger

### Cron-Mechanik

Statt direkte Cron-Einträge nutzen wir das `schedule`-Skill bzw. CronCreate, um drei Paperclip-Routinen anzulegen, die jeweils ein generisches Trigger-Script aufrufen:

1. `recherche-pass` (Cron `0 1 * * *`) → ruft `agent-learning-trigger.sh knowledge`
2. `reibungs-sweep` (Cron `0 2 * * *`) → ruft `agent-learning-trigger.sh lessons`
3. `decay-pass` (Cron `0 3 * * 0`) → ruft `agent-learning-trigger.sh decay`

Das Trigger-Script ist in Bash + jq + curl geschrieben (keine neuen Sprach-Dependencies), liest die Config via `yq`, und nutzt die Paperclip-REST-API, um Issues zu erzeugen.

### Trigger-Script — Pseudo-Code

```bash
#!/bin/bash
# ~/.paperclip/scripts/agent-learning-trigger.sh
# Aufrufe: knowledge | lessons | decay

set -euo pipefail
CONFIG="$HOME/.paperclip/instances/default/agent-learning.config.yaml"
MODE="$1"

case "$MODE" in
  knowledge)
    # Wochentag → Domain-Liste aus rotation.<weekday>
    # Für jede Domain: POST /api/companies/<whitestag-id>/issues mit
    #   title:   "Recherche: <domain.title> — Neuerungen seit <last-update>"
    #   body:    Template mit domain.sources, vault-pfad, dedup-anweisung
    #   assignee: <online-recherche-agent-id>
    ;;
  lessons)
    # Lookback: GET /api/runs?status=failed,errored&since=<24h-ago>
    # Filter: Companies whitestag + health
    # Pro Reibungs-Run (max max_runs_per_sweep):
    #   Activity-Log + Comments holen
    # POST /api/companies/<whitestag-id>/issues mit
    #   title:   "Lessons aus Reibungs-Runs vom <gestern>"
    #   body:    JSON-Liste der Reibungs-Runs + vault-Pfade pro Agent
    #   assignee: <vault-maintainer-id>
    ;;
  decay)
    # Iteriere über alle Files in Paperclip/Skill-Wissen/ und Paperclip/Agenten/.../lessons/
    # Wenn mtime/frontmatter-created > N Tage → move zu _archive/
    # Update MEMORY.md-Indices entsprechend
    # (Decay läuft offline ohne Agent — pure Filesystem-Logik)
    ;;
esac
```

### Issue-Body-Template (Knowledge-Issue)

```markdown
**Domain:** {{domain.title}}
**Quellen:** {{domain.sources}}
**Vault-Pfad:** /Volumes/WHITESTAG-ARCHIV/Obsidian/WHITESTAG-Vault/Paperclip/Skill-Wissen/{{domain.slug}}/

## Auftrag

Recherchiere, was sich bei {{domain.title}} seit {{last-update-date}} geändert hat. Konzentriere dich auf Neuerungen mit **operativem Impact** — also Features/Changes, die wir in unseren Workflows nutzen könnten oder die bestehende Workflows brechen.

## Schreib-Regeln

1. **Dedup zuerst:** Liste existierende Files im Vault-Pfad. Wenn ein Topic schon existiert → bestehende Datei updaten (`updated:` im Frontmatter), keine neue Datei anlegen.
2. **Quality-Gate:** Schreibe nur, wenn die Information non-obvious / surprising / actionable ist. Generische Release-Listen ohne operative Konsequenz nicht schreiben — Issue auf `done` mit Comment "no new actionable knowledge".
3. **Frontmatter-Pflicht:** type, domain, agent, created, sources (siehe Spec).
4. **MEMORY.md aktualisieren:** nach jedem Knowledge-File-Write den Domain-Index in `{{vault-pfad}}/MEMORY.md` aktualisieren.

## Constraints

- Max 30 Turns, Max 10 Min.
- Web-Recherche erlaubt (WebFetch/WebSearch).
- Wenn unsicher → kein Eintrag besser als ein schlechter Eintrag.
```

### Issue-Body-Template (Lessons-Issue)

```markdown
**Reibungs-Runs vom {{gestern}}:**

{{für jeden Run:}}
- Run `{{run-id}}` — Agent `{{agent-name}}` — Company `{{company-name}}` — Status `{{status}}` — Issue `{{issue-title}}`
  - Vault-Pfad für Lessons: /Volumes/WHITESTAG-ARCHIV/Obsidian/WHITESTAG-Vault/Paperclip/Agenten/{{company-slug}}/{{agent-slug}}/lessons/
  - Activity-Log-Snippet: `{{first-error-line}}`

## Auftrag

Für jeden Reibungs-Run oben:

1. Hole das vollständige Activity-Log via `GET /api/runs/{{run-id}}/activity` und Comments via `GET /api/issues/{{issue-id}}/comments`.
2. Destilliere in 3-5 Sätzen: **Was ist passiert? Warum? Was sollte der Agent beim nächsten Mal anders machen?**
3. Schreibe das Lesson nach `{{vault-pfad}}/{{datum}}-{{run-id-kurz}}-{{topic-slug}}.md` mit Frontmatter (type: lesson, agent, company, created, sources=[run-id]).
4. Aktualisiere `{{vault-pfad}}/../MEMORY.md` (Agent-Index) — füge Lesson-Eintrag oben in der Lessons-Liste hinzu.

## Sub-Step nach allen Lessons

Sync Context-Bundle in jeden Agent-Instructions-Ordner:

Für jeden Agent in (whitestag, health):
  Kopiere {{vault-agent-pfad}}/MEMORY.md  → instructions/MEMORY.md
  Erstelle instructions/recent-lessons.md (Top-5 lessons, letzte 14 Tage, Volltext)
  Erstelle instructions/relevant-knowledge.md (Headlines aus verlinkten Skill-Wissen-MEMORY.md, kein Volltext)

## Constraints

- Wenn `trigger_run_statuses` leer ist und keine Reibungs-Runs gefunden → Issue auf `done` mit Comment "no friction yesterday, nothing to learn".
- Max max_runs_per_sweep Runs (siehe Config).
- Vault nicht gemounted → Issue auf `blocked` mit Comment, kein Schreiben.
```

### Manuelle Trigger

Zusätzlich zur Cron-Routine kann Walter jederzeit ad-hoc:

- Ein Issue „Recherche: `<thema>`" in der WHITESTAG-Company anlegen und Online-Recherche zuweisen → läuft sofort, ohne auf 01:00 zu warten. Body sollte Vault-Pfad enthalten.
- Genauso „Lessons: `<agent>`" für gezielte Reflexion über die letzten N Runs eines bestimmten Agenten.

### Observability

- Trigger-Script schreibt nach jedem Lauf einen kurzen Status-Eintrag in `Paperclip/Agenten/_status.md`:
  ```
  ## 2026-05-12 01:00 — Recherche-Pass
  - n8n: 2 Knowledge-Files aktualisiert, 0 neu
  - photoshop: 1 neu, MEMORY.md aktualisiert
  ```
- Failed Runs der Recherche-/Lessons-Routinen tauchen automatisch beim nächsten Reibungs-Sweep auf → die Loops lernen rekursiv aus eigenen Fehlern.

## Load-Mechanismus

**Sync statt Symlink.** Vault-Maintainer schreibt am Ende des nächtlichen Sweeps einen schlanken Context-Bundle in jeden Agent-Instructions-Ordner (`~/.paperclip/instances/default/companies/<co>/agents/<ag>/instructions/`). Paperclip's `instructionsBundleMode: managed` zieht den Bundle dann beim nächsten Run automatisch in den Agent-Context.

### Was im Bundle landet (pro Agent, Budget ~5k Tokens)

```
instructions/
  AGENTS.md                    ← unverändert (vom Agent-Setup)
  MEMORY.md                    ← copy aus Vault, max 200 Zeilen
  recent-lessons.md            ← Top-5 Lessons der letzten 14 Tage (Volltext)
  relevant-knowledge.md        ← Headlines (kein Volltext) der Skill-Wissen-Domains,
                                 die laut MEMORY.md verlinkt sind
```

Volltexte der Knowledge-Files bleiben im Vault — der Agent kann sie via Read-Tool nachladen, wenn er sie braucht. Spart Tokens auf jedem Run, fügt sie aber nicht stumm in den Context.

### Sync-Flow

```
02:00  Vault-Maintainer schreibt Lessons in den Vault    (source of truth)
02:30  Sub-Step: bundle pro Agent in dessen instructions/ schreiben
03:00  Status-Eintrag in Paperclip/Agenten/_status.md
```

### AGENTS.md-Snippet pro Agent (einmalig, manuell oder via Hire-Script)

Wird in `instructions/AGENTS.md` ergänzt:

```markdown
## Gedächtnis & Lernen

Beim Task-Start: lies `MEMORY.md` und `recent-lessons.md` in deinem
Instructions-Ordner. Diese enthalten dein gesammeltes Wissen aus
vorherigen Tasks und nächtlicher Recherche.

Wenn ein Eintrag aus `relevant-knowledge.md` für deine aktuelle Task
relevant ist, lade die vollständige Datei aus dem Vault nach:
`/Volumes/WHITESTAG-ARCHIV/Obsidian/WHITESTAG-Vault/Paperclip/Skill-Wissen/<domain>/...`

Wenn du beim Task auf eine echte Reibung stößt (Tool-Error, unklare
Anweisung, fehlende Dependency), markiere das im Run-Comment explizit
als "LESSON-CANDIDATE: <kurz>" — der nächtliche Reibungs-Sweep destilliert
daraus eine Lesson.
```

### Graceful Degradation bei nicht-gemountetem Vault

- Vault-Maintainer überspringt den Sweep mit Comment „Vault not mounted, skipping" → Issue auf `blocked`.
- Alter Bundle-Stand bleibt im Instructions-Ordner stehen — Agenten arbeiten weiter mit letztem gesyncten Stand.
- Beim nächsten erfolgreichen Sweep wird automatisch wieder synchronisiert.

### Edge Case: lmstudio-Agenten ohne Filesystem-Read-Tool

Falls ein Agent kein Filesystem-Read kann (manche LM-Studio-Modelle ohne Tool-Use), kriegt er Volltexte direkt in den Bundle injiziert. Config-Flag pro Agent (optional, default: index-only):

```yaml
agents:
  cmo:
    bundle_mode: full-text     # statt index-only (default)
```

Bei `full-text` werden auch die Knowledge-File-Volltexte (gefiltert auf relevante Domains) in den Bundle gespiegelt. Trade-off: höherer Context, dafür Agent ohne Read-Tool funktionsfähig.

## Anti-Bloat

Vier ineinandergreifende Mechanismen verhindern, dass Vault, MEMORY.md oder Context-Bundles aufschwellen:

### 1. Quality-Gate beim Schreiben

Online-Recherche und Vault-Maintainer schreiben **nur**, wenn ein Eintrag *non-obvious / surprising / actionable* ist (gleiche Regel wie Walters bestehendes auto-memory-Pattern). Generisches „n8n 1.92 veröffentlicht" ohne operative Konsequenz → nicht schreiben.

Im Issue-Body explizit als Anweisung (siehe Templates oben).

### 2. Dedup vor Write

Vor dem Schreiben einer neuen Datei:

1. Agent listet existing Files im Zielordner (`ls vault/Skill-Wissen/<domain>/`)
2. Prüft per Titel + Frontmatter-Description auf Duplikat
3. Wenn ähnlich → **bestehende Datei updaten** (frontmatter `updated:`-Feld setzen), nicht neue anlegen

Verhindert Variationen wie `n8n-1.92-features.md`, `n8n-1.92-features-v2.md`, `n8n-1.92-real-features.md`.

### 3. Decay-Pass (sonntags)

Trigger-Script `agent-learning-trigger.sh decay` läuft sonntags 03:00 (nach beiden Loops). Iteriert über alle aktiven Files:

- **Knowledge** älter `decay_pass.knowledge_archive_after_days` (default 180) ohne `updated:`-Aktualisierung → move nach `<domain>/_archive/`
- **Lessons** älter `decay_pass.lessons_archive_after_days` (default 90) ohne Referenz im aktuellen MEMORY.md → move nach `lessons/_archive/`
- MEMORY.md-Indices werden entsprechend gepatcht (archivierte Einträge entfernt)
- Archivierte Files bleiben physisch im Vault → Walter kann sie in Obsidian lesen und ggf. manuell zurückholen
- Manuelle Moves von Walter (Datei aus `_archive/` rauszieht) werden via mtime-Vergleich respektiert — Decay-Pass touched manuell zurückgeholte Files nicht erneut

### 4. Hard-Size-Budgets

Wenn ein Limit aus `budgets:` überschritten wird, **erzwingt** das Trigger-Script Konsolidierung:

- MEMORY.md > 200 Zeilen → ältester 20% der Einträge wird zu Umbrella-Einträgen zusammengefasst, Einzel-Files archiviert (Vault-Maintainer-Job)
- Knowledge-Files > 30 pro Domain → ältere zu Quartals-Übersichten zusammengeführt
- Lessons > 50 pro Agent → ältere zu Pattern-Übersichten zusammengeführt
- Context-Bundle > 5000 Tokens → recent-lessons auf Top-3 reduziert, dann auf Top-1

### Skills bleiben eingefroren

**Wichtig:** Skill-Files (`~/.claude/skills/<name>/SKILL.md`, `whitestag-n8n-workflow/SKILL.md`, etc.) werden von diesem System **niemals automatisch erweitert**. Skills sind „so arbeite ich" — eingefroren bis zur manuellen Promotion durch Walter.

Wenn ein Vault-Eintrag häufig referenziert wird und tatsächlich Kern-Pattern wird → Walter promotet ihn manuell in den Skill. Kein Agent darf das selbst tun. Damit löst sich die Original-Sorge, dass Skills durch nächtliches Lernen aufschwellen: das Wissen geht in den Vault, **nicht** in den Skill.

### Monatlicher Review-Checkpoint

1. eines Monats erzeugt das Trigger-Script ein zusätzliches Issue „Memory-Review `<YYYY-MM>`" assigned to Walter mit Diff:

- Neue Knowledge-Files in jeder Domain (Anzahl + Titel)
- Neue Lessons pro Agent (Anzahl + Titel)
- Was wurde archiviert (Anzahl)
- Welche Knowledge-Domains hatten keinen Update letzten Monat (Hinweis: ggf. aus Rotation entfernen)

Walter kann in Obsidian Einzelne aus `_archive/` zurückholen oder Promotionen in Skills durchführen.

## Edge Cases

- **Wake-On-Demand-Verhalten:** Online-Recherche und Vault-Maintainer haben `heartbeat: false, wakeOnDemand: true`. Das Trigger-Script muss daher nicht nur Issues erzeugen, sondern auch sicherstellen, dass die Agenten geweckt werden — entweder via Issue-Assign-Event (Paperclip-Standardverhalten) oder explizit via `POST /api/agents/<id>/wake`. In der Plan-Phase verifizieren, ob Issue-Assignment allein als Wake-Trigger reicht.
- **Doppelter Lauf bei System-Reboot:** Wenn das Trigger-Script zwei Mal am gleichen Tag läuft (z.B. nach manuellem Re-Trigger), erzeugt es kein doppeltes Issue — Idempotenz über Issue-Titel-Match in der letzten 24h.
- **Online-Recherche im fehlerhaften Zustand:** Wenn Online-Recherche selbst auf `failed`-Runs läuft, fängt der Reibungs-Sweep das ab und schreibt eine Lesson über die eigene Knowledge-Loop. Rekursives Lernen.
- **Concurrent Writes in MEMORY.md:** Wenn zwei Recherche-Runs parallel laufen und beide MEMORY.md derselben Domain updaten wollen → File-Lock via `flock`-Wrapper im Trigger-Script. Bei Konflikt: zweiter Run wartet bis 60s, dann retry.
- **Health-Company-ID übernommen aus Pushover-Watch-Spec:** Die Health Company-ID (`158c4959-…`) stammt aus `2026-05-11-pushover-watch-plugin-design.md`. Vor Implementation per `GET /api/companies` gegenchecken.
- **Skill-Refs ohne installiertes Skill:** Wenn `domains.<x>.skill_refs` ein Skill nennt, das nicht installiert ist, fällt der Recherche-Lauf trotzdem nicht aus — die Knowledge-Files werden geschrieben, nur die Verlinkung im MEMORY.md zeigt ins Leere. Decay-Pass markiert das beim nächsten Lauf.

## Out of Scope

- **Clara Sound:** Bekommt später eigenen Vault, keine Files unter `Paperclip/Agenten/clara-sound/`.
- **Cross-Agent-Wissens-Transfer:** Wenn Agent A eine Lesson schreibt, die für Agent B nützlich wäre, übernimmt das aktuell nicht automatisch. Walter müsste manuell verlinken oder die Lesson nach `Skill-Wissen/<domain>/` promoten.
- **Conversational Memory:** Erinnerungen über frühere Chat-Verläufe mit Walter werden weiterhin über sein bestehendes `~/.claude/projects/.../memory/`-System gepflegt, **nicht** über dieses Agent-Learning-System.
- **Skill-Auto-Update:** Skills werden niemals automatisch erweitert. Nur manuelle Promotion durch Walter.
- **Hot-Reload der Config:** Config wird bei jedem Routine-Lauf neu gelesen, aber Änderungen am Cron-Schedule selbst (Cron-Expression) erfordern manuelle Aktualisierung der CronCreate-Routinen via `schedule`-Skill.

## Offene Punkte (zur Klärung in der Planungsphase)

- **Welche Health-Agenten existieren?** Spec listet sie generisch — die Liste muss vor Initial-Bundle-Erzeugung aus der Paperclip-API gezogen werden.
- **Welche Skill-Refs sind aktuell installiert?** Die `skill_refs:` in der Config sind beste Schätzung — manuell vor erstem Lauf verifizieren via `ls ~/.claude/skills/`.
- **WebSearch/WebFetch-Berechtigung für Online-Recherche:** muss in der `adapterConfig` bzw. via Tools-Whitelist gewährleistet sein. Vor erstem Recherche-Lauf testen.
- **Initial-Backfill:** Soll das erste Sync den Bundle für *alle* Agenten erzeugen (auch wenn der Vault noch leer ist)? Vorschlag: Ja — leere MEMORY.md mit Placeholder-Text, damit die `instructions/MEMORY.md`-Datei existiert und der Agent sie nicht als „missing" interpretiert.
