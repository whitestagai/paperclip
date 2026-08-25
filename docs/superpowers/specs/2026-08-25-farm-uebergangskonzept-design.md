# LLM-Farm: Übergangskonzept für Mac Studio + RTX Pro 6000

**Datum:** 2026-08-25
**Status:** umgesetzt am 25.08. — mit zwei Korrekturen gegenüber dem Entwurf, siehe
„Was bei der Umsetzung anders kam"
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

### Nebenbefund: die Cloud-Agenten scheitern an der lokalen Farm

Über 7 Tage:

| Agent | Modell | Erfolg | Hauptfehler |
|---|---|---|---|
| VP Engineering | `claude-sonnet-5` | **5 von 122** (4 %) | `blocked_by_pii_proxy: classifier_unavailable` — 50 (45 %) |
| n8n-Betriebsingenieur | `claude_local` | **35 von 272** (13 %) | `429 Server is temporarily limiting requests` — 177 (77 %) |

Der größte Einzelfehler des Cloud-Agenten VP Engineering ist der **PII-Klassifikator** —
`google/gemma-4-12b-qat`, das auf der überlasteten RTX lag und beim Aufräumen am 25.08.
gelöscht wurde. Schritt 4 der Migration stellt den Proxy auf `google/gemma-4-12b` am Mac
Studio um und repariert damit 45 % der VP-Engineering-Fehler, obwohl der Agent in der Cloud
bleibt.

Beim n8n-Betriebsingenieur ist der Umzug ins Lokale keine Qualitätseinbuße, sondern die
Reparatur seiner Hauptfehlerquelle: 77 % seiner Fehler sind Anthropic-Ratenbegrenzungen,
und ein einzelner 429 beendet bei `claude_local` den kompletten Run.

## Festlegungen

Vom Auftraggeber entschieden, nicht abgeleitet:

| Frage | Entscheidung |
|---|---|
| Knoten | Mac Studio M4 (128 GB) + RTX Pro 6000 (96 GB); MacBook fällt weg |
| Rolle Mac Studio | bleibt Steuerungshost für Paperclip, Postgres, n8n |
| Netz | 10 GbE oder schneller |
| Cloud | strikt lokal, kein Cloud-Ventil — **Ausnahme: VP Engineering bleibt auf `claude-sonnet-5`** |
| Aufteilung | nach Promptgröße: Kurzstrecke Mac, Langstrecke RTX |
| Fallback-Modelle | **entfallen im Übergang; nur noch Primärmodelle** |
| Flottenweite Obergrenze | zurückgestellt, erst Konfiguration und messen |
| Coding-Modell lokal | **entfällt** — ohne VP Engineering bliebe nur ein Nutzer |
| Slot-Teilung | entschieden: 8 qwen / 12 gemma — **umgesetzt: 5 / 8**, siehe „Was bei der Umsetzung anders kam" |

Konsequenz aus „strikt lokal": **drei** Agenten kommen aus der Cloud zurück —
n8n-Betriebsingenieur, Social Media & Community, Link-Detektor. (Bild & Video steht auf
`terminated` und wird nicht reaktiviert.)

**Die Ausnahme für VP Engineering trägt sich selbst.** Ohne ihn hätte ein lokales
Coding-Modell nur noch den n8n-Betriebsingenieur bedient — 22 GB für einen Agenten. Diese
22 GB werden stattdessen zu Bearbeitungsplätzen: `gemma4-31b-it` steigt von 4 auf 8 Slots
(im Entwurf waren 12 vorgesehen; das Fenster musste zurückgenommen werden, siehe unten).
Damit ist das größte Risiko dieses Entwurfs — 29 Agenten auf 4 Slots beim langsamen dichten
Modell — deutlich entschärft, ohne dass ein Gerät hinzukommt.

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

