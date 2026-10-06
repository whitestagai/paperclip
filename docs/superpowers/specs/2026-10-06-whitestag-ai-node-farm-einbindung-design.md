# WHITESTAG-AI als Redundanz-Node der LLM-Farm

**Stand:** 2026-10-06
**Status:** Entwurf zur Freigabe
**Betrifft:** `~/.paperclip/scripts/model-warden/`, `~/.paperclip/scripts/modell-wacht/`,
`agents.adapter_config.fallbackModel` in der Paperclip-DB, LM-Studio-Ladezustand am Node

## Ziel

Der LM-Link-Node **WHITESTAG-AI** ist angeschlossen, haelt zwei Modelle im
Speicher und traegt null Last. Er wird **Fallback-Geraet fuer beide
Modellfamilien** — die Primaerlast bleibt vollstaendig dort, wo sie heute
liegt.

Das loest ein konkretes Problem: **fuer 25 von 37 Agenten liegt der Fallback
heute auf derselben Maschine wie das Primaermodell.** Faellt das Studio aus
oder ist es ueberlastet, greift ihr Fallback ins Leere.

### Warum nicht Lastverteilung

Die zuerst verfolgte Variante (Agenten auf den Node umziehen) wurde nach der
Messung verworfen:

- Der Node ist das **schwaechste Geraet** der Farm: 56 GB VRAM gegen 96 GB
  (rtx) und 128 GB (studio), qwen in Q6_K statt Q8_0.
- Bei 48,99 GB Gewichten bleiben ~6,5 GiB fuer zwei KV-Caches mit je 98.304
  Fenster — realistisch 2 Slots je Modell. Die 12 qwen-Agenten laufen heute
  auf **4** Slots an der rtx. Ein Umzug waere eine Halbierung der Kapazitaet
  bei gleichzeitig niedrigerer Quantisierung, also keine Entlastung.
- Als Fallback-Geraet sind 2 Slots dagegen angemessen: Fallback-Last ist
  selten und kurz.

**Preis dieser Entscheidung:** Der Node traegt im Normalbetrieb weiterhin
nahe null Last. Entlastung von rtx und studio wird gegen Ausfallsicherheit
getauscht.

### Warum nicht beide Modelle auf die rtx

Der Gedanke, die Primaerlast beider Familien tagsueber auf der rtx zu
bedienen, scheitert am VRAM: 38,69 (qwen Q8_0) + 7,15 (gemma-4-12b-qat) +
18,69 (gemma-31b) = **64,53 GB Gewichte**. Am 2026-08-26 loeste die rtx bei
**62,94 GB** die Timeout-Welle aus (28 Timeouts in einer Stunde, GPU-Offload
24 von 40 Layern). Der Vorschlag wuerde den Vorfall mit mehr Gewichten als
damals reproduzieren. gemma-31b bleibt auf dem studio.

### Warum kein Tag/Nacht-Betrieb

Das `when`-Feld im Resident-Set (`always` / `day-only`) wird **von keinem
Code gelesen** — in `warden.py` und `evict.py` gibt es keine Zeitlogik, und
fuer den Lader existiert keine plist, er laeuft nicht. Eine Zeitsteuerung
muesste gebaut werden. Fuer ein Fallback-Geraet ist sie unerwuenscht: der
Fallback soll greifen, wenn das Primaermodell wegbricht — nachts ebenso.

## Ist-Stand (gemessen am 2026-10-06)

### Geraete

| Rolle | Name | Hardware | deviceIdentifier |
|---|---|---|---|
| `studio` | MacStudioM4Max128 | Apple M4 Max, 128 GB Unified | `9f59ca8364db547bb8ca3b6185f1c844` |
| `rtx` | RTX Pro 6000 | 96 GB VRAM | `3f6d2489f519c745243a6c4daa0334d5` |
| **neu** | **WHITESTAG-AI** | **Windows, RTX 5090 (32 GB) + RTX 3090 (24 GB) = 56 GB VRAM** | `55fb4392eb9f978c1bc68abfef0c4b59` |

WHITESTAG-AI ist **nicht** das Geraet, das im Resident-Set als `macbook`
steht; jener Eintrag (`qwen3.6-35b-a3b-mlx`) ist unveraendert aus dem Juli.

