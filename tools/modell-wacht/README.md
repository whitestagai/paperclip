# Modell-Aufsicht

Hält jede fest verdrahtete LM-Studio-Modell-ID im Haus gegen den tatsächlichen
Bestand — und die geladenen Modelle gegen ihren Soll-Zustand. Der Wächter
**repariert nichts** — er stellt fest und meldet.

Vier Prüfungen, vier Fehlerbilder:

| Prüfung | Frage |
|---|---|
| `bewerte` | Zeigt eine Stelle auf einen Namen, den es nicht gibt? |
| `bewerte_laufzeit` | Name richtig, Modell aber falsch bedient (Fenster, Slots)? |
| `bewerte_drift` | Steht in der Datei etwas anderes als im laufenden Dienst? |
| `bewerte_geraete` | Ist jedes Gerät verbunden und jedes Soll-Modell auf seinem Gerät? |

Harte Befunde gehen **per Mail an ws@** — ein Issue allein ist eine Akte, kein
Alarm (siehe 10.10.2026 unten).

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

### Der unbemerkte Geräteausfall vom 10.10.2026

Die RTX Pro 6000 fiel gegen 10:30 aus und blieb zwei Tage weg. Der Melder schlug
um 10:42 an — mit einem Issue **ohne Assignee im backlog**, das niemand sah. Und
selbst gelesen hätte es den Ausfall nicht gezeigt:

| Was im Issue stand | Was tatsächlich los war |
|---|---|
| HOCH: PII-Proxy zeigt auf «google/gemma-4-12b-qat» — ID unbekannt | das Modell lag auf der RTX, und die war weg |
| 30× NIEDRIG: «qwen3.6-35b-a3b» nicht geladen — „LM Studio lädt nach" | nachgeladen wurde nichts; LM Studio bediente die ID **still vom Node WHITESTAG-AI** (gleicher modelKey), mit 2 statt 4 Slots und Q6_K statt Q8_0 |

Die Aufsicht kannte schlicht **keine Geräte**. Seit 12.10. trägt jeder Eintrag in
`soll-laufzeit.json` ein Feld `geraet` (`lokal` = der Mac, auf dem LM Studio
läuft), und `bewerte_geraete` meldet hart:

- **Gerät getrennt** — ein Befund je Gerät mit allen betroffenen Modellen, nicht
  einer je Modell, sonst geht die Ursache in Folgezeilen unter.
- **Modell fehlt** auf einem verbundenen Gerät.
- **Modell auf falschem Gerät** — `lms load` kennt kein Geräte-Flag und lädt aufs
  preferred device; ein Neuladen vom Studio aus landet still auf dem Studio.

Quellen: `lms ps --json` (`deviceIdentifier`, null = lokal) und
`lms link status --json` (Namen und Verbindungsstatus).

## Aufbau

| Datei | Zweck |
|---|---|
| `pruefung.py` | reine Bewertungslogik, kein I/O — Regeln samt Begründung |
| `waechter.py` | sammelt die Referenzen, gibt JSON auf stdout |
| `melder.py` | halbstündlicher Takt: prüft, protokolliert, bei Wechsel Issue + Mail |
| `run-melder.js` | node-Türöffner für launchd (TCC, siehe unten) |
| `soll-laufzeit.json` | Soll-Gerät, -Fenster und -Slots je Modell, **mit Begründung** |
| `test_pruefung.py` | die Ernstfälle: tote ID, unlesbare Quelle, Fehlalarm-Schutz |
| `test_waechter.py` | die Sammelfallen: Sticky Notes, Ausdrücke, cheap-Profil, Geräte-Zuordnung |
| `test_melder.py` | Inhalt der Alarm- und Entwarnungsmail |

```sh
./waechter.py           # JSON
./waechter.py --text    # Klartext
./melder.py             # prüfen + protokollieren + ggf. Issue und Mail
```

Exitcode `1`, sobald ein Befund der Schwere `hoch` vorliegt, sonst `0`.

## Takt

| Takt | Wie | Wozu |
|---|---|---|
| alle 30 Minuten | launchd `ai.whitestag.modell-wacht` → `melder.py` | fängt kurze Vorfälle, meldet nur bei Wechsel |
| ~~täglich 07:30~~ | Paperclip-Routine `584f1e23…`, **pausiert seit 13.10.2026** | — |