| # | Modell | CTX | Parallel | Thinking | Agenten | Slot-Token |
|---|---|---|---|---|---|---|
| 1 | `abiray/qwen3.6-35b-a3b` | **98.304** | **5** | 0,5 % | 11 | 491.520 |
| 2 | `gemma4-31b-it` | **98.304** | **8** | 0,5 % | ~29 | 786.432 |
| | | | | | **Summe** | **1.277.952** |

Kein lokales Coding-Modell. `qwen/qwen3-coder-30b` wird **nicht** nachinstalliert — mit
VP Engineering in der Cloud bliebe nur ein Nutzer übrig, und die 22 GB sind als
Bearbeitungsplätze für die gesamte Flotte deutlich mehr wert.

**Warum 98.304 und nicht 65.536** — der Entwurf sah zunächst 65.536 × 8 / × 12 vor. Das ist
am 25.08. produktiv gescheitert und wurde zurückgenommen; die Begründung steht unten unter
„Was bei der Umsetzung anders kam". Kurzfassung: der Adapter kürzt erst ab 32.000
*geschätzten* Token, und seine Schätzung unterschätzt JSON um Faktor 2,19 — bis zu 70.000
echte Token gehen also ungekürzt durch. Unter einem Fenster von ~74.000 überläuft das.

### Mac Studio M4 — 128 GB

| # | Modell | CTX | Parallel | Thinking | Gewichte |
|---|---|---|---|---|---|
| 3 | `google/gemma-4-12b` | **65.536** | 6 | 11,8 % → `none` | 7,6 GB |
| 4 | `openbiollm-llama3-8b.gguf` | 8.192 | 2 | 0,0 % | 5,7 GB |
| 5 | `text-embedding-bge-m3` | 8.192 | — | — | 0,6 GB |
| | | | | **Summe** | **13,9 GB** |

**`google/gemma-4-12b-qat` existiert nicht mehr.** Es wurde beim RTX-Aufräumen am 25.08.
zusammen mit der qwen-Dublette gelöscht (14 Modelle / 186,02 GB → 12 / 156,80 GB, Differenz
29,22 GB = 7,15 + 22,07). Der PII-Proxy zeigte danach auf ein totes Modell und lief nur noch
über seinen Fallback — jede der 28.686 Klassifikationen pro 30 Tage mit einem Fehlversuch
davor. `PII_PROXY_CLASSIFIER_MODEL` steht jetzt ebenfalls auf `google/gemma-4-12b`.

Dazu Paperclip, Postgres, n8n. Der Swap steht heute bei **7,4 von 8 GB** — deshalb bleibt
dieser Knoten bewusst schlank.

### Speicherrechnung — in Slot-Token, nicht in Gigabyte

**Die SIZE-Spalte von `lms ps` enthält nur die Gewichte, nicht den KV-Cache.** Belegt am
25.08.: `abiray/qwen3.6-35b-a3b` meldet **30,30 GB bei 262.144 × 1 und bei 65.536 × 8** —
dieselbe Zahl bei doppelter Slot-Token-Zahl. Eine frühere Fassung dieses Entwurfs hat aus
dieser Spalte einen KV-Bedarf von „~32 kB je Slot-Token" abgeleitet und darauf die gesamte
Belegung gerechnet. Das war falsch und ist entfernt.

Ohne VRAM-Einblick auf der RTX ist die belastbare Größe deshalb das **Produkt aus Fenster
und Slots**, kalibriert an einem nachweislich laufenden Zustand:

```
nachweislich getragen (25.08., 65.536 × 8 + 65.536 × 12) = 1.310.720 Slot-Token
Zielbelegung          (98.304 × 5 + 98.304 × 8)          = 1.277.952 Slot-Token  ✓
```

Solange die Summe unter dem belegten Maximum bleibt, passt die Belegung. Wächst der Bedarf,
muss der Wert neu ermittelt werden — nicht aus `lms ps`, sondern durch Laden und Beobachten.