### Fallback-Verdrahtung

39 Agenten laufen mit `adapter_type = lmstudio_local`, 9 mit `claude_local`.
Primaer- und Fallback-URL sind bei 38 Agenten **identisch**
(`http://localhost:1234`) — die Geraetewahl erfolgt also ausschliesslich
ueber die Modell-ID, nicht ueber die URL. `fallbackUrl` muss nicht angefasst
werden.

| Agenten | Primaer | Fallback | Geraetetrennung |
|---|---|---|---|
| 25 | `google/gemma-4-31b` (studio) | `google/gemma-4-12b` (studio) | **nein** |
| 12 | `qwen3.6-35b-a3b` (rtx) | `google/gemma-4-12b` (studio) | ja |
| 2 | openbiollm / gemma-4-12b | kein Fallback | — |

Die Auflösung sitzt in `endpoint-resolver.ts`: `model: p.fallbackModel ||
p.primaryModel`. Ist `fallbackModel` leer, wird das Primaermodell erneut
versucht — dann gibt es faktisch keinen Fallback (derselbe Fehler wie beim
PII-Proxy vor dem 2026-10-04).

### Quantisierungen weichen je Geraet ab

| Familie | Primaer heute | am Node | Sprung |
|---|---|---|---|
| qwen3.6-35b-a3b | rtx: **Q8_0**, 36,03 GiB | **Q6_K**, 28,22 GiB | eine Stufe |
| gemma-4-31b | studio: **MLX 8-bit** | **GGUF Q4_K_M**, 17,40 GiB | 8 bit -> 4 bit |

Fuer die Fallback-Rolle ist das hinnehmbar: der Fallback ersetzt heute ein
**12B**-Modell. Ein 31B in Q4_K_M bzw. ein 35B in Q6_K ist in beiden Faellen
ein deutlicher Qualitaetsgewinn gegenueber dem Status quo.

Auf dem Node liegt zusaetzlich `lmstudio-community/qwen3.6-35b-a3b` in
Q4_K_M (20,55 GiB, nicht geladen). **Entscheidung: Q6_K bleibt** — als
Fallback ist die Kapazitaet nicht der Engpass.

**Falle:** `gemma-4-31b-it@q8_0` am Node ist mit 1,26 GB ein Fragment
(ein 31B in Q8 waere rund 33 GB). Nicht laden.

### Geschwindigkeit (Medianwerte, je 3-4 Laeufe)

| Modell | Generierung | Zeit bis fertige Antwort |
|---|---|---|
| `gemma-4-31b-it` (Node) | 42,4 tok/s (±1) | 2,98 s |
| `abiray/qwen3.6-35b-a3b` (Node) | 81-89 tok/s | 9,86 s |
| dto., Reasoning abgeschaltet | 81 tok/s | 1,85 s |

Die Generierungsrate ist auf ±1 tok/s reproduzierbar. Das **Prefill schwankt
um Faktor 3** (gemma 406-1.211 tok/s, im Wechsel gemessen) — Verdacht auf
KV-Platzmangel mit Layer-Offload. Fuer die Fallback-Rolle unkritisch, aber
Teil der Abnahme.

## Randbedingungen

1. **ctx 98.304 ist Untergrenze, nicht Zielwert.** Solange im Adapter
   `BUDGET_LOOKUP_THRESHOLD_TOKENS = 32000` steht, wird unterhalb dieser
   Schaetzung weder das Fenster abgefragt noch gekuerzt. Der Versuch mit
   65.536 am 2026-08-25 trieb die Ueberlaeufe auf 67 % und die Erfolgsquote
   auf 0. Gilt auch fuer Fallback-Modelle — ein Fallback mit zu kleinem
   Fenster ist keiner.

2. **LM Link verteilt keine Last.** `preferredDeviceIdentifier` ist ein
   globaler Einzelwert fuer die Modellauflösung. Eindeutige IDs sind deshalb
   Pflicht, damit ein Fallback nachweisbar auf dem Node landet.

3. **`lms load` hat kein Geraete-Flag.** Es laedt auf das preferred device.
   Der Rename geschieht darum **am Windows-PC**, nicht vom studio aus.

