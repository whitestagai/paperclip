# Modell-Aufsicht

Hält jede fest verdrahtete LM-Studio-Modell-ID im Haus gegen den tatsächlichen
Bestand. Der Wächter **repariert nichts** — er stellt fest und meldet.

## Warum

Am 22./23.08.2026 zog `qwen3.6-35b-a3b` vom MacBook auf die RTX und hieß danach
`abiray/qwen3.6-35b-a3b`. Drei Stellen zeigten weiter auf den alten Namen — und
keine davon fiel auf:

| Wo | Wie lange | Schaden |
|---|---|---|
| beide Obsidian-Tagger-Templates | seit dem Umzug | nächster echter Lauf wäre gescheitert |
| `ld.config` in **zwei** Link-Detektor-Datenbanken | seit dem Umzug | 233 Fehler an einem Tag, Dienst lief 24/7 ins Leere |
| `runtime_config.modelProfiles.cheap` bei 11 Agenten | eine Nacht | 641 von 642 cheap-Läufen auf dem falschen Gerät |

**Warum es niemand sah:** Ein toter Modellname taucht in der Statistik „Aufrufe
je Modell" **nicht auf** — er belastet ja kein Modell. Er erscheint nur als
`[ERROR] Invalid model identifier` im LM-Studio-Log, ohne Modell-Präfix, und
geht dort zwischen zehntausenden Zeilen unter.

## Aufbau

| Datei | Zweck |
|---|---|
| `pruefung.py` | reine Bewertungslogik, kein I/O — Regeln samt Begründung |
| `waechter.py` | sammelt die Referenzen, gibt JSON auf stdout |
| `test_pruefung.py` | die Ernstfälle: tote ID, unlesbare Quelle, Fehlalarm-Schutz |
| `test_waechter.py` | die Sammelfallen: Sticky Notes, Ausdrücke, cheap-Profil |

```sh
./waechter.py           # JSON
./waechter.py --text    # Klartext
```

Exitcode `1`, sobald ein Befund der Schwere `hoch` vorliegt, sonst `0`.

## Was geprüft wird

| Quelle | Felder |
|---|---|
| Paperclip-Agenten | `adapterConfig.model` / `.defaultModel` / `.fallbackModel` **und** `runtimeConfig.modelProfiles.<profil>.model` / `.fallbackModel` |
| Link-Detektor | `ld.config.llm_model` + `.embedding_model` in `link_detektor` **und** `link_detektor_clara` |
| n8n | literale Modell-Zuweisungen in `set`-Knoten aktiver Workflows |
| Obsidian-Tagger | `llm.modell` in beiden Templates |
| Wake-Satellit | `sat_config.CHAT_MODEL` |
| PII-Proxy | `PII_PROXY_CLASSIFIER_MODEL` + `..._FALLBACK_MODEL` aus der Plist |

Stand 23.08.: **158 Referenzen aus 6 Quellen**.

## Drei Entscheidungen, die nicht offensichtlich sind

**Das cheap-Profil wird aus `runtime_config` gelesen, nicht aus
`adapter_config`.** Beide Felder können dieselbe Struktur tragen; wirksam ist
ausschließlich `runtime_config` (`heartbeat.ts:7087` reicht
`agent.runtimeConfig` durch). Ein Wert im anderen Feld ist Dekoration — genau
daran ging die Nacht vom 22. auf den 23.08. verloren.

**Sticky Notes zählen nicht.** In vier aktiven n8n-Workflows stand die tote ID
— ausschließlich als Kommentar auf der Zeichenfläche. Wer sie mitzählt, meldet
vier Geister und schickt jemanden auf die falsche Fährte. (Ich bin genau darauf
hereingefallen.)

**Ausdrücke sind kein Befund.** Die Chat-Knoten beziehen ihr Modell über
`={{ $('Konfiguration')... }}`. Statisch nicht auflösbar; der literale Wert
steht im `set`-Knoten und wird dort abgegriffen. Den Ausdruck als „unbekanntes
Modell" zu melden wäre ein täglicher Fehlalarm.

## Fail-closed

Zwei Stellen, beide bewusst:

- **Eine unlesbare Quelle ist selbst ein Befund.** Kein „keine Fehler gefunden",
  wenn gar nicht nachgesehen werden konnte.
- **Antwortet LM Studio nicht, wird gar nicht geprüft.** Sonst wären auf einen
  Schlag alle 158 Referenzen „unbekannt" und der eine echte Befund ertränke in
  157 Fehlalarmen. Stattdessen genau ein Befund: der Bestand fehlt.

## Grenzen

- Modelle fremder Anbieter (`claude-`, `gpt-`, `gemini-`, …) werden übersprungen
  — sie stehen nie in `/v1/models`.
- n8n wird nur dort geprüft, wo der Modellname **literal** in einem `set`-Knoten
  steht. Wird ein Modell künftig anders durchgereicht, entsteht ein blinder
  Fleck, ohne dass der Wächter das meldet.
- Geprüft wird die **Existenz** einer ID, nicht ob das Modell für seine Aufgabe
  taugt und nicht, ob genug VRAM da ist.

## Läuft unter Python 3.9

launchd startet mit dem System-Python (3.9.6). Deshalb `Optional[x]` statt
`x | None`, keine Fremdpakete. Wer hier 3.10-Syntax einbaut, merkt es nicht beim
Entwickeln, sondern erst nachts im Dienst.

## Tests

```sh
python3 -m pytest -q     # 16 Tests
```

Jeder Test in `test_pruefung.py` ist ein Vorfall, der bereits passiert ist.
Zusätzlich gegen den echten Vorzustand geprüft: mit den Templates aus
`e8d522eb3^` meldet der Wächter beide toten IDs, mit dem heutigen Stand keinen
Befund.