**Der Kern:** `qwen` bekommt **fünf** Bearbeitungsplätze statt einem, `gemma4-31b-it`
**acht** statt vier.

**Vorbehalt:** Mehr Slots erhöhen nicht den Rohdurchsatz der GPU, der ist fest. Sie sorgen
dafür, dass Anfragen *vorankommen*, statt in einer Schlange zu verhungern. Genau das ist
der gemessene Fehlermodus — nicht zu wenig Rechenleistung, sondern Anfragen, die den
Timeout in der Warteschlange erreichen.

### Kontextwahl 98.304 — die Untergrenze ist der Adapter, nicht das Modell

Gemessener Bedarf über 30 Tage:

| Modell | ctx heute | p50 | p90 | p99 | max30d | Overflows |
|---|---|---|---|---|---|---|
| `abiray/qwen3.6-35b-a3b` | 98.304¹ | 17.434 | 34.944 | 54.072 | 92.121 | 97 |
| `gemma4-31b-it` | 98.304 | 17.330 | 31.457 | 57.662 | 83.845 | 120 |
| `google/gemma-4-12b` | 98.304 | 1.717 | 33.792 | 53.377 | 74.868 | **220** |
| `google/gemma-4-12b-qat` | 16.384 | 1.526 | 1.850 | 2.087 | 17.955 | 0 |

¹ laut Konfiguration; **geladen** war das Modell mit 262.144.

Der p99 liegt bei 54.072 bzw. 57.662 — nach dieser Zahl allein wäre 65.536 richtig
gewesen. **Die bindende Grenze ist aber nicht der Modellbedarf, sondern der Adapter.**