Die Routine (Agent LLM-Konfigurationsanalyst) legte ein Issue an, sobald
`ok: false` war — also schon bei **niedrigen** Befunden, praktisch täglich. Bis
zum 12.10. hatten sich so 112 offene Aufsichts-Issues angesammelt, die niemand
las. Der Melder deckt dasselbe ab, ohne LLM, alle 30 Minuten, mit Mail.
Reaktivieren: `PATCH /api/routines/584f1e23-da06-4da3-931a-4ef6c2e134c9`
mit `{"status": "active"}`.

Der halbstündliche Takt kostet nichts — `waechter.py` ist reines Python ohne
LLM. Er existiert, weil der Vorfall vom 26.08. von 10:00 bis 12:11 lief und ein
einzelner 07:30-Lauf ihn vollständig verpasst hätte.

**Gemeldet wird nur bei Zustandswechsel.** Ein Fehler, der zwei Stunden anhält,
erzeugt genau ein Issue und eine Mail — nicht vier. Die Signatur dafür lässt den Meldetext
bewusst weg, damit ein wackelnder Zahlenwert nicht als neuer Befund gilt. Der
Zustand in `~/.paperclip/logs/modell-wacht-last.json` wird bei **jedem** Lauf
fortgeschrieben, auch ohne Meldung — sonst bliebe ein behobener und wieder
auftretender Fehler beim zweiten Mal stumm.

### Mail

Bei jedem Wechsel des harten Befundstands geht eine Mail an `ws@whitestag.ai`
(Absender `cto@whitestag.ai`, über den Mailhub-Webhook `mailhub/send`, Secret aus
`~/.paperclip/instances/default/secrets/mailhub.env`). Darin stehen **nur die
harten Befunde im Wortlaut**; niedrige werden gezählt und stehen vollständig im
Issue. Verschwinden alle harten Befunde, kommt **einmal** „wieder grün".
Empfänger umstellbar per `MODELL_WACHT_MAIL_AN`. Issue und Mail sind getrennt
abgesichert: scheitert das eine, geht das andere trotzdem raus.

Zustellung prüfen: in n8n die Ausführungen von `SMTP Relay V21`
(`3LgkMnNjbKfcdK5H`) — `accepted: ["ws@whitestag.ai"]` und `250 OK` heißt,
der Mailserver hat sie angenommen.

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
| Wake-Satellit (live `~/.paperclip/scripts/wake-satellite/sat_config.py`) | `sat_config.CHAT_MODEL`, `CHAT_FALLBACK_MODEL` |
| PII-Proxy (Datei) | `PII_PROXY_CLASSIFIER_MODEL` + `..._FALLBACK_MODEL` aus der Plist |
| PII-Proxy (laufender Dienst) | dieselben Felder aus `launchctl print` — **das ist der wirksame Wert** |
| LM-Studio-Laufzeit | `contextLength` + `parallel` je geladenem Modell gegen `soll-laufzeit.json` |
| LM Link | Gerät je geladenem Modell (`lms ps --json`) und verbundene Geräte (`lms link status --json`) gegen `geraet` im Soll |

Stand 13.10.: **167 Referenzen aus 7 Quellen**, 9 Laufzeit-Zustände gegen
6 Sollwerte auf 3 Geräten (Studio, RTX Pro 6000, WHITESTAG-AI). Am 26.08. waren
es 122 Referenzen gegen 3 Sollwerte. 

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
- Geräte werden nur für Modelle mit Feld `geraet` geprüft. Ein Gerät, auf dem
  kein Soll-Modell liegt, kann ausfallen, ohne dass es auffällt.
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
/usr/bin/python3 -m pytest -q     # 55 Tests
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

Der RTX-Ausfall vom 10.10. als Probe, mit Testmail an ws@ (kein Issue):

```sh
/usr/bin/python3 -c "
import melder; from waechter import hole_soll; from pruefung import bewerte_geraete
b = bewerte_geraete({'gemma-4-31b-win':'WHITESTAG-AI','qwen3.6-35b-win':'WHITESTAG-AI'}, {'WHITESTAG-AI'}, hole_soll())
s, t, h = melder.alarm_mail(b, 'TEST', None); melder._sende('[TEST] ' + s, t, h)"
```
