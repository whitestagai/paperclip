# LLM-Farm: Übergangskonzept für Mac Studio + RTX Pro 6000

**Datum:** 2026-08-25
**Status:** Entwurf — freigegeben, Umsetzung noch nicht begonnen
**Auslöser:** Erfolgsquote der Flotte über 7 Tage bei **26,7 %** (1.739 von 6.520 Runs);
das MacBook M5 Max muss aus der Farm genommen werden
**Betroffen:** LM-Studio-Belegung auf Mac Studio M4 und RTX Pro 6000, `adapter_config`
und `runtime_config` aller 47 Agenten, kein Servercode
**Gilt bis:** Ankunft der zwei Mac Studio mit je 512 GB Unified Memory — dafür entsteht
ein eigener Entwurf

## Problem

Die Flotte ist nicht fehlerhaft, sie ist **gesättigt**. Über die letzten 7 Tage:

| Status | Runs |
|---|---|
| succeeded | 1.739 |
| timed_out | 2.490 |
| failed | 2.061 |
| cancelled | 212 |
| **Summe** | **6.520** |

Der Tagesverlauf zeigt, dass die Fehler eine reine Funktion der Last sind:

| Uhrzeit | Runs/h | Erfolg | Timeout |
|---|---|---|---|
| 18:00–00:00 | 2–4 | ~100 % | 0 % |
| 07:00–15:00 | 110–166 | 12–28 % | 60–76 % |

Nachts läuft dieselbe Flotte mit denselben Modellen fehlerfrei.

**Es ist kein Kontextproblem.** Die Einzelaufrufe aus den LM-Studio-Logs haben Median
**11.356** Prompt-Token, p90 31.257, Maximum 97.550. Das passt in jedes gefahrene Fenster.
(`cost_events.input_tokens` führt hier in die Irre — dort ist der Wert über den ganzen Run
kumuliert und ergibt scheinbare Prompts von 100k+.)

**Die Last liegt fast vollständig auf einer Maschine.** Prompt-Token über zwei Tage:

| Knoten | Prompt-Token | Anteil |
|---|---|---|
| RTX Pro 6000 | 99,9 Mio. | **89 %** |
| Mac Studio M4 | 6,7 Mio. | 6 % |
| MacBook M5 Max | 5,7 Mio. | 5 % |

Das MacBook zu verlieren kostet 5 % der Last. Der Engpass liegt woanders.

## Ursachenkette

Jede Station ist gemessen:

1. **`AGENT_DEFAULT_MAX_CONCURRENT_RUNS = 20`** (`packages/shared/src/constants.ts:75`).
   30 Agenten haben nichts gesetzt und laufen auf diesem Default, 7 weitere auf einer
   ausdrücklichen 20. Theoretisches Maximum: **740 gleichzeitige Runs**.
2. **Die Grenze wirkt nur pro Agent.** `startNextQueuedRunForAgent` zählt mit
   `countRunningRunsForAgent(agentId)` unter `withAgentStartLock(agentId)`
   (`server/src/services/heartbeat.ts:6689`). Eine flottenweite Grenze existiert nicht.
3. **Jeder Run macht bis zu `maxIterations` LLM-Aufrufe** — konfiguriert sind 8 bis 40,
   typisch 12.
4. **`abiray/qwen3.6-35b-a3b` hat genau einen Bearbeitungsplatz.** Geladen mit
   `contextLength 262.144`, `parallel 1`. Auf diesem Modell liegen **11 Agenten**.
5. Die Warteschlange wächst über den Aufruf-Timeout von 900 s hinaus → Timeout.
6. **Der Adapter schaltet auf das Fallback-Modell um** — auch bei `kind === "timeout"`
   (`execute.ts:423`).
7. Das Fallback-Modell lag auf dem MacBook (langsamstes Prefill der Flotte) und war
   ebenso überlastet → **„LLM call failed on fallback: LLM call timed out"**, mit
   **2.339 von 2.490 Timeouts** die mit Abstand größte Fehlerklasse.