4. **`--estimate-only` taugt nicht zur Kapazitaetsplanung.** Es meldet fuer
   `gemma-4-31b-it@q4_k_m` bei ctx 98.304 und `--parallel 2` genau
   17,40 GiB — die reine Gewichtsgroesse, ohne KV und ohne `parallel`,
   `Confidence: LOW`, und geschaetzt gegen die lokale Maschine.

5. **Der Entlade-Waerter ist unkritisch.** `evict.py` filtert auf
   `device == "studio"` und ueberspringt Instanzen mit gesetztem
   `deviceIdentifier`. Aber `config.py` wirft `ValueError: Unbekanntes
   device`, wenn ein Eintrag ein Geraet nennt, das nicht in `devices` steht.

6. **Die beiden Node-IDs sind historisch verbrannt.** `gemma-4-31b-it` und
   `abiray/qwen3.6-35b-a3b` wurden am 2026-10-03 als nicht existierende IDs
   aus allen Konfigurationen entfernt; sie waren die Ursache von 204
   `max_iterations`-Fehlern in 14 Tagen. Derzeit zeigt keine Konfiguration
   auf sie — deshalb ist jetzt der einzige gefahrlose Zeitpunkt zum Rename.

## Voraussetzung: der Node muss always-on sein

Ein Fallback auf ein Geraet, das zeitweise aus ist, ist **schlechter** als
der heutige Fallback auf `google/gemma-4-12b` am dauerhaft laufenden studio.
Die Nacht-Architektur vom 2026-08-23 fuehrt studio, macbook und rtx als
always-on — WHITESTAG-AI steht dort nicht.

**Diese Umstellung ist nur sinnvoll, wenn der Node dauerhaft laeuft und
erreichbar bleibt.** Ist das nicht gegeben, bleibt der 12B-Fallback die
bessere Wahl. Zu bestaetigen vor Schritt 1.

## Entscheidungen

| Frage | Entscheidung | Begruendung |
|---|---|---|
| Rolle | **reines Fallback-Geraet**, keine Primaerlast | Hardware taugt fuer seltene Last; behebt die fehlende Geraetetrennung bei 25 Agenten |
| Namen | Rename auf `gemma-4-31b-win` / `qwen3.6-35b-win` | Suffix nennt das Geraet; vermeidet Kollision mit den verbrannten IDs; jetzt gefahrlos, weil nichts darauf zeigt |
| Ausfuehrung | Walter am Windows-PC | kein globaler `set-preferred-device`-Schalter, keine Kollision mit dem Waerter |
| Quantisierung | qwen bleibt **Q6_K** | als Fallback ist Kapazitaet nicht der Engpass; Qualitaet geht vor |
| Slots | `--parallel 2` je Modell | konservativ; 4+4 fordern 1,57 Mio Slot-Token aus ~6,5 GiB |
| PII-Proxy | **nicht anfassen** | dessen Geraetetrennung ist bereits bewusst gesetzt |

## Zielzustand

- Node fuehrt `gemma-4-31b-win` und `qwen3.6-35b-win`, je ctx 98.304,
  `parallel 2`.
- Resident-Set kennt das Geraet `whitestag-ai` mit beiden Modellen.
- `soll-laufzeit.json` fuehrt beide Modelle begruendet; die Modell-Aufsicht
  laeuft ohne Befund durch.
- Die 25 gemma-Agenten haben `fallbackModel = gemma-4-31b-win`.
- Die 12 qwen-Agenten haben `fallbackModel = qwen3.6-35b-win`.
- Kein Agent hat Primaermodell und Fallback auf demselben Geraet.
- Primaerlast unveraendert: 25 gemma-Agenten am studio, 12 qwen-Agenten an
  der rtx, C-Suite weiterhin Q8_0 mit 4 Slots.

## Vorgehen

### Schritt 0 — Rueckweg sichern

`agent_config_revisions` (1.131 Eintraege) haelt `before_config` je
Aenderung. Zusaetzlich wird der Ist-Stand der 37 betroffenen
`fallbackModel`-Werte separat als JSON abgelegt, damit der Rueckweg nicht
allein von der Revisionstabelle abhaengt.