In [execute.ts:484](../../../opensource/paperclip-adapter-lmstudio/src/server/execute.ts#L484):

```ts
// Der Wert liegt deutlich unter dem kleinsten Budget, das ueberhaupt
// herauskommen kann (98304 × 0,8 = 78.643) …
const BUDGET_LOOKUP_THRESHOLD_TOKENS = 32_000;
```

Unterhalb von 32.000 **geschätzten** Token wird weder das Fenster abgefragt noch gekürzt.
Und die Schätzung ist `chars/4` — laut `context-budget.ts` unterschätzt sie JSON
(1,89 Zeichen/Token) und Shell-Ausgaben (1,83) um bis zu **Faktor 2,19**. Der
Korrekturfaktor `tokenFactor` startet bei 1 und wird erst *nach* einem erfolgreichen Aufruf
aus `usage.prompt_tokens` kalibriert — ein gescheiterter Aufruf liefert keine Usage, der
Faktor bleibt also auf 1 und der Lauf scheitert erneut.

```
32.000 geschätzt × 2,19 = 70.080 echte Token, die ungekürzt durchgehen
+ Platz für die Antwort                     ≈ 74.000 Mindestfenster
```

**Damit ist 98.304 die kleinste sichere Fenstergröße, solange die Konstante 32.000 ist.**
Wer das Fenster kleiner haben will, muss zuerst den Schwellenwert senken — siehe „Bewusst
zurückgestellt".

`google/gemma-4-12b` bekommt **65.536 × 6**, nicht die im Entwurf genannten 16.384: Der
Link-Detektor wurde wegen p50 = 0 als Kurzstrecke eingestuft, sein **Maximum liegt aber bei
47.180 Token**. Genau die Bimodalität, vor der dieser Entwurf weiter oben selbst warnt. Bei
einem 12B ist KV billig, die Großzügigkeit kostet fast nichts.

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
| `qwen/qwen3-coder-30b` (nicht Teil der Zielbelegung) | 1.203 | 0,0 % |

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

Von 14 Modellen auf **6**. `ornith-1.0-9b` und `google/gemma-4-31b` belegen zusammen
25,9 GB auf der Maschine, deren Swap voll ist.

### Agenten-Zuordnung

Ohne Fallback hat jeder Agent genau ein Modell. Aufgeführt sind nur **aktive** Agenten;
`terminated` gesetzte (CEO-Zweitträger, CTO 2, Büroleitung 2 und 3, Bild & Video als
`claude_local`) bleiben außen vor und werden nicht reaktiviert.

Zwei Namen kommen doppelt vor und meinen zwei getrennte Agenten: **Vault-Maintainer**
(WHITESTAG und Clara — beide auf `gemma4-31b-it`) und **Link-Detektor** (ein
`lmstudio_local` und ein `claude_local`; beide gehen auf `google/gemma-4-12b` am Mac).

**`abiray/qwen3.6-35b-a3b` (RTX, 8 Slots)** — Koordination, Analyse, Recherche
CEO · CTO · CPO · CRO · CHO · Büroleitung · Sekretärin · Blender · Recherche ·
Online-Rechercheur · Trainingscoach
*Rückkehrer aus der Cloud:* n8n-Betriebsingenieur

**`gemma4-31b-it` (RTX, 12 Slots)** — Deutsch, Kreativ, Text, Fachaufgaben
CMO · CFO · DPO · Adobe · Akquise & Booking · Buchhaltung · Creative Assistant ·
Creative Director · Drehbuch · Label Manager · Lektorat · Marken-Spezialist · Mistika VR ·
Produktentwicklung · Redaktion & PR · Social Media Specialist · Vault-Maintainer (×2) ·
Vermögensverwaltung · Vitals-Monitor · Web-Design Specialist · LLM-Konfigurationsanalyst
*Umzügler vom MacBook:* SEO/GEO-Spezialist · Schlafcoach · Office & Admin
*Rückkehrer aus der Cloud:* Social Media & Community

**`claude-sonnet-5` (Cloud, `claude_local`)** — bleibt als einzige Ausnahme
VP Engineering

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

| Feld | vorher | gesetzt | Begründung |
|---|---|---|---|
| `timeoutMs` | 900.000 | **240.000** | p90-Prefill der dichten Gemma = 146 s |
| `timeoutSec` / `maxRunSeconds` | 900 | **1800** | 12 Iterationen × 150 s |
| `maxIterations` | 8–40 | **min(vorher, 12)** | nur nach unten geklemmt, siehe unten |
| `maxToolResultChars` | 40.000 (Default) | **12.000** | ein Tool-Ergebnis durfte ~21.800 Token belegen |

**`maxIterations` wird nur nach unten geklemmt**, nicht einheitlich auf 12 gesetzt. Wer
vorher 8 hatte, behält 8. Grund: bei aktivem Überlaufproblem wäre eine *Erhöhung* die
falsche Richtung — mehr Iterationen heißt längere Historie heißt mehr Überläufe. Betroffen
sind 16 Agenten, die vorher zwischen 20 und 40 lagen.

**`maxToolResultChars`** war nie gesetzt und lief auf dem Default von 40.000 Zeichen. Bei
gemessenen 1,83 Zeichen/Token für Shell-Ausgaben sind das ~21.800 Token — ein einzelnes
Tool-Ergebnis konnte also über 40 % des Prompt-Budgets belegen. `capToolResult` läuft
ungated bei jedem Ergebnis ([execute.ts:786](../../../opensource/paperclip-adapter-lmstudio/src/server/execute.ts#L786)),
ist also unabhängig vom Schwellenwert-Problem wirksam.

Der Aufruf-Timeout sinkt von 15 auf 4 Minuten, das Run-Budget steigt von 15 auf 30 Minuten:
**schnell aufgeben beim einzelnen Aufruf, geduldig sein beim Gesamtvorgang.**

### Zulassungssteuerung — Stufe A

`maxConcurrentRuns` explizit setzen, statt sich auf den 20er-Default zu verlassen:

| Modellpool | Slots | Agenten | Grenze je Agent |
|---|---|---|---|
| `abiray/qwen3.6-35b-a3b` | 5 | 11 | **1** |
| `gemma4-31b-it` | 8 | ~29 | **1** |
| Mac-Kurzstrecke | 8 | 3 + Dienste | **1** |
| `claude_local` (Cloud) | — | 3 | **1** |

Umgesetzt wurde **1 für alle 47** — auch für die Mac-Kurzstrecke, weil die Warteschlange
ohnehin greift und ein einheitlicher Wert weniger Sonderfälle erzeugt.

Senkt das theoretische Maximum von 740 auf 47 — Faktor 16, durch Setzen eines Feldes, das
heute leer ist. Bei sieben Agenten muss dafür eine ausdrückliche 20 auf 1 korrigiert werden
(Dr-Knowledge, LLM-Konfigurationsanalyst, Lektorat, Link-Detektor ×2, SEO/GEO-Spezialist,
Vault-Maintainer).

## Migrationsreihenfolge

Jeder Schritt ist einzeln wirksam und einzeln zurücknehmbar.

1. **Tote Modelle entladen** — `ornith-1.0-9b`, `google/gemma-4-31b`, Nomic-Embeddings
   (zusammen **26,1 GB auf dem Mac Studio**) sowie die `qwen/qwen3.6-35b-a3b`-Dublette
   (**22,1 GB auf der RTX**).
2. **Slot-Korrektur `qwen`** — 262.144×1 → **98.304×5**. Der größte Einzelhebel; Schritt 1
   auf der RTX muss dafür abgeschlossen sein.
   *`lms load` braucht den `modelKey` (`qwen3.6-35b-a3b`), nicht den Lade-Bezeichner
   (`abiray/…`) — sonst „select a model interactively". Nach `unload` warten, bis das Modell
   aus `lms ps` verschwunden ist, sonst „identifier already exists".*
3. **`gemma4-31b-it`** auf **98.304×8**, **`google/gemma-4-12b`** auf **65.536×6**.
4. **PII-Proxy** von `google/gemma-4-12b-qat` (gelöscht) auf `google/gemma-4-12b` umstellen,
   Dienst neu starten. *Vorziehen: repariert 45 % der VP-Engineering-Fehler (siehe
   „Nebenbefund: die Cloud-Agenten scheitern an der lokalen Farm").*
5. **`openbiollm-llama3-8b`** vom NAS auf den Mac kopieren; laden erst nach MacBook-Aus.
   **Nach jedem Reload prüfen, ob Thinking noch aus ist** — das Gemma-Jinja-Template mit
   `{%- set enable_thinking = false -%}` ist am 22.08. schon einmal bei einem Reload
   verlorengegangen (34 denkende Aufrufe an genau diesem Tag, sonst null).
6. **`fallbackModel` leeren** bei allen 38 Agenten.
7. **Zeitfelder setzen** — `timeoutMs`, `maxRunSeconds`, `maxIterations`; bei
   Dr-Knowledge `timeoutMs` erstmalig.
8. **`maxConcurrentRuns`** auf 1 bzw. 2 — bei sieben Agenten von einer ausdrücklichen 20.
9. **Neun Agenten umhängen** — fünf MacBook-Waisen (SEO/GEO-Spezialist, Schlafcoach,
   Vault-Maintainer, Office & Admin, Dr-Knowledge), drei Cloud-Rückkehrer
   (n8n-Betriebsingenieur, Social Media & Community, Link-Detektor) und der
   `lmstudio_local`-Link-Detektor auf den Mac.
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
| Erfolgsquote CRO (1 Slot → 5) | 11 % | **> 70 %** |
| Erfolgsquote n8n-Betriebsingenieur (Cloud → lokal) | 13 % | **> 70 %** |
| `blocked_by_pii_proxy` bei VP Engineering | 50 / 7 T | **< 5** |
| Overflows `google/gemma-4-12b` | 220 / 30 T | **< 20** |
| Swap Mac Studio | 7,4 / 8 GB | **< 4 GB** |

Wird die Timeout-Quote nicht erreicht, greift in dieser Reihenfolge: analytische Agenten
von Gemma auf die MoE ziehen (Vitals-Monitor, LLM-Konfigurationsanalyst, Label Manager) →
Slots zwischen den beiden Modellen umverteilen → Stufe B.

**VP Engineering bleibt bewusst außerhalb der Erfolgsziele.** Seine 429-Fehler (21 %)
adressiert dieser Entwurf nicht.

## Was bei der Umsetzung anders kam

Umgesetzt am 25.08. zwischen 14:30 und 15:05. Vier Abweichungen vom Entwurf, alle belegt:

**1. Das Fenster 65.536 ist produktiv gescheitert und wurde zurückgenommen.**

| Zeitfenster | Runs | Erfolg | Timeout | Kontextüberlauf |
|---|---|---|---|---|
| vorher (07–09 Uhr, 98.304 / 262.144) | 162 | 36 % | 15 % | 21 % |
| 65.536 × 8 / × 12 (10:00–14:35) | 301 | 18 % | **5 %** | **55 %** |
| dazu die DB-Änderungen (14:35–14:56) | 21 | **0 %** | 0 % | **67 %** |
| Rollback auf 98.304 × 5 / × 8 | — | — | — | **0** |

Die Slot-Erhöhung hat die Timeouts von 60–76 % auf 5 % gebracht — das war der Hebel und er
hält. Die Fensterverkleinerung hat gleichzeitig die Überläufe von 21 % auf 67 % getrieben.
Beides sind unabhängige Effekte derselben Änderung; nur der zweite wurde zurückgenommen.

**Wie der Fehler zunächst übersehen wurde:** Die erste Auswertung nach der Umstellung zeigte
„kein Aufruf mehr über 65.536, p99 von 75.000 auf 46.000 gefallen" und wurde als Beleg
gelesen, dass die Kürzung greift. Sie war aus den LM-Studio-Logs gezogen — und die enthalten
nur **erfolgreiche** Aufrufe. Der p99 fiel, weil die großen Aufrufe scheiterten statt
durchzugehen. Dieselbe Falle ist in `ctx-stats` schon einmal aufgetreten.

**2. Die Speicherrechnung in Gigabyte war falsch.** Siehe „Speicherrechnung". Gerechnet wird
jetzt in Slot-Token gegen einen nachweislich getragenen Zustand.

**3. `google/gemma-4-12b` bekommt 65.536 statt 16.384** — Link-Detektors Maximum liegt bei
47.180 Token, nicht bei seinem p50 von 0.

**4. `google/gemma-4-12b-qat` war bereits gelöscht.** Der Migrationsschritt „von RTX auf Mac
verlagern" ging damit ins Leere; stattdessen wurde der PII-Proxy auf `google/gemma-4-12b`
umgestellt.

**Dr-Knowledge:** `openbiollm-llama3-8b` aus `/Volumes/WHITESTAG-ARCHIV/LM Studio Modelle/`
zurückgeholt, 5.732.986.720 Byte byte-identisch. Laden erst möglich, **wenn das MacBook aus
ist** — beide Kopien tragen denselben `modelKey`, und `lms load` kennt keinen Geräteschalter.

**Zehn Agenten** mussten über `POST /agents/:id/resume` aus `error` geholt werden. Sechs
standen auf `escalated_human`, wo bei uns niemand benachrichtigt wird (Buchhaltung bei 73
Versuchen, Link-Detektor bei 32, Creative Assistant bei 29).

## Bewusst zurückgestellt

| Punkt | Grund |
|---|---|
| **`BUDGET_LOOKUP_THRESHOLD_TOKENS` senken** | Die Konstante 32.000 im Adapter zwingt uns auf ein Mindestfenster von ~74.000 und kostet damit Slots. Auf ~20.000 gesenkt (oder besser: aus dem tatsächlichen Budget abgeleitet statt hart verdrahtet) wären 65.536 × 8 / × 12 wieder möglich — rund 60 % mehr Bearbeitungsplätze. Braucht Codeänderung, Build und Deploy im laufenden Betrieb. |
| **Cloud-Rückkehrer** | n8n-Betriebsingenieur und Social Media & Community bleiben vorerst auf `claude_local`. Der Wechsel des `adapter_type` ist der riskanteste Schritt und wurde nicht auf eine gerade erst stabilisierte Farm gestapelt. Vom MacBook sind beide nicht betroffen. |
| **Flottenweite Obergrenze (Stufe B)** | Braucht Servercode. Erst messen, ob 47 reicht. Entwurf: zusätzlicher Zähler über alle Agenten vor `startNextQueuedRunForAgent`, Startwert 12. |
| **Prompt-Caching** | Größter bekannter Hebel (`cachedInputTokens: 0` überall), aber eigene Untersuchung — betrifft Adapter und LM-Studio-Slotverhalten. |
| **Zielarchitektur mit 2× 512 GB** | Eigener Entwurf. Kernthese: große MoE-Modelle auf die Macs, dichte auf die RTX — belegt durch 5 s gegen 25 s Median-Prefill bei gleicher Promptlänge auf derselben Maschine. |

## Risiken

**`gemma4-31b-it` trägt mit ~29 Agenten mehr als die halbe Flotte** und ist das langsame
dichte Modell (25 s Median-Prefill gegen 5 s bei der MoE). Mit 12 statt 4 Slots ist das
Risiko weitgehend abgeräumt — ermöglicht durch den Verzicht auf das lokale Coding-Modell.
Bleibt es dennoch der Engpass, ist der nächste Schritt, analytische Agenten auf die MoE zu
ziehen (Vitals-Monitor, LLM-Konfigurationsanalyst, Label Manager brauchen kein kreatives
Deutsch).

**Kein Cloud-Ventil.** Übersteigt die Last dauerhaft die Kapazität beider Knoten, gibt es
keinen Ausweg außer Warten. Genau das ist gewollt — ein wartender Run kostet nichts, ein
gestarteter und gestorbener kostet Rechenzeit und erzeugt Nacharbeit.

**Die RTX wird zum alleinigen Träger der Agentenflotte.** Fällt sie aus, steht die Firma.
Im Übergang bewusst hingenommen: sie trägt heute bereits 89 %, und ein zweiter Knoten, der
in den Timeout läuft, erhöht die Verfügbarkeit nicht.

**VP Engineering bleibt bei 429ern verwundbar.** Er behält `claude-sonnet-5`, damit auch
die Anthropic-Ratenbegrenzung. 21 % seiner Fehler kommen von dort, und ein einzelner 429
beendet bei `claude_local` den kompletten Run. Dieser Entwurf repariert seine anderen 45 %
(PII-Klassifikator), aber nicht diesen Anteil — das ist ein eigener Vorgang.

**Der n8n-Betriebsingenieur verliert Coding-Qualität.** n8n-Reparatur bedeutet JSON und
JavaScript in Code-Nodes; `abiray/qwen3.6-35b-a3b` ist ein Allzweckmodell. Bewusst
abgewogen gegen seinen Ist-Zustand von 13 % Erfolg — die 77 % 429-Fehler verschwinden
lokal vollständig. Verschlechtert sich die Reparaturqualität sichtbar, ist die Rückkehr
zu einem lokalen Coding-Modell möglich — dann aber nur gegen Slots, denn die RTX ist mit
1.277.952 Slot-Token nahe an dem Wert, der nachweislich getragen wird.

*Stand 25.08.: nicht umgesetzt — beide Cloud-Agenten laufen vorerst weiter auf
`claude_local`.*

**Dr-Knowledge verliert nichts.** Das Fachmodell zieht mit auf den Mac.