8. Der Run scheitert, erzeugt ein Recovery-Issue, das einen neuen Run erzeugt.

Der Beleg für Station 4 steht in der Erfolgsstatistik selbst — gleiche Maschine, gleiche
Stunde, gleiche Last, nur andere Slotzahl:

| Agent | Modell | Slots | Erfolg | Timeout |
|---|---|---|---|---|
| CMO | `gemma4-31b-it` | 4 | **96 %** | 0 % |
| CRO | `abiray/qwen3.6-35b-a3b` | **1** | **11 %** | 76 % |

### Nebenbefund: kein Prompt-Caching

In jedem `usage_json` steht `cachedInputTokens: 0` und `sessionReused: false`. Iteration 2
eines Runs prefillt die Historie aus Iteration 1 erneut. Deshalb summiert der CHO 171.935
Input-Token pro Run bei einem Median-Einzelaufruf von 11.356. Der CMO macht **genau einen**
Aufruf pro Run (p50 27.153, max 27.188) und steht bei 96 %.

Nicht Teil dieses Übergangs, aber der größte bekannte Hebel für später.

## Festlegungen

Vom Auftraggeber entschieden, nicht abgeleitet:

| Frage | Entscheidung |
|---|---|
| Knoten | Mac Studio M4 (128 GB) + RTX Pro 6000 (96 GB); MacBook fällt weg |
| Rolle Mac Studio | bleibt Steuerungshost für Paperclip, Postgres, n8n |
| Netz | 10 GbE oder schneller |
| Cloud | **strikt lokal, kein Cloud-Ventil** |
| Aufteilung | nach Promptgröße: Kurzstrecke Mac, Langstrecke RTX |
| Fallback-Modelle | **entfallen im Übergang; nur noch Primärmodelle** |
| Flottenweite Obergrenze | zurückgestellt, erst Konfiguration und messen |
| Slot-Teilung | 6 qwen / 4 gemma, danach nachsteuern |

Konsequenz aus „strikt lokal": fünf Agenten müssen aus der Cloud zurück — VP Engineering,
n8n-Betriebsingenieur, Social Media & Community, Bild & Video, Link-Detektor.

## Zielarchitektur

### Trennlinie zwischen den Knoten

Eine Zuordnung einzelner Agenten nach Promptgröße funktioniert **nicht** — die Agenten sind
bimodal (Büroleitung: p50 7.436, p90 212.036). Die tragfähige Trennlinie verläuft zwischen
**Diensten und Agenten**:

| Last | Aufrufe/30 T | p50 | p99 | Ziel |
|---|---|---|---|---|
| PII-Klassifikation (`gemma-4-12b-qat`) | 28.686 | 1.526 | 2.087 | **Mac Studio** |
| Agenten-Dialoge | ~9.000 | 11.356 | 54.000+ | **RTX** |

Der Klassifikator ist die häufigste Last der Flotte — dreimal so viele Aufrufe wie alle
Agenten zusammen — und die kleinste pro Stück, mit null Overflows in 30 Tagen. Er
konkurriert heute auf der RTX mit jedem Agentendialog um die GPU.

### RTX Pro 6000 — 96 GB

| # | Modell | CTX | Parallel | Thinking | Speicher |
|---|---|---|---|---|---|
| 1 | `abiray/qwen3.6-35b-a3b` | 65.536 | **6** | 0,5 % | 34,4 GB |
| 2 | `gemma4-31b-it` | 65.536 | 4 | 0,5 % | 28,4 GB |
| 3 | `qwen/qwen3-coder-30b` | 65.536 | 2 | 0,0 % | ~22,0 GB |
| | | | | **Summe** | **84,8 / 96 GB** |

### Mac Studio M4 — 128 GB

