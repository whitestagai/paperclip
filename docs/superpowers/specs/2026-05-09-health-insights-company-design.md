# Design: Health Insights Company (Paperclip)

**Status:** Draft
**Datum:** 2026-05-09
**Autor:** Walter Schönenbröcher mit Claude Code

## Ziel & Kontext

Walter exportiert via Health Auto Export Apple-Health-Daten vom iPhone. Eine spezialisierte Paperclip-Company soll diese Daten analysieren, tägliche Briefings liefern, wöchentliche Trends aufzeigen, Anomalien erkennen und Ad-hoc-Fragen beantworten. **Alle LLM-Inferenz läuft lokal** (LM Studio), kein Cloud-Provider sieht Gesundheitsdaten.

## Anforderungen (aus Brainstorming)

- **Tägliches Briefing** mit Schlaf-, Trainings- und Vitalwert-Status
- **Wöchentlicher Trend-Report** mit längerfristigen Mustern
- **Anomalie-Erkennung** mit deterministischer Vorfilterung + LLM-Sanity-Check
- **Ad-hoc Q&A** im Paperclip-Chat
- **Datenpipeline:** iCloud Drive Sync (einfachster Weg, schon vorhanden)
- **Metriken-Scope:** Schlaf, Aktivität/Training, Vitalwerte (volle Breite)
- **Interaktion:** Paperclip-UI + Obsidian-Tagesprotokoll + n8n→Telegram, vorbereitend für Spracheingabe
- **Agent-Struktur:** Multi-Agent-Company mit Spezialisten

## Architektur-Übersicht

Drei austauschbare Schichten:

1. **Ingestion** — n8n liest neue Files aus iCloud, validiert, dedupliziert
2. **Storage** — Postgres als Source of Truth + Markdown als View-Layer
3. **Reasoning** — Health-Insights-Company in Paperclip mit lokalem LLM

```
iPhone (Health Auto Export)
   → iCloud Drive
   → n8n Ingest-Workflow
   → Postgres (raw + daily aggregates) + Markdown (data/daily/, data/weekly/)
   → Paperclip Health Company (CHO + Schlafcoach + Trainingscoach + Vitals-Monitor)
   → Paperclip-Issues + Obsidian + n8n→Telegram
```

## Datenpipeline

### Health Auto Export (iPhone)

- Automation täglich 06:00 Uhr
- Export-Format: **JSON** (strukturierter als CSV, behält Sample-Granularität)
- Aggregation: stündlich für Pulse/HRV, sonst pro Sample
- Ziel: iCloud Drive `Apps/Health Auto Export/`

### n8n Workflow `health-ingest V1`

- **Trigger:** File-Watcher auf iCloud-Ordner; Fallback Cron alle 30 min
- **Schritte:**
  1. Lese neue/geänderte JSON-Files
  2. Validiere Schema (Health Auto Export hat ein bekanntes Format)
  3. Dedupliziere gegen Postgres via Unique-Key `(metric, source, start_ts)`
  4. Schreibe Rohdaten in Postgres `health_samples`
  5. Berechne Tages-Aggregate, schreibe `health_daily` und Markdown-Daily
  6. Bei Wochenende: Markdown-Wochenaggregat (`data/weekly/<ISO-Woche>.md`); Wochenstats werden on-demand aus `health_daily` aggregiert (keine separate `health_weekly`-Tabelle)
  7. Z-Score-Anomalie-Erkennung (siehe unten), Flags in `health_anomaly_flags`
  8. Bei `severity = alert` Flag: sofortiges Issue an CHO + Telegram

### Postgres-Schema (DB `health`, Schema `paperclip_health`)

```sql
CREATE TABLE health_samples (
  id BIGSERIAL PRIMARY KEY,
  metric VARCHAR(64) NOT NULL,
  source VARCHAR(64),
  start_ts TIMESTAMPTZ NOT NULL,
  end_ts TIMESTAMPTZ,
  value DOUBLE PRECISION,
  unit VARCHAR(32),
  raw JSONB,
  ingested_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (metric, source, start_ts)
);
CREATE INDEX ON health_samples (metric, start_ts DESC);
CREATE INDEX ON health_samples USING BRIN (start_ts);

CREATE TABLE health_daily (
  date DATE NOT NULL,
  metric VARCHAR(64) NOT NULL,
  min DOUBLE PRECISION,
  max DOUBLE PRECISION,
  avg DOUBLE PRECISION,
  sum DOUBLE PRECISION,
  count INTEGER,
  computed_at TIMESTAMPTZ DEFAULT NOW(),
  PRIMARY KEY (date, metric)
);

CREATE TABLE health_workouts (
  id BIGSERIAL PRIMARY KEY,
  start_ts TIMESTAMPTZ NOT NULL,
  end_ts TIMESTAMPTZ NOT NULL,
  type VARCHAR(64),
  duration_sec INTEGER,
  active_energy_kcal DOUBLE PRECISION,
  distance_m DOUBLE PRECISION,
  avg_hr DOUBLE PRECISION,
  raw JSONB,
  UNIQUE (start_ts, type)
);

CREATE TABLE health_anomaly_flags (
  id BIGSERIAL PRIMARY KEY,
  detected_at TIMESTAMPTZ DEFAULT NOW(),
  metric VARCHAR(64),
  date DATE,
  value DOUBLE PRECISION,
  baseline_avg DOUBLE PRECISION,
  z_score DOUBLE PRECISION,
  rule VARCHAR(64),
  severity VARCHAR(16),
  reviewed_by_agent BOOLEAN DEFAULT FALSE,
  agent_classification VARCHAR(32),
  agent_note TEXT
);
```

