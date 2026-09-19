# model-warden

Hält den Bestand der geladenen LM-Studio-Modelle auf dem Soll aus
[`resident-set.json`](resident-set.json). Zwei Richtungen, zwei Einstiegspunkte:

| Skript | Richtung | Status |
|---|---|---|
| `warden.py` | **lädt**, was im Soll steht und fehlt | vorhanden, läuft **nicht** |
| `evict_main.py` | **entlädt** auf `studio`, was nicht im Soll steht | läuft alle 10 min als `ai.whitestag.model-evict` |

## Warum der Entlader existiert

In der Nacht zum 19.09.2026 lagen auf der Studio `google/gemma-4-31b`
(33,8 GB) und `qwen/qwen3.6-35b-a3b` (20,4 GB) dauerhaft im Speicher — beide
ohne einen einzigen Nutzer, beide von MLX per „context auto-fit" auf 262.144
Kontext aufgezogen (LM-Studio-Bug #2250, `-c` ist bei MLX wirkungslos). Von
128 GB waren **176 MB** frei. Ab 04:00 scheiterten 48 Agenten-Runs an
`Model loading was stopped due to insufficient system resources`.

Wer die beiden geladen hat, ließ sich nicht klären — per JIT waren sie es
nicht (JIT-Modelle tragen ein `ttlMs`, diese hatten keins). Der Entlader
räumt deshalb unabhängig von der Ursache auf.

## Wann entladen wird

Nur wenn **alles** davon zutrifft:

- `deviceIdentifier` ist `null` → das Modell liegt lokal auf der Studio.
  Modelle auf der WHITESTAG-AI bleiben **immer** unangetastet; sie tragen die
  Agentenflotte.
- Es steht nicht im `resident-set.json` (Gerät `studio`, geprüft gegen
  `ps_key` **und** `load_key`).
- Es ist ein `llm` — Einbettungsmodelle bleiben immer.
- `status` ist nicht arbeitend und `queued` ist 0.
- Es trägt **kein** `ttlMs`. Wer ein TTL setzt, hat das Modell bewusst auf
  Zeit geholt; LM Studio räumt es selbst weg.
- Die letzte Nutzung liegt mindestens **20 Minuten** zurück. `idle` heißt nur
  „gerade keine Anfrage" — zwischen zwei Aufrufen eines laufenden Jobs steht
  jedes Modell auf idle.

## Ein Modell nur zeitweise brauchen

Nicht ins `resident-set.json` eintragen, sondern mit TTL holen — dann räumt
LM Studio auf und der Wärter fasst es nicht an:

```sh
lms load google/gemma-4-31b --ttl 1800 -y
```

So macht es `~/.paperclip/scripts/vault-tagger-nightly.sh` um 00:00.
**Vorher prüfen, ob es schon geladen ist:** `lms load` auf ein bereits
geladenes Modell lädt nicht neu, sondern stellt eine **zweite Instanz**
daneben (`<id>:2`) — nochmal volle Gewichte im RAM.

## Betrieb

```sh
python3 evict_main.py --dry-run    # zeigt nur, was es täte
python3 evict_main.py --verbose    # loggt jede Entscheidung, auch ohne Aktion
python3 -m pytest -q               # 48 Tests
```

- Log: `~/.paperclip/logs/model-evict.log` (ruhige Läufe = eine Zeile),
  Status: `~/.paperclip/logs/model-evict-last.json`
- Live-Kopie: `~/.paperclip/scripts/model-warden/`. launchd startet von dort,
  damit der Job nicht vom SynologyDrive-Pfad abhängt.
  **Drift-Test:** `diff -rq tools/model-warden ~/.paperclip/scripts/model-warden`
- launchd nutzt bewusst `/opt/homebrew/bin/python3`: `/usr/bin/python3` bricht
  nach jedem Xcode-Update mit Exit 69 ab, bevor Code läuft.
- Nach Änderungen an der plist: `bootout` + `bootstrap`, **nicht** `kickstart`
  — das startet nur den Prozess, nicht den Job.

## Tests und die Betriebskonfiguration

`test_audit_agents.py` und `test_warden.py` lasen bis zum 19.09.2026 die echte
`resident-set.json` und prüften auf konkrete Modellnamen. Beim Entfernen der
toten ID `gemma-4-31b-it-mlx` fielen dadurch fünf Tests um, obwohl die Logik
unverändert war. Sie lesen jetzt `test-resident-set.json`. Nur
`test_config.py` liest weiter die echte Datei — dort ist das gewollt, er
prüft den Betriebsstand gegen das Schema.