| # | Modell | CTX | Parallel | Thinking | Speicher |
|---|---|---|---|---|---|
| 4 | `google/gemma-4-12b-qat` | 16.384 | 8 | 0,1 % | 7,2 GB |
| 5 | `google/gemma-4-12b` | 16.384 | 6 | 11,8 % → `none` | 7,6 GB |
| 6 | `openbiollm-llama3-8b.gguf` | 8.192 | 2 | 0,0 % | 5,7 GB |
| 7 | `text-embedding-bge-m3` | 8.192 | — | — | 0,6 GB |
| | | | | **Summe** | **21,1 GB** |

Dazu Paperclip, Postgres, n8n. Der Swap steht heute bei **7,4 von 8 GB** — deshalb bleibt
dieser Knoten bewusst schlank.

### Speicherrechnung

Nicht geschätzt, sondern aus den geladenen Modellen rückgerechnet. Auf der RTX reserviert
llama.cpp den KV-Cache vorab, die gemeldete Größe enthält ihn also:

```
qwen:  30,30 GB − 22,07 GB Gewichte =  8,23 GB KV / 262.144 = 31,4 kB je Slot-Token
gemma: 32,64 GB − 19,89 GB Gewichte = 12,75 GB KV / 393.216 = 32,4 kB je Slot-Token
```

Mit ~32 kB je Slot-Token ist jede Tabellenzeile nachrechenbar. Auf dem Mac (MLX) wird KV
lazy belegt, dort entspricht die gemeldete Größe näherungsweise den Gewichten.

**Der Kern:** `qwen` bekommt sechs Slots statt einem und kostet dabei 4,1 GB mehr.

### Kontextwahl 65.536

Gemessener Bedarf über 30 Tage:

| Modell | ctx heute | p50 | p90 | p99 | max30d | Overflows |
|---|---|---|---|---|---|---|
| `abiray/qwen3.6-35b-a3b` | 98.304¹ | 17.434 | 34.944 | 54.072 | 92.121 | 97 |
| `gemma4-31b-it` | 98.304 | 17.330 | 31.457 | 57.662 | 83.845 | 120 |
| `google/gemma-4-12b` | 98.304 | 1.717 | 33.792 | 53.377 | 74.868 | **220** |
| `google/gemma-4-12b-qat` | 16.384 | 1.526 | 1.850 | 2.087 | 17.955 | 0 |

¹ laut Konfiguration; **geladen** ist das Modell mit 262.144.

65.536 liegt über dem p99 beider großen Modelle. **Bewusst in Kauf genommen:** rund 1 % der
Aufrufe wird künftig vom Adapter beschnitten statt vollständig übergeben. Der Tausch lautet
1 % gekappte Historie gegen sechsfachen Durchsatz bei aktuell 76 % Timeout.

Die Kürzung von `google/gemma-4-12b` auf 16.384 adressiert seine 220 Overflows — die
schlechteste Zahl der Flotte. Sie entstehen aus der Doppelnutzung für Winzigaufgaben
(p50 1.717) und Riesenprompts (p90 33.792); nach der Trennung bedient es nur noch die
Kurzstrecke.

### Thinking

Gemessene Quote über 10 Tage LM-Studio-Logs — Anteil der Aufrufe mit nichtleerem
`reasoning_content`. Kein Schalter, sondern Modellverhalten:

| Modell | Aufrufe | Quote |
|---|---|---|
| `qwen3.6-35b-a3b-mlx` (MacBook, MLX) | 11.631 | **98,4 %** |
| `abiray/qwen3.6-35b-a3b` (RTX, GGUF) | 5.384 | **0,5 %** |
| `google/gemma-4-12b` | 5.085 | 11,8 % |
| `gemma4-31b-it` | 6.960 | 0,5 % |
| `google/gemma-4-12b-qat` | 42.305 | 0,1 % |
| `qwen/qwen3-coder-30b` | 1.203 | 0,0 % |

Dasselbe Modell denkt je nach Build um Faktor 200 unterschiedlich. Dass die Zielbelegung
auf der GGUF-Variante landet, ist damit nachträglich belegt — der MLX-Zwilling hatte mit
p50 = 222.119 Input-Token den teuersten Aufruf der Flotte.