### Markdown-Layout

Basisverzeichnis: `~/SynologyDrive/2026/AI/Claude Code/Paperclip/projekte/health-insights/data/` (finaler Pfad in Phase 1 fixiert):

```
data/
  daily/
    2026-05-09.md      # ein File pro Tag, ~1-2KB
  weekly/
    2026-W19.md        # ISO-Woche
```

Jedes Daily-MD hat eine **feste Struktur** (Schlaf-Block, Training-Block, Vitals-Block) für verlässliches LLM-Reasoning.

### Designentscheidungen

- **Postgres = Source of Truth.** Markdown ist nur eine reproduzierbare View — kann jederzeit aus DB neu erzeugt werden.
- **JSONB für `raw`:** Erlaubt nachträgliches Erweitern ohne Schema-Migration.
- **Dedup über Unique-Key:** Health Auto Export überlappt Zeiträume bei jedem Export.
- **BRIN-Index auf `start_ts`:** Effizient für Time-Range-Queries auf Append-Only-Daten.

## Health Insights Company

### Agenten

| Agent | Rolle | Kern-Aufgaben |
|---|---|---|
| **CHO** (Chief Health Officer) | Lead/Router | Tägliches Briefing orchestrieren, Q&A-Routing, Wochen-Report |
| **Schlafcoach** | Schlaf & Erholung | Schlafphasen, HRV-Trends, Ruhepuls, Atemfrequenz, Erholungsstatus |
| **Trainingscoach** | Aktivität & Performance | Workouts, Trainingsbelastung (ATL/CTL/TSB), Schritte, VO2max |
| **Vitals-Monitor** | Vitalwerte & Anomalien | Tagesherzfrequenz, Blutdruck, SpO2, Körpertemperatur, Anomalie-Review |

**Begründung der Aufteilung:**

- Kompakter, fokussierter Prompt pro Spezialist → besser für lokales LLM
- CHO sieht nur Spezialisten-Zusammenfassungen, nicht Rohdaten → spart Kontext
- Pro Spezialist eigene Skills/Heuristiken möglich (Trainingscoach kennt ATL/CTL, Schlafcoach kennt Schlafarchitektur)

### Datenzugriff

- Alle Spezialisten: lesender Zugriff auf Markdown-Daily/Weekly via Read-Tool
- Alle Spezialisten: MCP-Tool-Zugriff auf Postgres für Drilldown
- Schreibrechte: nur in eigene Issue/Task-Outputs, kein direkter DB-Write

### Bewusst weggelassen

- Kein Ernährungs-Agent (Health Auto Export liefert dafür kaum Daten)
- Kein eigener Stress-Agent (überlappt mit Schlaf/HRV)
- Keine Coach-zu-Coach-Diskussion ohne CHO (vermeidet Agent-Loops)

## MCP-Server `paperclip-health-mcp`

Lokaler Python-MCP-Server (systemd/launchd-Service), bietet Postgres-Drilldown-Tools.

| Tool | Zweck |
|---|---|
| `get_metric_range(metric, from, to, agg)` | Zeitreihe einer Metrik, optional aggregiert |
| `get_daily_summary(date)` | Aggregierte Werte aller Metriken für einen Tag |
| `get_workouts(from, to, type?)` | Workout-Liste in Zeitraum |
| `compare_periods(metric, period_a, period_b)` | Vergleich zweier Zeiträume |
| `get_correlations(metric_a, metric_b, days)` | Pearson-Korrelation zweier Metriken |
| `get_anomaly_flags(from, to)` | Liest Anomalie-Flags |
| `list_metrics()` | Verfügbare Metriken (Discovery) |

**Wichtig:** Tools liefern strukturierte JSON-Antworten **mit Stats und Trend**, nicht Rohdaten. Ein einziger Tool-Call liefert dem LLM Stats, Trend und Tageswerte kompakt.

Beispiel-Antwort `get_metric_range`:

