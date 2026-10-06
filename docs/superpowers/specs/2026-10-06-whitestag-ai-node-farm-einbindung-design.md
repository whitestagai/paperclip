# WHITESTAG-AI als dritter Node der LLM-Farm

**Stand:** 2026-10-06
**Status:** Entwurf zur Freigabe
**Betrifft:** `~/.paperclip/scripts/model-warden/`, `~/.paperclip/scripts/modell-wacht/`,
`agents.adapter_config` in der Paperclip-DB, LM-Studio-Ladezustand auf dem Node

## Ziel

Der LM-Link-Node **WHITESTAG-AI** ist angeschlossen, hält zwei Modelle im
Speicher und traegt **null Last** — in den letzten sieben Tagen null Aufrufe,
null Agenten. Er soll zwei Rollen uebernehmen:

1. **RTX Pro 6000 entlasten** — dort haengen alle 12 qwen-Agenten.
2. **Mac Studio entlasten** — dort haengen 25 gemma-Agenten plus 37 Fallbacks,
   der PII-Fallback-Klassifikator, der Clara-Tagger und beide Einbettungsmodelle.

## Ist-Stand (gemessen am 2026-10-06)

### Geraete

| Rolle | Name | Hardware | deviceIdentifier |
|---|---|---|---|
| `studio` | MacStudioM4Max128 | Apple M4 Max, 128 GB Unified | `9f59ca8364db547bb8ca3b6185f1c844` |
| `rtx` | RTX Pro 6000 | 96 GB VRAM | `3f6d2489f519c745243a6c4daa0334d5` |
| **neu** | **WHITESTAG-AI** | **Windows, RTX 5090 (32 GB) + RTX 3090 (24 GB) = 56 GB VRAM** | `55fb4392eb9f978c1bc68abfef0c4b59` |

WHITESTAG-AI ist **nicht** das Geraet, das im Resident-Set als `macbook`
steht. Der dortige Eintrag (`qwen3.6-35b-a3b-mlx`) ist unverändert aus dem
Juli und betrifft eine andere Maschine.

### Lastverteilung, 7 Tage

| Geraet | Modell | Aufrufe | kTok | Agenten |
|---|---|---|---|---|
| studio | `google/gemma-4-12b` | 526 | 52.233 | Fallback von 37, PII-Fallback, Clara-Tagger |
| studio | `google/gemma-4-31b` | 220 | 23.273 | 25 |
| rtx | `qwen3.6-35b-a3b` | 155 | 37.077 | 12 (inkl. gesamter C-Suite) |
| — | `claude-sonnet-4-6` | 25 | 196 | 4 |
| **whitestag-ai** | beide geladen | **0** | **0** | **0** |

### Geladener Zustand auf dem Node

| Identifier | modelKey | Groesse | ctx | parallel |
|---|---|---|---|---|
| `gemma-4-31b-it` | `gemma-4-31b-it@q4_k_m` | 18,69 GB | 98.304 | 4 |
| `abiray/qwen3.6-35b-a3b` | dito | 30,30 GB | 98.304 | 4 |

Summe Gewichte **48,99 GB bei 56 GB VRAM**. Die beiden Modelle fordern
zusammen 1,57 Mio Slot-Token (2 × 98.304 × 4) aus den verbleibenden ~7 GB.

### Geschwindigkeit (Medianwerte, je 3-4 Laeufe)

| Modell | Generierung | Zeit bis fertige Antwort |
|---|---|---|
| `gemma-4-31b-it` | 42,4 tok/s (±1) | 2,98 s |
| `abiray/qwen3.6-35b-a3b` | 81-89 tok/s | 9,86 s |
| dto., Reasoning abgeschaltet | 81 tok/s | **1,85 s** |

Die Generierungsrate ist ueber alle Laeufe auf ±1 tok/s reproduzierbar.
Das **Prefill schwankt um Faktor 3** (gemma 406-1.211 tok/s, im Wechsel
gemessen) — der Verdacht ist KV-Platzmangel mit Layer-Offload auf die CPU,
also derselbe Engpass wie auf der RTX am 2026-08-26 (28 Timeouts in einer
Stunde bei GPU-Offload 24 von 40 Layern).

## Randbedingungen