### Schritt 1 — Rename am Node

Am Windows-PC, je Modell entladen und mit neuem Identifier laden:

    lms unload gemma-4-31b-it
    lms load gemma-4-31b-it@q4_k_m --identifier gemma-4-31b-win -c 98304 --parallel 2 -y
    lms unload abiray/qwen3.6-35b-a3b
    lms load abiray/qwen3.6-35b-a3b --identifier qwen3.6-35b-win -c 98304 --parallel 2 -y

Gegenprobe vom studio: `lms link status` und `GET /api/v0/models/<id>` je
neuer ID — `/api/v0/models` allein ist unvollstaendig.

### Schritt 2 — Waechter-Dateien nachziehen

`resident-set.json`: `whitestag-ai` in `devices`, beide Modelle mit
Begruendung. `soll-laufzeit.json`: beide Modelle mit `contextLength` und
`parallel`. Die Tests unter `model-warden/` muessen gruen bleiben;
`modell-wacht/pruefung.py` muss mit Exit 0 durchlaufen.

### Schritt 3 — Fallback nachweislich ausloesen (vor der Umstellung)

Ein unerprobter Fallback ist wertlos, und dieser Codepfad hatte am
2026-07-07 bereits einen Bug (RAM-Guardrail-400 schaltete nicht um). Vor der
Umstellung aller Agenten wird an **einem** unkritischen Agenten geprueft:
`fallbackModel` auf die Node-ID setzen, Primaermodell kurz unerreichbar
machen, und im Lauf-Log nachweisen, dass `usingFallback` greift und der Lauf
auf dem Node erfolgreich endet.

### Schritt 4 — Umstellung in zwei Wellen

**Welle A:** die 25 gemma-Agenten auf `gemma-4-31b-win`. 24 Stunden
beobachten.
**Welle B:** die 12 qwen-Agenten auf `qwen3.6-35b-win`.

## Erfolgskriterien

1. Schritt 3 belegt einen Fallback-Lauf auf dem Node mit erfolgreichem
   Abschluss — nicht nur eine gesetzte Konfiguration.
2. Kein Agent mit Primaermodell und Fallback auf demselben Geraet
   (heute: 25 Verstoesse).
3. Keine neuen `max_iterations`-Fehler gegenueber der Vorwoche.
4. `modell-wacht/pruefung.py` ohne Befund.
5. Primaerlast unveraendert — `cost_events` je Modell zeigt nach 7 Tagen
   dieselbe Verteilung wie heute (526 / 220 / 155).

## Risiken

| Risiko | Gegenmittel |
|---|---|
| Node zeitweise aus -> Fallback schlechter als heute | Always-on-Voraussetzung vor Schritt 1 bestaetigen |
| Fallback-Pfad schaltet nicht um (Bug vom 07.07.) | Schritt 3 als Nachweis vor jeder Massenumstellung |
| Verwechslung der neuen IDs mit den verbrannten | Geraete-Suffix im Namen; Eintrag in beiden Waechter-Dateien |
| Tippfehler in der ID -> stiller Rueckfall aufs Primaermodell | `fallbackModel || primaryModel` beachten; Gegenprobe per `GET /api/v0/models/<id>` |
| KV-Platzmangel am Node unter Fallback-Last | `parallel 2`; Prefill-Streuung bei der Abnahme messen |

## Nicht Teil dieser Arbeit

- **Reasoning-Abschaltung bei qwen3.6.** Gemessen: ein leerer
  `<think></think>`-Block als Assistant-Prefill senkt die Antwortzeit von
  9,86 s auf 1,85 s; `reasoning_effort: none` wirkt bei diesem Modell nicht
  (eher gegenteilig), `/no_think` wird ignoriert. Hebel sitzt im Adapter.
- **`maxConcurrentRuns`.** Nur bei **1** von 48 Agenten gesetzt.
- **`when`-Feld ohne Wirkung.** Das Resident-Set fuehrt `day-only`, aber
  kein Code liest es und `warden.py` laeuft nicht.
- **Die 2 Agenten ohne Fallback** (openbiollm, gemma-4-12b).