Einziger Eingriff: `reasoningEffort: "none"` für `google/gemma-4-12b` auf dem
Kurzstrecken-Knoten. Bei `qwen3.6` wäre ein solcher Eingriff wirkungslos — das Modell
ignoriert ein gesetztes `none`.

### Modelle, die entfallen

| Modell | GB | Grund |
|---|---|---|
| `gemma-4-31b-it-mlx` | 33,8 | MacBook fällt weg |
| `mistral-small-3.2-24b-mlx` | 20,0 | MacBook fällt weg; 55 Aufrufe/30 T |
| `google/gemma-4-31b` | 19,9 | **0 Aufrufe/30 T**, kein Agent, kein Skript |
| `qwen/qwen3.6-35b-a3b` (Zweitkopie) | 22,1 | Dublette zu `abiray/…` |
| `ornith-1.0-9b` | 6,0 | **0 Aufrufe/30 T**, kein Agent, kein Skript |
| `text-embedding-nomic-…` ×2 | 0,2 | ungenutzt neben `bge-m3` |

Von 14 Modellen auf 7. `ornith-1.0-9b` und `google/gemma-4-31b` belegen zusammen 25,9 GB
auf der Maschine, deren Swap voll ist.

### Agenten-Zuordnung

Ohne Fallback hat jeder Agent genau ein Modell. Aufgeführt sind nur **aktive** Agenten;
`terminated` gesetzte (CEO-Zweitträger, CTO 2, Büroleitung 2 und 3, Bild & Video als
`claude_local`) bleiben außen vor und werden nicht reaktiviert.

Zwei Namen kommen doppelt vor und meinen zwei getrennte Agenten: **Vault-Maintainer**
(WHITESTAG und Clara — beide auf `gemma4-31b-it`) und **Link-Detektor** (ein
`lmstudio_local` und ein `claude_local`; beide gehen auf `google/gemma-4-12b` am Mac).

**`abiray/qwen3.6-35b-a3b` (RTX, 6 Slots)** — Koordination, Analyse, Recherche
CEO · CTO · CPO · CRO · CHO · Büroleitung · Sekretärin · Blender · Recherche ·
Online-Rechercheur · Trainingscoach

**`gemma4-31b-it` (RTX, 4 Slots)** — Deutsch, Kreativ, Text, Fachaufgaben
CMO · CFO · DPO · Adobe · Akquise & Booking · Buchhaltung · Creative Assistant ·
Creative Director · Drehbuch · Label Manager · Lektorat · Marken-Spezialist · Mistika VR ·
Produktentwicklung · Redaktion & PR · Social Media Specialist · Vault-Maintainer (×2) ·
Vermögensverwaltung · Vitals-Monitor · Web-Design Specialist · LLM-Konfigurationsanalyst
*Umzügler vom MacBook:* SEO/GEO-Spezialist · Schlafcoach · Office & Admin
*Rückkehrer aus der Cloud:* Social Media & Community · Bild & Video

**`qwen/qwen3-coder-30b` (RTX, 2 Slots)** — Rückkehrer aus der Cloud
VP Engineering · n8n-Betriebsingenieur

**`google/gemma-4-12b` (Mac, 6 Slots)** — Kurzstrecke
Link-Detektor ×2 (p50 = 0, reine Werkzeugarbeit — der ideale Mac-Kandidat)

**`openbiollm-llama3-8b.gguf` (Mac, 2 Slots)**
Dr-Knowledge — 82 Läufe in 30 Tagen, **82 erfolgreich**, Prompts 3.424–4.040 Token

**Dienste ohne Agentenbezug (Mac):** PII-Klassifikation, Embeddings

### Fallback-Abbau

Alle 38 LM-Studio-Agenten haben heute:

```json
"url":         "http://localhost:1234",
"fallbackUrl": "http://localhost:1234"
```

Es gibt keinen zweiten Endpunkt. Der Fallback ist derselbe Server mit anderem Modellnamen.
Und die Umschaltprüfung testet den **Server**, nicht die Warteschlange des Modells
(`execute.ts:428`):