```json
{
  "metric": "hrv_sdnn",
  "from": "2026-04-09", "to": "2026-05-09",
  "agg": "daily",
  "stats": {"min": 32, "max": 68, "median": 48, "mean": 47.2, "stddev": 8.3, "count": 30},
  "trend": {"slope_per_day": -0.12, "direction": "slightly_declining"},
  "values": [{"date": "2026-04-09", "value": 52}]
}
```

## Daily Briefing Flow

**Trigger:** Paperclip-Routine, cron `0 7 * * *`. Gate: erst feuern, wenn n8n den heutigen Daily-MD geschrieben hat. Implementierung: n8n schreibt nach erfolgreichem Daily-Aggregat eine Marker-Datei `data/daily/<heute>.ready` oder setzt eine Spalte `health_ingest_runs(date, status='ready')`. Routine pollt diesen Marker bis 09:00; danach Failover-Briefing mit Hinweis "Daten unvollständig".

**Sequenz:**

1. CHO liest `data/daily/<heute>.md` und `data/weekly/<aktuelle-woche>.md` als Snapshot
2. CHO erstellt drei Subtasks (Paperclip-Task-Delegation):
   - "Schlafcoach: Bewerte letzte Nacht im Kontext der letzten 14 Tage"
   - "Trainingscoach: Bewerte gestrige Aktivität, Empfehlung für heute"
   - "Vitals-Monitor: Auffälligkeiten in den letzten 24h?"
3. Spezialisten arbeiten parallel; lesen Daily-MD, rufen bei Bedarf MCP-Tools, antworten in striktem Format
4. CHO konsolidiert zu einem Briefing-Markdown
5. Distribution parallel:
   - Paperclip-Issue im Health-Company-Posteingang anlegen (immer)
   - Obsidian-Tagesprotokoll: Abschnitt `## Health` ergänzen (wenn Datei existiert; nicht neu anlegen)
   - n8n-Webhook → Telegram

### Antwortformat der Spezialisten (verbindlich)

```markdown
### {Spezialist}: {Status-Emoji}{kurzer Status}

**Kennzahlen (heute vs. 14d-Median):**
- Schlafdauer: 7h12 (Median 7h05) ↑
- HRV: 48ms (Median 52ms) ↓

**Trend:** {1 Satz}

**Empfehlung:** {1-2 Sätze, konkret und actionable}
```

### Konsolidiertes Briefing-Format

```markdown
# Health Briefing — 2026-05-09

**Gesamtstatus:** 🟡 Solide, aber HRV signalisiert leichte Unterstütztheit

## Schlaf
{Block vom Schlafcoach}

## Training
{Block vom Trainingscoach}

## Vitals
{Block vom Vitals-Monitor}

## Empfehlung des Tages
{Synthese vom CHO, max 3 Sätze}
```

### Fehlerfälle

- **Daten heute fehlen:** CHO postet Issue "Daten fehlen — bitte iCloud-Sync prüfen", keine Spezialisten-Subtasks
- **Ein Spezialist failt:** Briefing trotzdem mit verfügbaren Spezialisten + Hinweis im Issue
- **Lokales LLM nicht verfügbar:** Routine retried 3× mit Abstand, dann Fehler-Notification

## Weekly Trend Report

- **Trigger:** Paperclip-Routine, sonntags 20:00 (`0 20 * * 0`)
- **Daten-Basis:** `data/weekly/<ISO-Woche>.md` + Postgres-Drilldowns für 4-/12-Wochen-Vergleiche
- **CHO delegiert** an Spezialisten: "Wochenanalyse + Trend gegen letzte 4 Wochen"
- **Zusätzlicher Trend-Block** in der Spezialisten-Antwort:
  - Welche Metrik signifikant gestiegen/gefallen?
  - Welche Korrelation auffällig?
  - Was empfehle ich für nächste Woche?
- **Output:** Längeres Markdown als Paperclip-Issue (keine Push-Notification)

## Anomalie-Erkennung

Zwei Stufen — rein-LLM-basierte Erkennung wäre weder verlässlich noch günstig.

### Stufe 1 — Deterministisch in n8n (jeder Ingest-Run)

- Z-Score gegen rolling 30-Tage-Baseline pro Metrik
- Schwelle: |z| > 2.5 → Flag
- Hard-Limits zusätzlich (z.B. Ruhepuls > 90, HRV-Drop > 30% gegen 7d-Median)
- Output: `health_anomaly_flags`-Tabelle mit `severity` (`info`/`warn`/`alert`)

### Stufe 2 — LLM-Bewertung (Vitals-Monitor)

- Liest Flags `WHERE reviewed_by_agent = FALSE`
- Pro Flag: "Wirklich auffällig oder erklärbar (Training gestern, Krankheit, Reise)?"
- Kontext-Tools: `get_recent_workouts(days)`; später ggf. Kalender-Events
- Klassifiziert: `false_positive` | `noted` | `alert`
- Markiert `reviewed_by_agent = TRUE`, schreibt `agent_classification` + `agent_note`

