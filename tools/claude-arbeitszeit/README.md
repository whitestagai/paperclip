# Claude-Code-Arbeitszeit

Tägliche Mail um 07:00 an ws@whitestag.ai: wie viele Stunden Walter gestern, in
der laufenden Woche, im laufenden Monat und im laufenden Jahr an welchen
Claude-Code-Projekten gearbeitet hat — als Kacheln, 100-%-Balken je Zeitraum,
gestapelte Tagessäulen der letzten 30 Tage und Tabelle mit Stunden, Prozent und
Vault-Chats.

## Datenquellen

| Wert | Quelle |
|---|---|
| Stunden | Sitzungsprotokolle `~/.claude/projects/*/*.jsonl` (Zeitstempel je Nachricht) |
| Chats | Vault `Claude Code/<Projekt>/yyyy-mm-tt Chatverlauf *.md` |
| Projektname | erster Arbeitsordner der Sitzung, angeglichen an die Vault-Ordner (`ALIAS`) |

Die Vault-Chatverläufe tragen nur ein Datum, keine Uhrzeit — Stunden lassen sich
daraus nicht ableiten.

**Messregel:** Nachrichten mit höchstens 15 Minuten Abstand gelten als
durchgehende Arbeit, längere Lücken als Pause. Laufen Sitzungen mehrerer
Projekte in derselben Minute, teilen sie sich die Minute — die Projektsummen
ergeben so die tatsächlich gearbeitete Zeit. Läufe der Paperclip-Agenten
(`entrypoint: sdk-cli`, Ordner unter `~/.paperclip/instances/`) zählen nicht.

## Register

Claude Code löscht Protokolle nach etwa 30 Tagen. Jeder Lauf schreibt die
gemessenen Minuten nach `~/.claude/arbeitszeit/claude-arbeitszeit.sqlite`; was
dort steht, bleibt, auch wenn das Protokoll verschwindet. Der Ort ist bewusst
gewählt: `~/.claude` sichert `system-secrets-backup` nach Hetzner,
`~/.paperclip/state` nicht. Eine kürzere Fassung
derselben Sitzung (z.B. aus einer alten Sicherung) überschreibt nie eine längere.

Am 26.10.2026 aus den Restic-Snapshots `64f84108` (04.09.), `25e9809a` (20.09.)
und `6d1e439e` (04.10.) nachgefüllt — lückenlose Messung ab 03.08.2026. Davor
gibt es keine Protokolle mehr; die Mail weist darauf hin.

Nachfüllen aus einer Sicherung:

```
restic … restore <id> --target DIR --include '/Users/walterschoenenbroecher.de/.claude/projects/*/*.jsonl'
./run.sh --nur-einlesen --quelle DIR/Users/walterschoenenbroecher.de/.claude/projects
```

## Bedienung

```
./run.sh                          # Bericht für gestern, senden
./run.sh --dry-run --out x.html   # nur ansehen
./run.sh --datum 2026-10-25       # anderer Berichtstag
/usr/bin/python3 -m pytest -q     # Tests
```

## Deploy

Live-Kopie: `~/.paperclip/scripts/claude-arbeitszeit/` (Drift-Test:
`diff -rq tools/claude-arbeitszeit ~/.paperclip/scripts/claude-arbeitszeit`).
launchd: `~/Library/LaunchAgents/de.whitestag.claude-arbeitszeit.plist`, Logs
`/tmp/claude-arbeitszeit{,-error}.log`. Nach plist-Änderung `bootout` +
`bootstrap`, nicht `kickstart -k`.