1. **ctx 98.304 ist Untergrenze, nicht Zielwert.** Solange im
   lmstudio-Adapter `BUDGET_LOOKUP_THRESHOLD_TOKENS = 32000` steht, wird
   unterhalb dieser Schaetzung weder das Fenster abgefragt noch gekuerzt.
   Der Versuch mit 65.536 am 2026-08-25 trieb die Ueberlaeufe auf 67 % und
   die Erfolgsquote auf 0. **VRAM darf nicht ueber kleinere Fenster
   gespart werden** — der einzige Hebel ist `parallel`.

2. **LM Link verteilt keine Last.** `preferredDeviceIdentifier` ist ein
   globaler Einzelwert fuer die Modellauflösung, kein Lastverteiler. Zwei
   Geraete mit derselben Modell-ID bedeuten: alles geht an das bevorzugte
   Geraet. Lastteilung ist nur ueber **eindeutige IDs plus explizite
   Agent-Zuordnung** erreichbar.

3. **`lms load` hat kein Geraete-Flag.** Es laedt auf das preferred device.
   Ein Rename vom Studio aus erfordert das globale Umschalten und ein
   Zeitfenster, in dem jeder andere Ladevorgang auf dem Node landet —
   bei einem Entlade-Waerter im 10-Minuten-Takt ein Risiko.

4. **`--estimate-only` taugt nicht zur Kapazitaetsplanung.** Es meldet fuer
   `gemma-4-31b-it@q4_k_m` bei ctx 98.304 und `--parallel 2` genau
   17,40 GiB — die reine Gewichtsgroesse. KV-Cache und `parallel` gehen
   nicht ein, `Confidence: LOW`, und geschaetzt wird gegen die lokale
   Maschine, nicht gegen den Node.

5. **Der Entlade-Waerter ist unkritisch.** `evict.py` filtert auf
   `device == "studio"` und ueberspringt Instanzen mit gesetztem
   `deviceIdentifier`. Er fasst den Node nicht an. Aber `config.py`
   wirft `ValueError: Unbekanntes device`, wenn ein Eintrag ein Geraet
   nennt, das nicht in `devices` steht.

6. **Die beiden Node-IDs sind historisch verbrannt.** `gemma-4-31b-it` und
   `abiray/qwen3.6-35b-a3b` wurden am 2026-10-03 als nicht existierende IDs
   aus allen Konfigurationen entfernt; sie waren die Ursache von 204
   `max_iterations`-Fehlern in 14 Tagen. Derzeit zeigt **keine** Konfiguration
   auf sie — deshalb ist jetzt der einzige gefahrlose Zeitpunkt fuer einen
   Rename.

## Entscheidungen

| Frage | Entscheidung | Begruendung |
|---|---|---|
| Namen | **Rename auf `gemma-4-31b-win` / `qwen3.6-35b-win`** | Suffix nennt das Geraet; vermeidet die Kollision mit den verbrannten IDs. Jetzt gefahrlos, weil nichts darauf zeigt. |
| Ausfuehrung | **Walter am Windows-PC** | Kein globaler `set-preferred-device`-Schalter, keine Kollision mit dem Waerter. |
| C-Suite | **zieht mit um** (alle 12 qwen-Agenten) | Entscheidung Walters am 2026-10-06. Die Empfehlung lautete, CEO/CTO/CPO/CRO/CHO auf der RTX zu lassen, weil die Slot-Kapazitaet des Node unbekannt ist. Konsequenz: die Kapazitaetsmessung wird **Vorbedingung** statt Begleitmaßnahme, und der Rueckweg muss vor der ersten Umstellung stehen. |
| Fallbacks | bleiben auf `google/gemma-4-12b` (studio) | Anderes Geraet als das Primaermodell — Lehre vom 2026-09-22. |

## Zielzustand

- Node fuehrt `gemma-4-31b-win` und `qwen3.6-35b-win`, beide ctx 98.304,
  `parallel` nach Messergebnis.
- Resident-Set kennt das Geraet `whitestag-ai` mit beiden Modellen.
- `soll-laufzeit.json` fuehrt beide Modelle mit begruendeten Werten; die
  Modell-Aufsicht laeuft ohne Befund durch.
- Alle 12 qwen-Agenten zeigen auf `qwen3.6-35b-win`.
- Beide Vault-Maintainer zeigen auf `gemma-4-31b-win`; weitere der 25
  gemma-Agenten nach Bedarf und Messlage.
- Fallback jedes umgezogenen Agenten liegt auf einem anderen Geraet.

