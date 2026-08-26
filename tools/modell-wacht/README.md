# Modell-Aufsicht

Hält jede fest verdrahtete LM-Studio-Modell-ID im Haus gegen den tatsächlichen
Bestand — und die geladenen Modelle gegen ihren Soll-Zustand. Der Wächter
**repariert nichts** — er stellt fest und meldet.

Drei Prüfungen, drei Fehlerbilder:

| Prüfung | Frage |
|---|---|
| `bewerte` | Zeigt eine Stelle auf einen Namen, den es nicht gibt? |
| `bewerte_laufzeit` | Name richtig, Modell aber falsch bedient (Fenster, Slots)? |
| `bewerte_drift` | Steht in der Datei etwas anderes als im laufenden Dienst? |

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

### Die zwei blinden Flecken vom 26.08.2026

An diesem Tag meldete die Aufsicht um 07:30 „120 Konfigurationen geprüft, keine
Inkonsistenzen" — während zwei echte Fehler liefen. Beide konnte sie
konstruktionsbedingt nicht sehen:

| Fehler | Schaden | Warum unsichtbar |
|---|---|---|
| PII-Proxy lief auf dem gelöschten `google/gemma-4-12b-qat` | 822 gescheiterte Klassifikator-Aufrufe an einem Tag | Geprüft wurde die **plist auf der Platte** — die war seit dem Vortag korrekt. launchd hatte die Änderung nie eingelesen. |
| beide RTX-Modelle auf Fenster 65.536 statt 98.304 (10:00–12:11) | 109 Kontextüberläufe, Erfolgsquote fiel auf 11 % | Geprüft wurde nur, ob eine ID **existiert und geladen ist**. Fenstergröße und Slotzahl kamen gar nicht vor. |

Die Lehre aus dem ersten Fall steckt jetzt im Code: **`kickstart -k` startet nur
den Prozess neu, nicht den Job.** Eine geänderte plist wird erst mit `bootout` +
`bootstrap` wirksam. Bis dahin sieht die Korrektur erledigt aus und ist es nicht.

## Aufbau

| Datei | Zweck |
|---|---|
| `pruefung.py` | reine Bewertungslogik, kein I/O — Regeln samt Begründung |
| `waechter.py` | sammelt die Referenzen, gibt JSON auf stdout |
| `melder.py` | halbstündlicher Takt: prüft, protokolliert, meldet bei Wechsel |
| `run-melder.js` | node-Türöffner für launchd (TCC, siehe unten) |
| `soll-laufzeit.json` | Soll-Fenster und -Slots je Modell, **mit Begründung** |
| `test_pruefung.py` | die Ernstfälle: tote ID, unlesbare Quelle, Fehlalarm-Schutz |
| `test_waechter.py` | die Sammelfallen: Sticky Notes, Ausdrücke, cheap-Profil |

```sh
./waechter.py           # JSON
./waechter.py --text    # Klartext
./melder.py             # prüfen + protokollieren + ggf. Issue anlegen
```

Exitcode `1`, sobald ein Befund der Schwere `hoch` vorliegt, sonst `0`.

## Zwei Takte

| Takt | Wie | Wozu |
|---|---|---|
| täglich 07:30 | Paperclip-Routine `Modell-Aufsicht (taeglich, 07:30)` | Bericht, auch wenn alles in Ordnung ist |
| alle 30 Minuten | launchd `ai.whitestag.modell-wacht` → `melder.py` | fängt kurze Vorfälle, meldet nur bei Wechsel |

Der halbstündliche Takt kostet nichts — `waechter.py` ist reines Python ohne
LLM. Er existiert, weil der Vorfall vom 26.08. von 10:00 bis 12:11 lief und ein
einzelner 07:30-Lauf ihn vollständig verpasst hätte.

**Gemeldet wird nur bei Zustandswechsel.** Ein Fehler, der zwei Stunden anhält,
erzeugt genau ein Issue — nicht vier. Die Signatur dafür lässt den Meldetext
bewusst weg, damit ein wackelnder Zahlenwert nicht als neuer Befund gilt. Der
Zustand in `~/.paperclip/logs/modell-wacht-last.json` wird bei **jedem** Lauf
fortgeschrieben, auch ohne Meldung — sonst bliebe ein behobener und wieder
auftretender Fehler beim zweiten Mal stumm.

### Zwei Fußangeln beim launchd-Betrieb

Beide beim ersten Probelauf am 26.08. real erlebt, beide fail-closed als harter
Befund sichtbar geworden statt still:

- **`PATH` muss `/opt/homebrew/bin` enthalten.** Der Wächter ruft `psql` ohne
  absoluten Pfad auf. Mit dem minimalen launchd-PATH sind zwei Quellen
  unlesbar — statt 122 Referenzen kommen nur noch 16 durch.
