# LLM-Farm-Umzug: Flottenmodelle auf GeForce-Node, Pro 6000 wird Coding-Node

> **Für agentische Bearbeiter:** Dieser Plan ist ein **Betriebs-Migrationsplan**, kein
> Code-Plan. Statt „Test schreiben → rot → grün" hat jede Aufgabe eine **Messung**
> und einen **Rückweg**. Schritte nutzen Checkbox-Syntax (`- [ ]`).
> **Phase 0 ist ein Gate: Bricht sie, wird der Umzug nicht durchgeführt.**

**Ziel:** Die beiden Flottenmodelle (`gemma4-31b-it`, `abiray/qwen3.6-35b-a3b`) von
der RTX Pro 6000 auf einen neuen, dauerstromfreien PC mit RTX 5090 + RTX 3090
umziehen; die Pro 6000 wird tagsüber laufender Coding-Node für VP Engineering.

**Architektur:** Heute tragen 37 von 48 Agenten zwei Modelle auf **einer** 96-GB-Karte
(62,94 GB Gewichte + ~33 GB KV für 1.050.624 Slot-Token). Künftig liegen sie auf
**zwei getrennten Karten mit zusammen 56 GB** — was nur aufgeht, wenn beide Modelle
auf Q4_K_M herunterquantisiert werden **und** der KV-Cache auf `q8_0` quantisiert
wird. Phase 0 misst genau das auf der großen Karte, bevor Hardware bewegt wird.