## Vorgehen

### Schritt 0 — Rueckweg sichern (vor allem anderen)

`agent_config_revisions` (1.131 Eintraege) haelt `before_config` je Aenderung.
Vor der ersten Umstellung wird der Ist-Stand der betroffenen
`adapter_config`-Felder separat als JSON abgelegt, damit der Rueckweg nicht
von der Revisionstabelle allein abhaengt.

### Schritt 1 — Slot-Kapazitaet messen

Der tragbare Wert fuer `parallel` ist vom Mac aus nicht auslesbar und muss
unter Last ermittelt werden. Gemessen wird bei gestaffelter Slot-Zahl
(4+4, 2+2, 1+1) jeweils Generierungsrate und Prefill-Streuung unter
parallelen Anfragen. **Abbruchkriterium:** Prefill-Streuung ueber Faktor 2
oder Generierungsrate unter 35 tok/s (gemma) bzw. 70 tok/s (qwen) deutet
auf Layer-Offload und schliesst die Stufe aus.

### Schritt 2 — Rename auf dem Node

Auf dem Windows-PC, je Modell entladen und mit neuem Identifier laden:

    lms unload gemma-4-31b-it
    lms load gemma-4-31b-it@q4_k_m --identifier gemma-4-31b-win -c 98304 --parallel <N> -y
    lms unload abiray/qwen3.6-35b-a3b
    lms load <modelKey> --identifier qwen3.6-35b-win -c 98304 --parallel <N> -y

Gegenprobe vom Studio: `lms link status` und `GET /api/v0/models/<id>` je
neuer ID — `/api/v0/models` allein ist unvollstaendig.

### Schritt 3 — Waechter-Dateien nachziehen

`resident-set.json`: `whitestag-ai` in `devices`, beide Modelle mit
Begruendung. `soll-laufzeit.json`: beide Modelle mit `contextLength` und
`parallel`. Die Tests unter `model-warden/` (`test_config.py`,
`test_evict.py`) muessen gruen bleiben; `modell-wacht/pruefung.py` muss
mit Exit 0 durchlaufen.

### Schritt 4 — Umzug in zwei Wellen

**Welle A:** die 7 unkritischen qwen-Agenten (Blender, Bueroleitung,
Online-Rechercheur, Recherche, SEO/GEO-Spezialist, Sekretaerin,
Trainingscoach) plus beide Vault-Maintainer. 24 Stunden beobachten.

**Welle B:** die C-Suite (CEO, CTO, CPO, CRO, CHO) — erst wenn Welle A
die Erfolgskriterien erfuellt.

## Erfolgskriterien

1. Keine neuen `max_iterations`-Fehler bei den umgezogenen Agenten
   gegenueber der Vorwoche.
2. Prefill-Streuung unter Last kleiner als Faktor 2.
3. Aufrufe je Geraet nachweisbar verschoben (`cost_events` nach Modell).
4. `modell-wacht/pruefung.py` ohne Befund.
5. Kein Agent mit Primaermodell und Fallback auf demselben Geraet.

## Risiken

| Risiko | Gegenmittel |
|---|---|
| Node traegt die C-Suite-Last nicht | Schritt 1 als Vorbedingung; Welle B erst nach 24 h Welle A |
| Verwechslung der neuen IDs mit den verbrannten | Geraete-Suffix im Namen; Eintrag in beiden Waechter-Dateien |
| Stiller Fallback bei Tippfehler in der ID | Gegenprobe `GET /api/v0/models/<id>`; Aufrufe je Modell nach 24 h pruefen |
| Node faellt aus (Windows, WLAN) | Fallback liegt auf dem Studio; bei Ausfall greift `google/gemma-4-12b` |

## Nicht Teil dieser Arbeit

- **Reasoning-Abschaltung bei qwen3.6.** Gemessen: ein leerer
  `<think></think>`-Block als Assistant-Prefill senkt die Antwortzeit von
  9,86 s auf 1,85 s; `reasoning_effort: none` wirkt bei diesem Modell nicht
  (eher gegenteilig), `/no_think` wird ignoriert. Der Hebel sitzt im
  lmstudio-Adapter und ist ein eigener Vorgang.
- **`maxConcurrentRuns`.** Bei allen 48 Agenten derzeit nicht gesetzt.
  Eigener Befund, eigener Vorgang.