```ts
const probe = await probeEndpoint(fallbackUrl, probeTimeoutMs);
if (!probe.ok) return false;
```

Ein überlastetes Modell auf einem gesunden Server besteht diese Prüfung immer. Die
Umschaltung feuert bei jedem Timeout garantiert und landet auf der nächsten Schlange.

**Der naheliegende Griff wäre falsch.** `fallbackUrl` zu leeren nimmt auch die einzige
Wiederholung mit — sie hängt am Rückgabewert von `maybeSwitchToFallback`:

```ts
const switched = await maybeSwitchToFallback(err, "chat completion");
if (switched) {
  const retryBudget = Math.max(1000, timeoutMs - (Date.now() - iterationStart));
  // ... erst hier wird wiederholt
}
```

**Richtig ist eine Zeile weiter oben:**

```ts
currentEndpoint = { url: fallbackUrl, model: fallbackModel || primaryModel };
```

Ist `fallbackModel` leer, nimmt der Adapter das Primärmodell.

> **Umsetzung: `fallbackModel` bei allen 38 Agenten leeren, `fallbackUrl` stehen lassen.**

Kein Modellwechsel mehr — die Fehlerklasse „failed on fallback" entfällt
konstruktionsbedingt — und die Wiederholung bleibt erhalten, jetzt auf dem richtigen Modell.

### Zeitarchitektur

Die Wiederholung ist heute rechnerisch tot: `timeoutMs` (900.000) und `maxRunSeconds`
(900) sind identisch, das Restbudget nach einem Timeout ist die 1-Sekunden-Untergrenze.

| Feld | heute | neu | Begründung |
|---|---|---|---|
| `timeoutMs` | 900.000 | **240.000** | p90-Prefill der dichten Gemma = 146 s |
| `timeoutSec` / `maxRunSeconds` | 900 | **1800** | 12 Iterationen × 150 s |
| `maxIterations` | 8–40 | **12** | Ausreißer angleichen |

Der Aufruf-Timeout sinkt von 15 auf 4 Minuten, das Run-Budget steigt von 15 auf 30 Minuten:
**schnell aufgeben beim einzelnen Aufruf, geduldig sein beim Gesamtvorgang.**

### Zulassungssteuerung — Stufe A

`maxConcurrentRuns` explizit setzen, statt sich auf den 20er-Default zu verlassen:

| Modellpool | Slots | Agenten | Grenze je Agent |
|---|---|---|---|
| `abiray/qwen3.6-35b-a3b` | 6 | 11 | **1** |
| `gemma4-31b-it` | 4 | ~29 | **1** |
| `qwen/qwen3-coder-30b` | 2 | 2 | **1** |
| Mac-Kurzstrecke | 16 | 2 + Dienste | **2** |

Senkt das theoretische Maximum von 740 auf 47 — Faktor 16, durch Setzen eines Feldes, das
heute leer ist. Bei sieben Agenten muss dafür eine ausdrückliche 20 auf 1 korrigiert werden
(Dr-Knowledge, LLM-Konfigurationsanalyst, Lektorat, Link-Detektor ×2, SEO/GEO-Spezialist,
Vault-Maintainer).

## Migrationsreihenfolge

Jeder Schritt ist einzeln wirksam und einzeln zurücknehmbar.

1. **Tote Modelle entladen** — `ornith-1.0-9b`, `google/gemma-4-31b`, Nomic-Embeddings
   (zusammen **26,1 GB auf dem Mac Studio**) sowie die `qwen/qwen3.6-35b-a3b`-Dublette
   (**22,1 GB auf der RTX**).
2. **Slot-Korrektur `qwen`** — 262.144×1 → 65.536×6. Der größte Einzelhebel, ohne
   Speichermehrbedarf.
