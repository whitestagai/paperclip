# Mount-Wächter für die NAS-Freigaben

Hält die SMB-Freigabe `WHITESTAG-ARCHIV` eingehängt — die Freigabe, auf der
**alle** NAS-Sicherungen liegen. launchd-Job `ai.whitestag.mount-archiv`,
alle 300 Sekunden.

| | |
|---|---|
| Freigabe | `smb://ws-cloud@WHITESTAG-NAS._smb._tcp.local/WHITESTAG-ARCHIV` |
| Mountpoint | `/Volumes/WHITESTAG-ARCHIV` |
| Sondenpfad | `Backup Mac Studio M4 Max` |
| Log | `~/.paperclip/logs/nas-mount.log` (nur Zustandswechsel) |
| Status | `~/.paperclip/logs/nas-mount-WHITESTAG-ARCHIV-last.json` |

Löst `~/.claude/scripts/mount-whitestag-archiv.sh` ab (unversioniert, ungetestet).

## Der Vorfall vom 24.08.2026

Um **04:28** riss die SMB-Verbindung zur NAS ab. `/Volumes/homes` wurde vom
Keepalive binnen vier Sekunden neu eingehängt, `/Volumes/WHITESTAG-ARCHIV`
**28 Stunden lang nicht**. In dieser Zeit fiel aus:

- die DB-Sicherung vom 25.08. (02:30, `ABBRUCH: NAS nicht erreichbar`)
- der Vault-Spiegel vom 25.08. (04:00, derselbe Abbruch)
- der Claude-Code-Spiegel, der seither steht

Aufgefallen ist es nur, weil `backup-waechter` am 24.08. um 09:00 Alarm
geschlagen hat. Der Wächter hat funktioniert — die Selbstheilung nicht.

## Zwei Fehler, beide am 25.08.2026 unter launchd nachgemessen

### 1. Lebendprüfung mit `ls`

Die Vorgängerin prüfte `mount | grep … && ls "$MOUNTPOINT"`. Unter launchd ist
das **Auflisten** eines Netzlaufwerks TCC-gesperrt — für `bash` wie für `zsh`,
auch bei völlig gesundem Mount:

```
=== ls ===   ls: /Volumes/WHITESTAG-ARCHIV: Operation not permitted
```

`ls` schlug dort also **immer** fehl. Das Skript schloss daraus „nicht
eingehängt", hängte zwangsweise aus und mountete neu — **287-mal am Tag**, seit
Juni. Der Nachweis steht im alten Log: 287 Zeilen `OK – gemountet` pro Tag,
bei 288 Läufen. Die stille Nebenwirkung war der eigentliche Schaden: der
Vault-Spiegel vom 24.08. scheiterte mit `rsync error … (code 11)` an fast
jedem Ordner — die Signatur eines Volumes, das mitten im Lauf wegbricht.

**`test -d` (stat) ist nicht gesperrt** und beweist denselben Punkt. Das ist
der Unterschied zwischen dieser Fassung und der alten — und derselbe Grund,
aus dem `nas-mount-keepalive.sh` für `/Volumes/homes` seit jeher
funktioniert: es prüft mit `[ -d … ]`, nicht mit `ls`.

### 2. Unbegrenztes Warten

Auf einer toten SMB-Verbindung blockieren `diskutil unmount` und
`osascript mount volume` beliebig lange. launchd startet bei `StartInterval`
**keine zweite Instanz**, solange die erste noch läuft — ein einziger Hänger
legt den Wächter still. Genau das waren die 28 Stunden: zwischen
`04:22:51` und `08:27:02` am Folgetag steht keine einzige Logzeile, während
alle anderen Dienste normal weiterliefen.

Jeder Aufruf nach außen läuft deshalb unter einer Frist (30 s) und wird bei
Ablauf **zurückgelassen** statt abgewartet: ein Prozess, der im Kern auf totem
SMB hängt, überlebt oft auch SIGKILL. Ein verwaister Prozess ist hinnehmbar,
ein toter Wächter nicht.

## Was das Skript bewusst *nicht* tut

- **Kein Mailversand.** Bei 288 Läufen am Tag wäre jede Störung eine Mailflut.
  Alarmiert wird über `backup-waechter` (täglich 09:00) und die
  Sicherungsskripte selbst.
- **Kein Aushängen bei fehlendem Sondenpfad.** Ist die Freigabe erreichbar,
  aber der Sondenordner fehlt (umbenannt, gelöscht), ist das ein
  Konfigurationsfehler — kein toter Mount. Wer ihn wie einen behandelt, stellt
  die Dauerschleife von oben wieder her. Das Skript meldet stattdessen
  `Sondenpfad fehlt` und fasst nichts an.
- **Nur Zustandswechsel ins Log.** Das alte Log war mit 900 KB `OK – gemountet`
  so zugestellt, dass der echte Ausfall darin nicht auffiel.

## Benutzung

```bash
bash nas-mount.sh --freigabe WHITESTAG-ARCHIV --probe "Backup Mac Studio M4 Max"
```

Das Skript ist **nicht** auf diese eine Freigabe festgelegt. `--mountpoint`,
`--frist` und die drei `--*-bin`-Schalter existieren für die Tests; letztere
ersetzen `mount`, `diskutil` und `osascript` durch Attrappen — nur so lässt
sich beweisen, dass ein gesunder Mount **nicht angefasst** wird.

## Tests

```bash
/usr/bin/python3 -m pytest -q
```

## Deploy

```bash
./deploy.sh
launchctl bootout gui/$UID/ai.whitestag.mount-archiv
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/ai.whitestag.mount-archiv.plist
```

## Offen

`~/bin/nas-mount-keepalive.sh` hält `/Volumes/homes` und hat dieselbe
Hänger-Anfälligkeit (Punkt 2) — die Lebendprüfung dort ist korrekt. Es kann
ohne Änderung an diesem Skript auf `nas-mount.sh --freigabe homes --probe …`
umgestellt werden; das ist bisher nicht geschehen, weil der Job funktioniert.