### Notification-Routing

| Klassifikation | Aktion |
|---|---|
| `false_positive` | still |
| `noted` | wandert ins nächste Daily-Briefing |
| `alert` | sofort Telegram-Push + Paperclip-Issue Priority "high" |

### Bewusst weggelassen

- Keine ML-Modelle (Isolation Forest, Autoencoder etc.) — Z-Score reicht für persönliche Daten
- Keine Verknüpfung mit medizinischer Literatur — der Agent gibt **keine Diagnose**, nur Beobachtungen mit Empfehlung "ggf. ärztlich abklären"

## Q&A Flow

Walter fragt im Paperclip-Chat eines Health-Agenten:

- **An CHO**, wenn unklar/breit ("Wie bin ich diesen Monat drauf?")
- **Direkt an Spezialisten**, wenn fokussiert ("Schlafcoach: Wie war die Erholung?")

CHO darf bei Bedarf einmalig delegieren (Subtask), kein endloses Hin-und-Her.

## Notification Channels

| Channel | Trigger | Inhalt |
|---|---|---|
| **Paperclip-Issue** | Pflicht für jedes Briefing/Alert | strukturiertes Markdown |
| **Obsidian-Tagesprotokoll** | nach Briefing-Erstellung | Abschnitt `## Health`; Datei wird **nicht** neu angelegt |
| **n8n → Telegram** | Briefing (still) + Alert (Sound) | kompakte Zusammenfassung |
| **Spracheingabe** (später) | Hook über Paperclip-REST | (vorbereitet, nicht implementiert) |

n8n-Workflow `paperclip-health-notify V1` empfängt POST `{kind, title, body, severity}` und routet an Telegram.

## Privacy & Local-LLM

- **Datenfluss komplett lokal:** iCloud (Apple-verschlüsselt) → Mac → Postgres → MCP-Server → LM Studio (localhost)
- **Kein** Cloud-LLM, **keine** externe Telemetrie
- **LM Studio:** Walter wählt; Empfehlung Llama 3.1 70B oder Qwen 2.5 32B (Tool-Use-fähig)
- **Telegram-Notifications:** Daten verlassen das Gerät als **Zusammenfassung** im privaten Channel; Alternative `osascript`-Notifications wenn das nicht akzeptabel ist
- **Backup:** tägliches `pg_dump` nach SynologyDrive; Markdowns leben sowieso auf SynologyDrive

### Disclaimer im CHO-System-Prompt (verbindlich)

> "Du bist kein Arzt. Du gibst keine Diagnose. Bei auffälligen Werten empfiehlst du, einen Arzt zu konsultieren — und triffst keine medizinischen Entscheidungen."

## MVP-Phasen

### Phase 1 — Datenpipeline + Q&A

- Health Auto Export einrichten, iCloud-Export läuft
- Postgres-Schema anlegen, n8n-Ingest-Workflow `health-ingest V1`
- MCP-Server mit Top-3-Tools: `get_daily_summary`, `get_metric_range`, `get_workouts`
- **Ein Health-Generalist** in einer Health-Company, kann Q&A
- **Validierung:** "Wie war mein Schlaf gestern?" liefert sinnvolle Antworten

### Phase 2 — Spezialisten + Daily Briefing

- Generalist aufteilen in CHO + Schlafcoach + Trainingscoach + Vitals-Monitor
- Daily-Briefing-Routine + Markdown-Tagessummaries
- Obsidian-Tagesprotokoll-Integration

### Phase 3 — Anomalie-Erkennung + Notifications

- Z-Score-Anomaly-Detection in n8n
- Vitals-Monitor reviewt Flags
- n8n → Telegram für Alerts + Briefings

### Phase 4 — Weekly Reports + Drilldown-Tools

- Weekly-Routine
- Erweiterte MCP-Tools: `compare_periods`, `get_correlations`

### Phase 5 — optional, später

- Spracheingabe-Hook
- Weitere Korrelationen, ggf. Kalenderkontext

Jede Phase ist für sich produktiv nutzbar.

## Offene Fragen / Spätere Entscheidungen

- **Health Auto Export Lizenz:** Free-Version reicht für JSON-Export; falls Automatisierungs-Limits stören, ggf. Paid
- **Konkretes lokales LLM-Modell:** wird in Phase 1 anhand Tool-Use-Qualität ausgewählt
- **n8n vs. Python-Skript für Ingest:** Default n8n (passt zu Walters Stack); Fallback Python-Cron-Skript wenn n8n-Workflow zu komplex wird
- **Metrik-Normalisierungs-Mapping** (Health-Auto-Export-Feldnamen → kanonische `metric`-Namen): wird in Phase 1 konkret aufgebaut