- **Start über `node`, nicht über `python3`.** macOS verweigert einem
  launchd-Job aus python/zsh den Zugriff auf die SynologyDrive-Freigabe
  („Operation not permitted", TCC). `node` hat die Berechtigung und vererbt sie
  an Kindprozesse. Ohne diesen Umweg sind Tagger-Templates und Wake-Satellit
  unlesbar und der Melder legt ein Fehlalarm-Issue an.

## Was geprüft wird

| Quelle | Felder |
|---|---|
| Paperclip-Agenten | `adapterConfig.model` / `.defaultModel` / `.fallbackModel` **und** `runtimeConfig.modelProfiles.<profil>.model` / `.fallbackModel` |
| Link-Detektor | `ld.config.llm_model` + `.embedding_model` in `link_detektor` **und** `link_detektor_clara` |
| n8n | literale Modell-Zuweisungen in `set`-Knoten aktiver Workflows |
| Obsidian-Tagger | `llm.modell` in beiden Templates |
| Wake-Satellit | `sat_config.CHAT_MODEL` |
| PII-Proxy (Datei) | `PII_PROXY_CLASSIFIER_MODEL` + `..._FALLBACK_MODEL` aus der Plist |
| PII-Proxy (laufender Dienst) | dieselben Felder aus `launchctl print` — **das ist der wirksame Wert** |
| LM-Studio-Laufzeit | `contextLength` + `parallel` je geladenem Modell gegen `soll-laufzeit.json` |

Stand 26.08.: **122 Referenzen aus 7 Quellen**, dazu 5 Laufzeit-Zustände gegen
3 Sollwerte. (Am 23.08. waren es 158 Referenzen — was dazwischen wegfiel, ist
nicht nachgehalten.)

Nur Modelle, die in `soll-laufzeit.json` stehen, werden auf Fenster und Slots
geprüft. `openbiollm` und die Einbettungsmodelle haben bewusst kleine Fenster
und gehören nicht hinein.

## Fünf Entscheidungen, die nicht offensichtlich sind

**Bei falschem Fenster wird die Slotzahl nicht extra gemeldet.** Beide Werte
gehören zusammen — ein kleineres Fenster erlaubt mehr Slots im selben Speicher.
Am 26.08. standen die RTX-Modelle auf `65.536 × 8/12` statt `98.304 × 5/8`: das
ist **ein** Zustand, nicht zwei Fehler. Zwei Meldungen daraus zu machen bläht
jeden Bericht auf und verdeckt, dass es eine einzige Ursache ist.

**Ein zu kleines Fenster ist `hoch`, ein zu großes nur `niedrig`.** Zu klein
heißt Überläufe und gescheiterte Läufe. Zu groß kostet Speicher und sonst
nichts.



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
- Fenster und Slots werden nur gegen `soll-laufzeit.json` gehalten. Wer die
  Farm bewusst umbaut, muss die Datei mitziehen — sonst meldet der Wächter den
  neuen Zustand als Fehler.
- Der Drift-Abgleich Datei ↔ Dienst gilt bislang **nur für den PII-Proxy**.
  Jeder andere launchd-Dienst mit Modellnamen in der Umgebung hat dieselbe
  Falle, wird aber nicht geprüft.
- Der Wächter sieht nur den Zustand **im Moment seines Laufs**. Der Vorfall vom
  26.08. begann um 10:00 und war um 12:11 vorbei — ein einzelner Lauf um 07:30
  hätte ihn komplett verpasst.

## Läuft unter Python 3.9

launchd startet mit dem System-Python (3.9.6). Deshalb `Optional[x]` statt
`x | None`, keine Fremdpakete. Wer hier 3.10-Syntax einbaut, merkt es nicht beim
Entwickeln, sondern erst nachts im Dienst.

## Tests

```sh
python3 -m pytest -q     # 30 Tests
```

Jeder Test in `test_pruefung.py` ist ein Vorfall, der bereits passiert ist.
Zusätzlich gegen den echten Vorzustand geprüft: mit den Templates aus
`e8d522eb3^` meldet der Wächter beide toten IDs, mit dem heutigen Stand keinen
Befund.

Für die beiden Prüfungen vom 26.08. ebenso nachgestellt:

```sh
# Fenster: Soll künstlich hochsetzen -> beide RTX-Modelle als "zu klein" gemeldet
MODELL_WACHT_SOLL=/tmp/soll-vorfall.json ./waechter.py --text   # Exitcode 1

# Drift: gegen den Dienstzustand von 12:00 Uhr desselben Tages
python3 -c "import waechter as w; from pruefung import bewerte_drift; \
  print(bewerte_drift(w.hole_pii_proxy(), \
    [w.Referenz('PII-Proxy (laufender Dienst)','CLASSIFIER_MODEL','google/gemma-4-12b-qat')]))"
```

Beide schlagen an, im Normalzustand meldet der Wächter keinen Befund.