3. **`gemma4-31b-it`** auf 65.536×4, **`google/gemma-4-12b`** auf 16.384×6.
4. **`gemma-4-12b-qat`** von RTX auf Mac verlagern.
5. **`qwen/qwen3-coder-30b`** neu laden (RTX), **`openbiollm-llama3-8b`** auf den Mac.
6. **`fallbackModel` leeren** bei allen 38 Agenten.
7. **Zeitfelder setzen** — `timeoutMs`, `maxRunSeconds`, `maxIterations`; bei
   Dr-Knowledge `timeoutMs` erstmalig.
8. **`maxConcurrentRuns`** auf 1 bzw. 2.
9. **20 Agenten umhängen** — MacBook-Waisen und Cloud-Rückkehrer.
10. **`reasoningEffort: "none"`** für `google/gemma-4-12b`.

Schritte 1–5 betreffen LM Studio, 6–10 die Datenbank. Kein Servercode, kein Build, kein
Deploy.

## Abnahmekriterien

Nach einer Woche Regelbetrieb, gemessen mit denselben Abfragen wie oben:

| Größe | heute | Ziel |
|---|---|---|
| Erfolgsquote gesamt | 26,7 % | **> 70 %** |
| Timeout-Quote 07:00–15:00 | 60–76 % | **< 15 %** |
| „failed on fallback: timed out" | 2.339 / 7 T | **0** |
| Erfolgsquote CRO | 11 % | **> 70 %** |
| Overflows `google/gemma-4-12b` | 220 / 30 T | **< 20** |
| Swap Mac Studio | 7,4 / 8 GB | **< 4 GB** |

Wird die Timeout-Quote nicht erreicht, greift in dieser Reihenfolge:
`gemma4-31b-it` auf 5 Slots (2,1 GB, passt) → analytische Agenten von Gemma auf die MoE
ziehen (Vitals-Monitor, LLM-Konfigurationsanalyst, Label Manager) → Stufe B.

## Bewusst zurückgestellt

| Punkt | Grund |
|---|---|
| **Flottenweite Obergrenze (Stufe B)** | Braucht Servercode. Erst messen, ob 47 reicht. Entwurf: zusätzlicher Zähler über alle Agenten vor `startNextQueuedRunForAgent`, Startwert 12. |
| **Prompt-Caching** | Größter bekannter Hebel (`cachedInputTokens: 0` überall), aber eigene Untersuchung — betrifft Adapter und LM-Studio-Slotverhalten. |
| **Zielarchitektur mit 2× 512 GB** | Eigener Entwurf. Kernthese: große MoE-Modelle auf die Macs, dichte auf die RTX — belegt durch 5 s gegen 25 s Median-Prefill bei gleicher Promptlänge auf derselben Maschine. |

## Risiken

**`gemma4-31b-it` trägt mit ~29 Agenten mehr als die halbe Flotte auf 4 Slots** und ist das
langsame dichte Modell (25 s Median-Prefill gegen 5 s bei der MoE). Entschieden wurde,
mit 6/4 zu starten und nachzusteuern; die Reserve dafür ist eingeplant.

**Kein Cloud-Ventil.** Übersteigt die Last dauerhaft die Kapazität beider Knoten, gibt es
keinen Ausweg außer Warten. Genau das ist gewollt — ein wartender Run kostet nichts, ein
gestarteter und gestorbener kostet Rechenzeit und erzeugt Nacharbeit.

**Die RTX wird zum alleinigen Träger der Agentenflotte.** Fällt sie aus, steht die Firma.
Im Übergang bewusst hingenommen: sie trägt heute bereits 89 %, und ein zweiter Knoten, der
in den Timeout läuft, erhöht die Verfügbarkeit nicht.

**VP Engineering verliert Qualität.** Der Umzug von `claude-sonnet-5` auf ein lokales 30B
ist der teuerste Teil von „strikt lokal". `qwen/qwen3-coder-30b` ist die belegte Wahl — es
lief hier bis zum 22.08. produktiv, mit 2.189 Aufrufen allein am 30.07. — aber es ist
kein Ersatz auf Augenhöhe.

**Dr-Knowledge verliert nichts.** Das Fachmodell zieht mit auf den Mac.
