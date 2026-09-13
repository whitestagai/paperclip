# Agenten-Aufsicht (`agent-wacht`)

Holt stehende Agenten aus `error` zurück — und meldet, wenn die **interne**
Selbstheilung selbst ausgefallen ist.

## Warum es ihn gibt

Am **02.09.2026 um 20:57** wechselte der Watch-Tree, aus dem der Dev-Server
läuft, von `feat/vorfall-abschluss` auf `master` (reflog `80ce1cc55`). Der Code
der internen Selbstheilung lag nur im Feature-Branch; in `master` standen bloß
Spec und Plan. Der letzte Eintrag in `agent_self_heal_ledger` stammt vom
**02.09. um 20:57:11** — auf die Minute derselbe Zeitpunkt.

Elf Tage lang holte niemand mehr Agenten aus `error`. Am 13.09. standen fünf
Agenten zwischen 10 und 46 Stunden still, darunter der CEO. Gemerkt hat es
niemand, denn **ein fehlender Wächter meldet nichts** — die plist setzte sogar
weiter `INCIDENT_CLOSURE_ENABLED=true` für Code, der nicht mehr existierte.

Dieser Wächter läuft **außerhalb der Anwendung**. Er überlebt Branch-Wechsel,
Deployments und Abstürze, und genau deshalb hätte er den Ausfall am 03.09.
früh gemeldet statt nach elf Tagen.

## Was er prüft

1. **Stehen Agenten in `error`?** Wer länger als 20 Minuten steht und *nicht*
   von der internen Selbstheilung betreut wird, wird per
   `POST /api/agents/:id/resume` zurückgeholt.
2. **Schweigt der Ledger, obwohl es etwas zu tun gäbe?** Stehen Agenten in
   `error` und der jüngste Ledger-Eintrag ist älter als 60 Minuten, arbeitet
   die interne Selbstheilung nicht mehr. Das ist der eigentliche Zweck:
   **die Aufsicht über die Aufsicht.**

## Arbeitsteilung mit der internen Selbstheilung

Die interne (`server/src/services/recovery/agent-self-heal.ts`) ist zuständig
und kennt Backoff-Stufen von 5/15/60 Minuten. Dieser Wächter greift ihr **nicht
vor die Füße** — sonst entsteht genau die Weckschleife, die vermieden werden
soll.

**Die Feinheit, an der ein naiver Bau scheitert:** Eine offene Ledger-Zeile
allein heißt *nicht* „kümmert sich". Die interne gibt nach drei Versuchen je
Fehlercode auf und lässt die Zeile **offen stehen**. Beim ersten Trockenlauf
am 13.09. waren 12 Zeilen offen, davon genau **eine frisch**. Als Betreuung
zählt deshalb nur eine Zeile, deren `updated_at` jünger als 75 Minuten ist
(längste Backoff-Stufe plus Luft). Alles andere ist ein aufgegebener Fall und
wird geholt.

## Meldeweg

Mail an Walter über den n8n-Mailhub — **nicht** als Paperclip-Issue. Ein Issue
nützt nichts, wenn gerade die Agenten stillstehen, die es bearbeiten müssten.
Genau daran scheiterte die eingebaute Eskalation: `escalateToHuman` schreibt
nur eine Log-Zeile, und niemand erfuhr davon.

Gemeldet wird **nur bei Zustandswechsel**. Der Zustand steht in
`~/.paperclip/logs/agent-wacht-last.json` und wird bei **jedem** Lauf
fortgeschrieben, sonst bleibt ein wiederkehrender Fehler beim zweiten Mal
stumm. Aktiv betreute Agenten zählen nicht als Befund — sonst meldet der
Wächter jeden Wackler und wird zu Rauschen, das niemand mehr liest.

## Aufbau

| Datei | Zweck |
|---|---|
| `pruefung.py` | reine Entscheidungslogik, ohne DB und Netz |
| `melder.py` | Ablauf (`lauf`) plus dünner IO-Mantel |
| `run-melder.js` | Türöffner für launchd, enthält keine Logik |
| `ai.whitestag.agent-wacht.plist` | launchd-Job, alle 15 Minuten |

Der Takt (15 Min) ist bewusst kürzer als die Schwelle (20 Min), damit ein Agent
nicht unnötig lange über der Schwelle liegt, bevor jemand nachsieht.

## Betrieb

```bash
# Tests (System-Python 3.9 — keine `x | None`-Annotationen!)
cd ~/.paperclip/scripts/agent-wacht && python3 -m pytest -q   # 24 Tests

# Lage ansehen, ohne etwas anzufassen
python3 -c "
from datetime import datetime
import melder; from pruefung import signatur, zu_holen
l = melder.lies_lage(); j = datetime.now()
print(signatur(l, j), [a.name for a in zu_holen(l, j)])"

# Log
tail -20 ~/.paperclip/logs/agent-wacht.launchd.log
```

## Zwei launchd-Fußangeln (beide im Haus schon erlebt)

- **`PATH` braucht `/opt/homebrew/bin`** — der Melder ruft `psql` ohne
  absoluten Pfad auf.
- **Start über `node`, nicht `python3`** — aus Python verweigert TCC den
  Zugriff auf die SynologyDrive-Freigabe.
- Eine geänderte plist wird **nicht** nachgeladen; `kickstart -k` startet nur
  den Prozess. Nur `bootout` + `bootstrap` übernimmt sie.