**Stand der Fakten:** erhoben am 2026-09-11 (siehe „Ausgangslage").

**Spec:** Dieser Plan ist selbsttragend — die Ausgangslage steht unten vollständig.

---

## Global Constraints

Diese Regeln gelten für **jede** Aufgabe. Verstöße haben in diesem Projekt
nachweislich Flottenleistung gekostet; die Belege stehen jeweils dabei.

- **Kontextfenster nie unter 98.304.** 65.536 trieb die Überläufe am 25.08. von
  21 % auf 67 % und am 26.08. binnen einer Stunde auf 71 %, nachdem 98.304 zuvor
  18 Stunden ohne einen einzigen Überlauf gelaufen war.
- **Slots (`--parallel`) nie auf 1.** Am 25.08. stand CMO mit 4 Slots bei 96 %
  Erfolg, CRO mit 1 Slot bei 11 % — gleiche Maschine, gleiche Stunde.
- **`modelProfiles` wirkt in `runtime_config`, NICHT in `adapter_config`.**
  `adapter_config.modelProfiles` wird geschrieben und nie gelesen. Am 22.08.
  landete deshalb von 642 cheap-Läufen genau **einer** auf dem gewollten Modell.
  Richtiger Pfad: `runtime_config.modelProfiles.cheap.adapterConfig.model`.
- **`PATCH {"runtimeConfig": {...}}` ERSETZT das Objekt** → immer die volle
  bestehende Struktur mitsenden. **`PATCH {"adapterConfig": {...}}` MERGED** →
  ein Schlüssel lässt sich darüber nur auf `null` setzen, nicht entfernen.
- **Adaptertyp nie im selben PATCH wechseln wie andere Felder.** Wechselt
  `adapterType`, fallen `paperclipSkillSync`, `allowedWriteRoots` und
  `maxIterations` ersatzlos heraus (am 31.07. live erlebt).
- **Modell-IDs nie aus dem Gedächtnis tippen.** Vor jedem PATCH gegen
  `GET http://localhost:1234/v1/models` verifizieren, das Gerät aus `lms ps`.
  Falsche Modellnamen sind die größte Fehlerklasse dieser Flotte.
- **`lms load` braucht den `modelKey`, nicht den Lade-Bezeichner.** `lms load
  abiray/qwen3.6-35b-a3b` scheitert; der Key ist `qwen3.6-35b-a3b`. Beides steht
  in `lms ls --json`.
- **Nach `unload` warten, bis das Modell aus `lms ps` verschwunden ist**, sonst
  „identifier already exists". **Nur bei STATUS `IDLE` entladen** — sonst bricht
  man einen laufenden Agentenlauf ab.
- **Keine Zugangsdaten in Protokolle, Chatverläufe oder den Vault** — nur den
  Fundort nennen.

**Zugänge und Pfade:**

| Was | Wo |
|---|---|
| Board-Token | `~/.paperclip/auth.json` → `credentials["http://localhost:3100"].token` |
| Paperclip-API | `http://localhost:3100` |
| Agenten je Company | `GET /api/companies/:id/agents` (`/api/agents` = 404) |
| Postgres | `localhost:54329`, DB/User/PW `paperclip` |
| LM Studio CLI | `~/.lmstudio/bin/lms` (nie `npx`) |
| LM Studio API | `http://localhost:1234` |
| Preload-Skript | `~/Desktop/n8n.sh`, RTX-Abschnitt Zeilen 232–262 |

**Company-IDs:**

| Company | ID | Agenten |
|---|---|---|
| WHITESTAG | `9cebf3cf-efe8-4597-a400-f06488900a87` | 30 |
| Clara Sound | `0e426844-309c-4528-9aa5-90ff76790a51` | 13 |
| Health Insights | `158c4959-4973-4cb0-8066-55ec0f35625e` | 5 |

---

## Ausgangslage (erhoben 2026-09-11)

**RTX Pro 6000 (96 GB), beide Modelle `IDLE`:**

| Identifier | modelKey | Quant | Gewichte | ctx | Slots |
|---|---|---|---|---|---|
| `abiray/qwen3.6-35b-a3b` | `qwen3.6-35b-a3b` | Q6_K | 30,30 GB | 131.328 | 4 |
| `gemma4-31b-it` | `gemma4-31b-it` | Q8_0 | 32,64 GB | 131.328 | 4 |

Summe Gewichte **62,94 GB**, KV-Budget daraus **~33 GB für 1.050.624 Slot-Token**.

**Mac Studio (`Local`, Gerätename `MacStudioM4Max128`):** `gemma-4-31b-it-mlx`
(33,80 GB, ctx 262144), `google/gemma-4-12b` (7,56 GB, ctx 98304, PII-Classifier),
`openbiollm-llama3-8b` (5,73 GB), `text-embedding-bge-m3`, `nomic-embed-text-v1.5`.
Die Studio fährt gleichzeitig Postgres, n8n, Paperclip, Brain und den PII-Proxy.

**Zweiter Peer `WHITESTAG-AI`: `disconnected`, trägt kein Modell.**

**Agentenbindung (37 Agenten):**
- 25 Primär auf `gemma4-31b-it`
- 12 Primär auf `abiray/qwen3.6-35b-a3b`
- 10 davon zusätzlich `cheap`-Profil auf `gemma4-31b-it`
- **Alle 37** haben `fallbackModel` = `gemma-4-31b-it-mlx` (Mac Studio)

**Lastverteilung (Runs, 14 Tage):** 00–07 Uhr = 3.548 auf 8 Stunden = **444/h**;
08–17 Uhr = 4.182 auf 10 Stunden = **418/h**. Die Nacht ist die Hauptschicht.

**Nacht-Runs (22–07 Uhr, 14 Tage), Top 5:** VP Engineering 968 · Online-Rechercheur
659 · CTO 538 · CMO 248 · CRO 241.

**VP Engineering läuft heute auf `claude-sonnet-5` (Cloud)**, ist also
geräteunabhängig.

**DeepSeek V4 Flash liegt bereits auf der Karte, ungeladen:**

```
modelKey:        deepseek/deepseek-v4-flash
paramsString:    256x8.4B   (MoE)
quantization:    MXFP4 (4 bits)
sizeBytes:       156.378.406.202  (156,38 GB)
maxContextLength: 1.048.576
trainedForToolUse: false
```

`lms load deepseek/deepseek-v4-flash --estimate-only` meldet
**„Estimated GPU Memory: 145.64 GiB", Confidence LOW** — auf einer 96-GB-Karte.

**Das Preload-Skript ist veraltet:** `~/Desktop/n8n.sh` lädt auf die RTX nur
`mistral-small-3.2-24b@q4_k_m` und kommentiert die Karte als „NACHTS AUS". Die
beiden heutigen Flottenmodelle kommen darin **nicht vor**; sie überleben einen
LM-Studio-Neustart also nur, weil sie ohne TTL geladen sind.

---

## Aufgabenübersicht

| # | Aufgabe | Gate |
|---|---|---|
| 0 | Probelauf der Zielkonfiguration auf der Pro 6000 | **Ja — bricht sie, endet der Plan** |
| 1 | Coding-Modell festlegen (DeepSeek ersetzen) | Ja |
| 2 | GeForce-Node aufsetzen und einbinden | — |
| 3 | Modelle auf den Node laden und pinnen | — |
| 4 | Agenten umschalten | — |
| 5 | Fallback-Kette reparieren | — |
| 6 | VP Engineering auf Tag/Nacht-Betrieb | — |
| 7 | Preload und Nachsorge | — |

---

### Task 0: Probelauf der Zielkonfiguration auf der Pro 6000

**Der wichtigste Schritt des ganzen Plans.** Er beantwortet auf vorhandener
Hardware die zwei Fragen, die der Umbau sonst erst hinterher beantwortet:
trägt Q4 die Qualität, und reicht das geschrumpfte Slot-Budget? Kostet nur
Download-Zeit.

**Betrifft:** LM Studio auf der RTX Pro 6000, keine Paperclip-Änderung.

**Rückweg:** Die Q6/Q8-Dateien bleiben liegen; Rückkehr ist ein `lms unload` +
`lms load` der alten Keys mit `-c 131328 --parallel 4`.

- [ ] **Schritt 1: Baseline messen, bevor irgendetwas angefasst wird**

Die Vergleichszahl für alles Folgende. Sieben Tage zurück:

```bash
PGPASSWORD=paperclip psql -h localhost -p 54329 -U paperclip -d paperclip -c "
SELECT a.name, a.adapter_config->>'model' AS model,
       count(*) AS runs,
       count(*) FILTER (WHERE r.status = 'succeeded') AS ok,
       round(100.0 * count(*) FILTER (WHERE r.status = 'succeeded') / count(*), 1) AS pct
FROM heartbeat_runs r JOIN agents a ON a.id = r.agent_id
WHERE r.started_at > now() - interval '7 days'
  AND a.adapter_config->>'model' IN ('gemma4-31b-it','abiray/qwen3.6-35b-a3b')
GROUP BY 1,2 ORDER BY 3 DESC;"
```

Ergebnis in `docs/superpowers/plans/baseline-2026-09-11.txt` sichern. Ohne diese
Zahl ist die Bewertung in Schritt 7 wertlos.

- [ ] **Schritt 2: Fehlerklassen der Baseline festhalten**

```bash
PGPASSWORD=paperclip psql -h localhost -p 54329 -U paperclip -d paperclip -c "
SELECT substring(r.error from 1 for 60) AS fehler, count(*)
FROM heartbeat_runs r JOIN agents a ON a.id = r.agent_id
WHERE r.started_at > now() - interval '7 days' AND r.error IS NOT NULL
  AND a.adapter_config->>'model' IN ('gemma4-31b-it','abiray/qwen3.6-35b-a3b')
GROUP BY 1 ORDER BY 2 DESC LIMIT 15;"
```

Besonders auf `Context size has been exceeded` achten — das ist die Zahl, die
beim Schrumpfen des KV-Budgets zuerst hochgeht.

- [ ] **Schritt 3: Q4-Repos verifizieren, NICHT aus dem Gedächtnis tippen**

An der RTX Pro 6000 (sie annonciert kein SSH — der Download muss **an der Karte**
gestartet werden, `lms get` kennt keine Geräte-Option):

```bash
lms get lmstudio-community/gemma-4-31B-it-GGUF --select
lms get lmstudio-community/Qwen3.6-35B-A3B-GGUF --select
```

`--select` zeigt die Quant-Liste. **Q4_K_M** wählen. Erwartete Größen:
gemma ~18–19 GB, qwen ~21–22 GB. Weichen sie um mehr als 2 GB ab, hier stoppen
und die Rechnung neu aufstellen.

- [ ] **Schritt 4: Defekt-Test der frischen Dateien**

Drei Metadatenfelder entscheiden, ob ein GGUF heil ist — der schnellste
Defekt-Test, den es hier gibt (`google/gemma-4-31b-qat` war genau daran als
beschädigte Datei erkennbar):

```bash
curl -s http://localhost:1234/api/v0/models | python3 -c "
import json,sys
for m in json.load(sys.stdin)['data']:
    if 'gemma-4-31' in m['id'] or 'qwen3.6-35' in m['id']:
        print(m['id'], '| arch:', m.get('arch'), '| max_ctx:', m.get('max_context_length'),
              '| caps:', m.get('capabilities'))
"
```

Erwartet: `arch`, `max_context_length` und `capabilities: [tool_use]` sind bei
**beiden** gesetzt. Fehlt eines, ist die Datei defekt → neu ziehen.

- [ ] **Schritt 5: Alte Modelle sauber entladen**

Erst prüfen, dass beide `IDLE` sind — ein `unload` auf einem laufenden Modell
bricht einen Agentenlauf ab:

```bash
~/.lmstudio/bin/lms ps
```

Zeigt die STATUS-Spalte für beide `IDLE`:

```bash
~/.lmstudio/bin/lms unload gemma4-31b-it
~/.lmstudio/bin/lms unload abiray/qwen3.6-35b-a3b
```

Dann warten, bis sie aus `lms ps` **verschwunden** sind (sonst „identifier
already exists" beim Laden).

- [ ] **Schritt 6: Zielkonfiguration laden**

KV-Cache-Quantisierung ist in LM Studio eine **Lade-Option der GUI**
(„K Cache Quantization Type" / „V Cache Quantization Type"), kein `lms load`-Flag
— wie beim Spec-Decoding. An der RTX in der GUI **beide auf `q8_0`** setzen,
dann laden.

**Zuerst die modelKeys der frisch gezogenen Q4-Dateien ablesen** — sie sind
andere als die der alten Q6/Q8-Dateien, und `lms load` braucht den Key, nicht den
Bezeichner:

```bash
~/.lmstudio/bin/lms ls --json | python3 -c "
import json,sys
for m in json.load(sys.stdin):
    q = (m.get('quantization') or {}).get('name','')
    if 'Q4' in str(q) and m.get('type') == 'llm':
        print(m['modelKey'], '|', q, '|', round(m['sizeBytes']/1e9,2), 'GB')
"
```

Die beiden ausgegebenen Keys unten einsetzen. Fenster und Slots sind das
Zielprofil der kleineren Karten:

```bash
~/.lmstudio/bin/lms load <QWEN_Q4_KEY> --identifier abiray/qwen3.6-35b-a3b \
  -c 98304 --parallel 4 -y
~/.lmstudio/bin/lms load <GEMMA_Q4_KEY> --identifier gemma4-31b-it \
  -c 98304 --parallel 3 -y
```

**`--ttl` NICHT setzen** — die Option setzt nur, sie löscht nicht; ohne sie
bleibt `ttlMs=null`. Der `--identifier` muss **exakt** `abiray/qwen3.6-35b-a3b`
bzw. `gemma4-31b-it` lauten — daran hängen alle 37 Agenten; eine Abweichung lässt
sie ins Leere zeigen. Zweite Falle: sind zwei Kopien desselben modelKey auf
verschiedenen Geräten registriert, ist `lms load -y` **nicht disambiguierbar** —
es gibt keinen Geräteschalter.

- [ ] **Schritt 7: Belegung gegenrechnen**

```bash
~/.lmstudio/bin/lms ps
```

Die SIZE-Spalte zeigt **nur die Gewichte, nicht den KV-Cache** — daraus lässt
sich kein KV-Bedarf ableiten (dieser Fehlschluss ist hier schon einmal gemacht
worden). Belastbar ist allein: laden die Modelle, und läuft die Karte stabil.
Erwartete Gewichtssumme **~40 GB**.

- [ ] **Schritt 8: Tool-Call und Deutsch prüfen — Q4 kann beides kosten**

Gemma liegt in der Flotte, weil es Deutsch und Kreativtexte trägt; der Sprung von
Q8 auf Q4 ist dort nicht folgenlos. Der Prüfstand dafür existiert als
`gemma_pruefstand.py` (Metadaten / Tool-Call 3× / Deutsch-Vergleich auf
Template-Müll / TTFT + Decode + Langprompt). Liegt er nicht mehr vor, mindestens:

```bash
curl -s http://localhost:1234/v1/chat/completions -H 'Content-Type: application/json' -d '{
  "model": "gemma4-31b-it",
  "messages": [{"role":"user","content":"Schreib eine kurze, höfliche Absage an einen Kunden, der einen Drehtermin am Wochenende wollte."}],
  "max_tokens": 400
}' | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['choices'][0]['message']['content'])"
```

Prüfen: Deutsch fehlerfrei, keine Template-Reste, `content` nicht leer.
**Achtung:** Ist `content` leer und der Text steckt in `reasoning_content`, ist
die Reasoning-Abschaltung in der Jinja-Vorlage beim Quant-Wechsel verloren
gegangen → an der RTX erneut in der Vorlage abschalten. Ein einzelner Lauf mit
`reason_tok=0` beweist nichts; **sechs** Läufe fahren.

- [ ] **Schritt 9: Eine Woche laufen lassen, dann bewerten**

Nach 7 Tagen die Abfragen aus Schritt 1 und 2 erneut fahren und gegen
`baseline-2026-09-11.txt` halten.

**Gate — der Umzug geht nur weiter, wenn alle drei zutreffen:**
1. Erfolgsquote je Agent **nicht mehr als 5 Prozentpunkte** unter Baseline.
2. `Context size has been exceeded` **nicht höher** als in der Baseline.
3. Deutsch- und Tool-Call-Prüfung aus Schritt 8 bestanden.

**Bricht das Gate:** Der Umzug in dieser Form ist tot. Die 56 GB tragen die
Flotte nicht. Alternativen dann: nur **ein** Modell auf den GeForce-Node und das
andere auf der Pro 6000 lassen (dann muss die Karte doch durchlaufen), oder
größeres VRAM im neuen PC.

---

### Task 1: Coding-Modell festlegen — DeepSeek V4 Flash ersetzen

**Betrifft:** LM Studio auf der RTX Pro 6000.

**Warum:** `lms load --estimate-only` meldet für DeepSeek V4 Flash
**145,64 GiB GPU-Speicher** bei 96 GB Karte, und die Metadaten melden
`trainedForToolUse: false`. Ein Paperclip-Agent ohne Tool-Calls kann nicht
arbeiten — beides zusammen schließt das Modell aus.

- [ ] **Schritt 1: Den Befund selbst nachstellen, nicht diesem Plan glauben**

```bash
~/.lmstudio/bin/lms load deepseek/deepseek-v4-flash --estimate-only
~/.lmstudio/bin/lms ls --json | python3 -c "
import json,sys
for m in json.load(sys.stdin):
    if 'deepseek' in str(m.get('modelKey','')):
        print('trainedForToolUse:', m.get('trainedForToolUse'),
              '| sizeBytes:', m.get('sizeBytes'),
              '| quant:', m.get('quantization'))
"
```

Erwartet: ~145 GiB und `trainedForToolUse: False`.

- [ ] **Schritt 2: Ersatzmodell ziehen**

`qwen3-coder-next` (80B MoE, 3B aktiv) lag bis zum 21.08. auf dieser Karte
(48,49 GB @ ctx 131328) und flog nur raus, weil es damals ungenutzt war — 5
Aufrufe in 30 Tagen. Bei Q4 sind es ~35–40 GB. An der RTX:

```bash
lms get lmstudio-community/Qwen3-Coder-Next-GGUF --select
```

Den exakten Repo-Namen aus der Trefferliste übernehmen; **nicht** aus diesem Plan
abtippen. Q4_K_M wählen.

- [ ] **Schritt 3: Defekt-Test wie in Task 0 Schritt 4**

Hier ist `capabilities: [tool_use]` kein Nice-to-have, sondern die Bedingung.
Fehlt es, ist das Modell für VP Engineering unbrauchbar.

- [ ] **Schritt 4: Laden, Fenster nach `max30d` wählen**

Das Fenster wird nach dem **Maximum** der letzten 30 Tage bemessen, nicht nach
p99 — p99 heißt, dass 1 % der Läufe garantiert scheitert. Der historische
Coder-Bedarf lag bei p99 70.404 / max30d 78.100, also reichen 98.304:

```bash
~/.lmstudio/bin/lms load qwen3-coder-next -c 98304 --parallel 4 -y
```

- [ ] **Schritt 5: DeepSeek von der Platte nehmen**

156,38 GB, die nichts tun. **Erst löschen, wenn Schritt 3 und 4 durch sind** —
die Regel „jede neue RTX-Belegung ist eine Verdrängungs-Entscheidung" gilt auch
rückwärts.

```bash
~/.lmstudio/bin/lms rm deepseek/deepseek-v4-flash
```

---

### Task 2: GeForce-Node aufsetzen und einbinden

**Betrifft:** Neuer PC, LM Link.

**Voraussetzung:** Task 0 bestanden.

- [ ] **Schritt 1: Dauerbetrieb sicherstellen — das ist die Bedingung, nicht ein Detail**

Die Farm fährt nachts 444 Runs/h gegen 418/h tagsüber. Schläft der Node, steht
die Hauptschicht ohne Primärmodelle da — genau das Nacht-Geräteloch, das am
23.08.2026 bewusst geschlossen wurde (es kostete 45–67 % Timeouts beim
PII-Classifier gegen 2–5 % tagsüber).

Auf dem PC: Ruhezustand, Energiesparmodus und Festplatten-Abschaltung **aus**;
automatischen Neustart nach Stromausfall **an**. Windows: Energieoptionen →
Höchstleistung, „Energie sparen" auf „Nie". Linux: `systemd` targets
`sleep.target suspend.target hibernate.target hybrid-sleep.target` maskieren.

- [ ] **Schritt 2: LM Studio installieren und LM Link verbinden**

Auf dem PC LM Studio installieren, Server auf Port 1234 aktivieren, dann von der
Mac Studio aus verbinden. Danach gegenprüfen:

```bash
~/.lmstudio/bin/lms link status
```

Erwartet: der neue Node erscheint mit `Status: connected`. Der Gerätename ist die
einzige Stelle, an der Klarnamen stehen — `lms ps --json` liefert nur
Geräte-Hashes.

- [ ] **Schritt 3: Gerätenamen und Identifier notieren**

```bash
~/.lmstudio/bin/lms link status --json | python3 -m json.tool
```

`deviceName` und `deviceIdentifier` des neuen Node festhalten — Task 7 braucht
beides für das Preload-Skript.

- [ ] **Schritt 4: Klären, ob LM Studio beide Karten getrennt ansprechen kann**

Standardmäßig splittet llama.cpp über **alle** sichtbaren GPUs. Für diesen Plan
muss aber jedes Modell auf **einer** Karte liegen. Zwei Wege, in dieser
Reihenfolge prüfen:

1. LM Studio GUI → Hardware-Einstellungen: GPU-Auswahl je Modell.
2. Falls nicht vorhanden: zwei LM-Studio-Instanzen mit gesetztem
   `CUDA_VISIBLE_DEVICES=0` bzw. `=1`.

**Geht keines von beiden, hier stoppen und melden** — dann ist der Plan ab
Task 3 nicht ausführbar, und die Alternative ist Tensor-Split über beide Karten
mit nur **einem** großen Modell.

---

### Task 3: Modelle auf den Node laden und pinnen

**Betrifft:** LM Studio auf dem GeForce-Node.

**Rückweg:** Die Modelle auf der Pro 6000 bleiben in Task 3 **geladen**. Erst
Task 4 schaltet die Agenten um; erst danach wird auf der Karte entladen.

- [ ] **Schritt 1: Q4-Dateien auf den Node ziehen**

`lms get` lädt immer auf die Maschine, auf der es läuft → **am PC** starten:

```bash
lms get lmstudio-community/gemma-4-31B-it-GGUF --select     # Q4_K_M
lms get lmstudio-community/Qwen3.6-35B-A3B-GGUF --select    # Q4_K_M
```

- [ ] **Schritt 2: Defekt-Test wie Task 0 Schritt 4**

- [ ] **Schritt 3: Auf die jeweilige Karte laden**

Die größere Karte bekommt das größere Modell. KV-Quantisierung in der GUI auf
`q8_0`, **identische Bezeichner wie bisher**:

```bash
# 5090 (32 GB): qwen ~22 GB Gewichte, ~10 GB KV
lms load qwen3.6-35b-a3b --identifier abiray/qwen3.6-35b-a3b -c 98304 --parallel 4 -y

# 3090 (24 GB): gemma ~19 GB Gewichte, ~5 GB KV
lms load gemma-4-31b-it --identifier gemma4-31b-it -c 98304 --parallel 3 -y
```

Kein `--ttl`.

- [ ] **Schritt 4: Reasoning-Abschaltung bei Gemma prüfen**

Der Eingriff in die Jinja-Vorlage vom 22.08. hängt an der Modelldatei, nicht am
Agenten — auf einer frisch gezogenen Datei ist er **weg**. Sechs Läufe fahren
(ein einzelner mit `reason_tok=0` beweist nichts), darunter einer mit „Denk
gründlich nach". Kommt `content=""` bei gefülltem `reasoning_content`, in der
Vorlage auf dem Node abschalten. Über die API ist es nicht abschaltbar:
`reasoning_effort`, `chat_template_kwargs` und `/no_think` sind alle verifiziert
wirkungslos, und der Paperclip-lmstudio-Adapter sendet `chat_template_kwargs`
ohnehin nicht.

- [ ] **Schritt 5: Beide Modelle antworten lassen**

```bash
for M in abiray/qwen3.6-35b-a3b gemma4-31b-it; do
  echo "== $M"
  curl -s http://localhost:1234/v1/chat/completions -H 'Content-Type: application/json' \
    -d "{\"model\":\"$M\",\"messages\":[{\"role\":\"user\",\"content\":\"Antworte nur mit OK.\"}],\"max_tokens\":10}" \
    | python3 -c "import json,sys; print(json.load(sys.stdin)['choices'][0]['message'])"
done
```

Beide müssen über `localhost:1234` der **Mac Studio** erreichbar sein — LM Link
routet dorthin. Antwortet nur eines, ist die Geräteaufteilung aus Task 2
Schritt 4 nicht wirksam.

---

### Task 4: Agenten umschalten

**Betrifft:** 37 Agenten über drei Companies.

**Trick:** Weil die Bezeichner gleich bleiben, ist **kein PATCH nötig** — LM Link
serviert dieselben Modell-IDs, nur von einem anderen Gerät. Diese Aufgabe ist
deshalb primär eine **Verifikation**, dass die Läufe tatsächlich auf dem neuen
Node landen.

- [ ] **Schritt 1: Konfiguration sichern, bevor irgendetwas angefasst wird**

```bash
TOKEN=$(python3 -c "import json;print(json.load(open('$HOME/.paperclip/auth.json'))['credentials']['http://localhost:3100']['token'])")
mkdir -p ~/.paperclip/backups
for CID in 9cebf3cf-efe8-4597-a400-f06488900a87 \
           0e426844-309c-4528-9aa5-90ff76790a51 \
           158c4959-4973-4cb0-8066-55ec0f35625e; do
  curl -s -H "Authorization: Bearer $TOKEN" \
    "http://localhost:3100/api/companies/$CID/agents" \
    > ~/.paperclip/backups/agents-$CID-$(date +%Y%m%d-%H%M%S).json
done
ls -la ~/.paperclip/backups/
```

- [ ] **Schritt 2: Pro 6000 entlasten — erst jetzt**

Beide Modelle müssen `IDLE` sein:

```bash
~/.lmstudio/bin/lms ps
~/.lmstudio/bin/lms unload gemma4-31b-it
~/.lmstudio/bin/lms unload abiray/qwen3.6-35b-a3b
```

- [ ] **Schritt 3: Nachweisen, wo die Läufe wirklich landen**

Der Merksatz, der jede stille Fehlleitung in Minuten entlarvt — gemessene gegen
konfigurierte Modelle gruppieren:

```bash
PGPASSWORD=paperclip psql -h localhost -p 54329 -U paperclip -d paperclip -c "
SELECT c.model AS gemessen, a.adapter_config->>'model' AS konfiguriert, count(*)
FROM cost_events c JOIN agents a ON a.id = c.agent_id
WHERE c.occurred_at > now() - interval '2 hours'
GROUP BY 1,2 ORDER BY 3 DESC;"
```

Abweichungen zwischen den beiden Spalten sind Fehlleitungen. Zusätzlich
`lms ps` auf der Mac Studio: die DEVICE-Spalte muss für beide Modelle den neuen
Node zeigen, **nicht** `RTX Pro 6000`.

- [ ] **Schritt 4: `cheap`-Profile der 10 betroffenen Agenten gegenlesen**

Sie zeigen auf `gemma4-31b-it` und wirken nur aus `runtime_config`:

```bash
PGPASSWORD=paperclip psql -h localhost -p 54329 -U paperclip -d paperclip -c "
SELECT a.name,
       a.runtime_config->'modelProfiles'->'cheap'->'adapterConfig'->>'model' AS cheap_rt,
       a.adapter_config->'modelProfiles'->'cheap'->'adapterConfig'->>'model' AS cheap_ac
FROM agents a WHERE a.status != 'deleted'
  AND a.runtime_config->'modelProfiles' IS NOT NULL ORDER BY 1;"
```

Steht ein Wert **nur** in `cheap_ac`, ist er wirkungslos — dann per PATCH nach
`runtimeConfig` heben, **volle Struktur mitsenden** (das Objekt wird ersetzt).

---

### Task 5: Fallback-Kette reparieren

**Betrifft:** 37 Agenten.

**Warum:** Alle 37 haben denselben `fallbackModel` = `gemma-4-31b-it-mlx` auf der
Mac Studio, die gleichzeitig den kompletten Dienste-Stack fährt. Der zweite Peer
`WHITESTAG-AI` ist `disconnected` und trägt nichts. Fällt der neue Node aus,
kippt die gesamte Flotte auf ein MLX-Modell, das bei ~16 tok/s prefillt — ein
74.860-Token-Prompt braucht dort 394 s, während die Agenten nach ~60 s abbrechen.
Das ist heute schon ein Single Point of Failure und wird nach dem Umzug der
einzige Rückweg.

- [ ] **Schritt 1: Klären, was aus `WHITESTAG-AI` geworden ist**

```bash
~/.lmstudio/bin/lms link status
```

Steht der Peer dauerhaft auf `disconnected`, ist zu entscheiden: zurückholen
(dann kann er Fallback-Modelle tragen) oder als Kapazität abschreiben (dann muss
der Fallback woanders hin). **Diese Entscheidung braucht Walter.**

- [ ] **Schritt 2: Zweiten Träger für den Fallback bestimmen**

Nach dem Umzug hat die Pro 6000 tagsüber ~50 GB frei neben dem Coder. Sie ist
nachts aus, taugt also nur als **Tag-Fallback** — was genau in die Stunden fällt,
in denen die Flotte am wenigsten läuft. Der belastbarere Weg ist, den Fallback
auf dem GeForce-Node selbst zu halten (anderes Modell, kleineres Fenster) oder
`WHITESTAG-AI` zurückzuholen.

- [ ] **Schritt 3: Fallback-Verteilung splitten**

Die 25 Gemma-Agenten und die 12 qwen-Agenten sollten **nicht** denselben
Fallback teilen. Vorschlag: Gemma-Agenten → `google/gemma-4-12b` (Mac Studio,
7,56 GB, ohnehin resident). `adapterConfig` merged, der PATCH ist also
unkritisch für die übrigen Felder.

**Erst an genau einem Agenten testen.** Dessen ID holen:

```bash
PGPASSWORD=paperclip psql -h localhost -p 54329 -U paperclip -d paperclip -t -A -c "
SELECT id FROM agents WHERE name = 'Lektorat' AND status != 'deleted';"
```

Patchen und die Antwort gegenlesen:

```bash
TOKEN=$(python3 -c "import json;print(json.load(open('$HOME/.paperclip/auth.json'))['credentials']['http://localhost:3100']['token'])")
AID=<ID_AUS_DER_ABFRAGE>
curl -s -X PATCH -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"adapterConfig":{"fallbackModel":"google/gemma-4-12b"}}' \
  "http://localhost:3100/api/agents/$AID" | python3 -m json.tool | head -30
```

Erwartet: HTTP 200, `fallbackModel` im Ergebnis auf dem neuen Wert, und
`maxIterations` / `allowedWriteRoots` / `paperclipSkillSync` **unverändert
vorhanden**. Fehlt eines davon, sofort stoppen — dann hat der PATCH nicht
gemerged, und die Sicherung aus Task 4 Schritt 1 wird gebraucht.

Erst danach der Massenlauf über die 25 Gemma-Agenten:

```bash
TOKEN=$(python3 -c "import json;print(json.load(open('$HOME/.paperclip/auth.json'))['credentials']['http://localhost:3100']['token'])")
PGPASSWORD=paperclip psql -h localhost -p 54329 -U paperclip -d paperclip -t -A -c "
SELECT id FROM agents WHERE status != 'deleted'
  AND adapter_config->>'model' = 'gemma4-31b-it'
  AND adapter_config->>'fallbackModel' = 'gemma-4-31b-it-mlx';" \
| while read AID; do
    CODE=$(curl -s -o /dev/null -w '%{http_code}' -X PATCH \
      -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
      -d '{"adapterConfig":{"fallbackModel":"google/gemma-4-12b"}}' \
      "http://localhost:3100/api/agents/$AID")
    echo "$AID -> $CODE"
  done
```

Alle Zeilen müssen `200` zeigen. Danach gegenlesen:

```bash
PGPASSWORD=paperclip psql -h localhost -p 54329 -U paperclip -d paperclip -c "
SELECT adapter_config->>'fallbackModel' AS fb, count(*)
FROM agents WHERE status != 'deleted' AND adapter_config->>'model' IS NOT NULL
GROUP BY 1 ORDER BY 2 DESC;"
```

- [ ] **Schritt 4: Selbst-Fallbacks ausschließen**

Ein Agent, der sich selbst als Fallback hat, hat keinen. Das ist hier schon
zweimal aufgetreten:

```bash
PGPASSWORD=paperclip psql -h localhost -p 54329 -U paperclip -d paperclip -c "
SELECT name, adapter_config->>'model' AS m, adapter_config->>'fallbackModel' AS fb
FROM agents WHERE status != 'deleted'
  AND adapter_config->>'model' = adapter_config->>'fallbackModel';"
```

Erwartet: leer.

- [ ] **Schritt 5: Kein Doppel-auf-einer-Maschine**

Primär und Fallback auf demselben Gerät sind kein Fallback:

```bash
~/.lmstudio/bin/lms ps
```

Für jeden Agenten prüfen, dass `model` und `fallbackModel` auf **verschiedenen**
Zeilen der DEVICE-Spalte stehen.

---

### Task 6: VP Engineering auf Tag/Nacht-Betrieb

**Betrifft:** ein Agent, `claude-sonnet-5` → Coder auf der Pro 6000.

**Das Problem:** VP Engineering hat **968 Nacht-Runs in 14 Tagen** — mehr als
jeder andere Agent. Die Karte ist nachts aus. `adapter_config` kennt kein
Zeitfenster, nur `model` und `fallbackModel`.

- [ ] **Schritt 1: Tag/Nacht-Mechanik wählen (Weg A oder B) — Walters Entscheidung**

*Hinweis: Schritt 2 stellt eine zweite, davon unabhängige Frage — wie der Agent
überhaupt an den lokalen Coder kommt (Weg 1/2/3). Beide werden gebraucht.*

**Weg A — Fallback in die Cloud.** `model` = Coder (RTX), `fallbackModel` =
`claude-sonnet-5`. Funktioniert ohne neue Bauteile, kostet aber **pro Nacht-Run
einen Fehlversuch** vor dem Fallback. Genau dieses Muster erzeugte im August 50
von 111 Fehlern dieses Agenten, als der PII-Classifier auf ein totes Modell
zeigte — es funktioniert, sieht in den Logs aber wie ein Dauerdefekt aus.

**Weg B — zeitgesteuerter PATCH** per launchd auf der Mac Studio: morgens auf den
Coder, abends auf `claude-sonnet-5`. Sauber im Betrieb, aber ein weiteres
bewegliches Teil. **Falls B:** launchd braucht `/opt/homebrew/bin` im PATH und
`node` als Starter — aus `bash`/`zsh` heraus kommt launchd hier nicht überall
hin. Und: eine geänderte plist wird **nicht nachgeladen**; `kickstart -k` startet
nur den Prozess. Nur `bootout` + `bootstrap` übernimmt eine neue plist.

- [ ] **Schritt 2: Den Preis des Adaptertyp-Wechsels kennen — er ist höher als gedacht**

VP Engineering (ID `5563514c-4254-48d5-9339-802172304119`) steht auf
`adapter_type: claude_local` mit:

```
model:              claude-sonnet-5
maxTurnsPerRun:     80
env:                ANTHROPIC_BASE_URL = http://localhost:4711/anthropic  (PII-Proxy)
paperclipSkillSync: 13 Skills
instructionsFilePath: …/agents/5563514c-…/instructions/AGENTS.md
```

**Der Wechsel auf `lmstudio_local` kostet die 13 Skills — und zwar doppelt.**
Technisch fallen `paperclipSkillSync`, `allowedWriteRoots` und `maxIterations`
beim Adaptertyp-Wechsel ersatzlos heraus (am 31.07. live erlebt). Konzeptionell
wiegt schwerer: **einen `lmstudio_local`-Agenten erreicht nur `AGENTS.md`** —
Paperclip-Skills sind für ihn schlicht kein Kanal. Ein zweiter PATCH kann das
Feld zurückschreiben, aber nicht bewirken, dass das Modell die Skills sieht.

Dazu kommt der Verlust des PII-Proxys: `ANTHROPIC_BASE_URL` zeigt heute auf
`localhost:4711/anthropic`. Beim lokalen Modell entfällt dieser Pfad — was
sachlich richtig ist (lokal verlässt nichts das Haus), aber die Kette ändert.

**Daraus folgen drei Wege — auch das ist Walters Entscheidung:**

**Weg 1 — VP Engineering bleibt `claude_local`, ein *neuer* Agent bekommt den
lokalen Coder.** Die 13 Skills bleiben unangetastet, der lokale Coder übernimmt
die Arbeit, für die er taugt. Neuer Agent per `POST /api/agent-hires` +
`/approve` (`POST /agents` gibt 409). Fallen dabei: `maxConcurrentRuns` wirkt in
`runtime_config`, nicht `adapter_config`; ein Recovery-Issue wird zum Blocker und
erzeugt eine 422-Schleife; Wecken nur per `heartbeat/invoke`.

**Weg 2 — Anthropic-kompatibler Proxy vor LM Studio.** VP Engineering bleibt
`claude_local`, `ANTHROPIC_BASE_URL` zeigt tagsüber auf einen Übersetzer vor dem
lokalen Coder. Skills und Adaptertyp bleiben. Preis: ein weiterer Dienst, der
laufen und gepflegt werden muss.

**Weg 3 — voller Wechsel auf `lmstudio_local`.** Am einfachsten, kostet aber die
Skills. Nur sinnvoll, wenn die Arbeit an lokalen Projekten ohne sie auskommt.

- [ ] **Schritt 3: Gewählten Weg umsetzen — bei Weg 3 zuerst sichern**

```bash
mkdir -p ~/.paperclip/backups
PGPASSWORD=paperclip psql -h localhost -p 54329 -U paperclip -d paperclip -t -A -c "
SELECT jsonb_pretty(adapter_config) FROM agents
WHERE id = '5563514c-4254-48d5-9339-802172304119';" \
  > ~/.paperclip/backups/vp-eng-adapterconfig-$(date +%Y%m%d-%H%M%S).json
cat ~/.paperclip/backups/vp-eng-adapterconfig-*.json | head -5
```

Die Sicherung muss die 13 Skills enthalten. Dann der Typwechsel **allein**, ohne
weitere Felder im selben PATCH:

```bash
TOKEN=$(python3 -c "import json;print(json.load(open('$HOME/.paperclip/auth.json'))['credentials']['http://localhost:3100']['token'])")
curl -s -X PATCH -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"adapterType":"lmstudio_local","adapterConfig":{"model":"qwen3-coder-next"}}' \
  "http://localhost:3100/api/agents/5563514c-4254-48d5-9339-802172304119" \
  | python3 -m json.tool | head -40
```

Dann mit einem **zweiten** PATCH zurückspielen, was herausgefallen ist —
`paperclipSkillSync`, `maxIterations`, `allowedWriteRoots` aus der Sicherung —
und anschließend gegenlesen:

```bash
PGPASSWORD=paperclip psql -h localhost -p 54329 -U paperclip -d paperclip -c "
SELECT adapter_type,
       adapter_config->>'model' AS model,
       jsonb_array_length(adapter_config->'paperclipSkillSync'->'desiredSkills') AS skills,
       adapter_config->>'maxIterations' AS maxiter
FROM agents WHERE id = '5563514c-4254-48d5-9339-802172304119';"
```

Erwartet: `skills` = **13**. Steht dort `NULL`, ist der zweite PATCH nicht
angekommen.

- [ ] **Schritt 4: Schreibgrenzen bewusst setzen**

`allowedWriteRoots` ist **keine Sperre** — `shell_exec` prüft keinen Pfad, und
`claude_local` fährt mit `--dangerously-skip-permissions`. Wenn VP Engineering
künftig an lokalen Projekten arbeitet, ist das eine bewusste Entscheidung, keine
technische Absicherung. Vor der Umstellung festlegen, an welchen Verzeichnissen
er arbeiten soll.

- [ ] **Schritt 5: Einen Tag beobachten**

```bash
PGPASSWORD=paperclip psql -h localhost -p 54329 -U paperclip -d paperclip -c "
SELECT date_trunc('hour', r.started_at) AS stunde, r.status, count(*)
FROM heartbeat_runs r JOIN agents a ON a.id = r.agent_id
WHERE a.name = 'VP Engineering' AND r.started_at > now() - interval '24 hours'
GROUP BY 1,2 ORDER BY 1;"
```

Erwartet bei Weg A: tagsüber `completed` über den Coder, nachts `completed` über
den Cloud-Fallback — mit einem Fehlversuch davor. Bei Weg B: durchgehend
`completed` ohne Fehlversuche.

---

### Task 7: Preload und Nachsorge

**Betrifft:** `~/Desktop/n8n.sh`, Dokumentation.

**Warum:** Das Preload-Skript kennt die beiden Flottenmodelle **gar nicht** und
beschreibt die RTX als „NACHTS AUS". Nach einem LM-Studio-Neustart wäre der
Zustand nicht wiederherstellbar.

- [ ] **Schritt 1: RTX-Abschnitt neu schreiben**

`~/Desktop/n8n.sh`, Zeilen 232–262. Der Peer-Lookup sucht heute nach `'RTX'` im
Gerätenamen — für den neuen Node kommt ein zweiter Lookup dazu. Muster wie
gehabt: `set_pref <node>` → `load …` → `set_pref $STUDIO_ID` zurück.

Aufzunehmen:
- neuer Node: `abiray/qwen3.6-35b-a3b` `-c 98304 --parallel 4`,
  `gemma4-31b-it` `-c 98304 --parallel 3`
- RTX Pro 6000: `qwen3-coder-next` `-c 98304 --parallel 4`
- den Kommentar „RTX ist NACHTS AUS" auf den neuen Stand bringen: die RTX ist
  wieder ein Tag-Dienst, der **neue Node** ist 24/7

- [ ] **Schritt 2: Dry-Run**

```bash
bash -n ~/Desktop/n8n.sh && echo "Syntax ok"
```

Dann ausführen und das Log lesen:

```bash
tail -50 ~/Library/Logs/*/lmstudio-preload.log
```

- [ ] **Schritt 3: Neustart-Test**

LM Studio auf allen Nodes neu starten, Preload laufen lassen, dann:

```bash
~/.lmstudio/bin/lms ps
```

Erwartet: beide Flottenmodelle auf dem neuen Node mit ctx 98304, der Coder auf
der Pro 6000, der PII-Classifier `google/gemma-4-12b` auf der Studio. Fehlt der
Classifier, ist die Farm blind — er ist mit ~18.700 Aufrufen in 30 Tagen das
meistgenutzte Modell und **taucht in `cost_events` nicht auf**, weil der Proxy
direkt gegen `:1234` geht.

- [ ] **Schritt 4: `docs/Agenten-LLM-Zuordnung.md` nachziehen**

Geräte, Modelle, Fenster, Slots und die Tag/Nacht-Regel für VP Engineering.

- [ ] **Schritt 5: Eine Woche nach dem Umzug erneut messen**

Die Abfragen aus Task 0 Schritt 1 und 2 gegen `baseline-2026-09-11.txt`. Diesmal
zusätzlich die Fehlerklassen-Signatur lesen: `Model unloaded` und HTML-500
(`API error 500: <!DOCTYPE…`) bedeuten **Reload-Turbulenz**, reine `timeout`
bedeuten **Sättigungs-Stau**. Die beiden verlangen gegenteilige Reaktionen.

- [ ] **Schritt 6: `ToDo.md` und Memory aktualisieren**

Neue Geräteaufteilung, das Ergebnis des Q4-Gates und die Tag/Nacht-Entscheidung
für VP Engineering festhalten.

---

## Offene Entscheidungen für Walter

Diese vier kann der Plan nicht selbst treffen:

1. **Task 2 Schritt 4** — Kann LM Studio auf dem PC jedes Modell auf eine
   bestimmte Karte pinnen? Geht das nicht, ist der Plan ab Task 3 nicht
   ausführbar, und die Alternative ist Tensor-Split über beide Karten mit nur
   **einem** großen Modell.
2. **Task 5 Schritt 1** — Kommt `WHITESTAG-AI` zurück, oder wird die Kapazität
   abgeschrieben? Davon hängt ab, wohin die Fallback-Kette zeigt.
3. **Task 6 Schritt 2** — Wie kommt VP Engineering an den lokalen Coder?
   Weg 1 (neuer Agent, Skills bleiben) · Weg 2 (Anthropic-Proxy vor LM Studio) ·
   Weg 3 (voller Adapterwechsel, 13 Skills fallen weg).
4. **Task 6 Schritt 1** — Tag/Nacht: Weg A (Cloud-Fallback, ein Fehlversuch pro
   Nacht-Run) oder Weg B (zeitgesteuerter PATCH per launchd)?

## Was dieser Plan bewusst NICHT tut

- **Er zieht nicht um, bevor Task 0 bestanden ist.** Das Gate ist der ganze Zweck
  der ersten Aufgabe.
- **Er fasst die Mac Studio nicht an.** Sie trägt den Dienste-Stack und den
  PII-Classifier; jede Umverteilung dorthin ist eine eigene Entscheidung.
- **Er rührt die Recovery- und Run-Zulassungs-Mechanik nicht an.** Wenn nach dem
  Umzug Runs stauen, ist das eine eigene Untersuchung — `maxConcurrentRuns` wirkt
  nur pro Agent, flottenweit gibt es keine Grenze.
