---
title: Paperclip → HomePod "Studio" Voice-Bridge
status: draft
date: 2026-05-11
scope: WHITESTAG company only
---

## Ziel

Walter erhält Paperclip-Informationen sprachlich über seinen HomePod "Studio" — in zwei Modi:

1. **Push (Aufmerksamkeit):** Sobald in der WHITESTAG-Company eine neue *pending Approval* auftaucht, sagt der HomePod das ungefragt an.
2. **Pull (manuell):** Walter sagt "Hey Siri, Paperclip-Status" und bekommt den aktuellen Stand offener Approvals vorgelesen.

Out of Scope: andere Companies, andere Event-Typen, Multi-HomePod-Routing, Meeting-Awareness, Konfigurations-UI.

## Voraussetzungen

- macOS mit AirPlay-Pairing zum HomePod "Studio" (bereits eingerichtet).
- `brew install switchaudio-osx` — CLI-Tool zum Umschalten des System-Audio-Outputs.
- Paperclip läuft lokal auf `http://127.0.0.1:3100` (launchd-Service `ing.paperclip.dev`).
- Paperclip-Board-Token in `~/.paperclip/auth.json` (bereits vorhanden).
- iPhone mit "Persönliche Anfragen" am HomePod aktiviert (für den Pull-Modus).

## Konstanten

| Schlüssel | Wert |
|---|---|
| WHITESTAG Company-ID | `9cebf3cf-efe8-4597-a400-f06488900a87` |
| Paperclip-API-Base (lokal) | `http://127.0.0.1:3100/api` |
| Paperclip-API-Base (LAN/Tunnel, für Siri-Shortcut) | `https://company.whitestag.ai/api` |
| HomePod-Audio-Device-Name | `Studio` |
| Polling-Intervall | 60 Sekunden |
| Quiet Hours | 22:00–08:00 (lokale Zeit) |
| TTS-Stimme | macOS-System-Default (deutsch) |
| Token-Quelle | `jq -r '.credentials["http://localhost:3100"].token' ~/.paperclip/auth.json` |

### Approval-Type → Sprachbezeichnung

Die API-Feld `type` enthält Maschinen-Kürzel. Für die Ansage werden sie auf natürliche deutsche Begriffe gemappt:

| API-`type` | Sprachbezeichnung |
|---|---|
| `hire_agent` | "Einstellung" |
| `approve_ceo_strategy` | "Strategie-Freigabe" |
| (unbekannt) | wörtlich der `type`-Wert, mit Unterstrichen als Leerzeichen |

Mapping liegt als kleines Shell-Case-Statement in `homepod-watcher.sh`.

## Komponenten (Push-Pipeline, lokal)

### 1. `~/.paperclip/scripts/homepod-speak.sh`

Shared TTS-Helper. Aufruf: `homepod-speak.sh "Text der gesprochen werden soll"`.

Verhalten:

1. Aktuelle Audio-Output-Source merken: `CURRENT=$(SwitchAudioSource -c)`.
2. Auf "Studio" wechseln: `SwitchAudioSource -s "Studio"`.
   - Wenn das fehlschlägt (z.B. HomePod offline) → Exit Code ≠ 0, **kein** Sprechen, **kein** Zurückwechseln.
3. Sprechen: `say "$1"` (System-Default-Stimme).
4. Zurückwechseln: `SwitchAudioSource -s "$CURRENT"`.
   - Wenn `$CURRENT` leer war (z.B. vorheriges Gerät war abgemeldet) → Fallback auf `Mac Studio-Lautsprecher`.
5. Logging nach `~/.paperclip/state/homepod-speak.log` (Zeitstempel, Text, Exit Codes).

### 2. `~/.paperclip/scripts/homepod-watcher.sh`

Polling-Loop. Wird von launchd alle 60 s als One-Shot gestartet.

Verhalten pro Lauf:

1. Token aus `~/.paperclip/auth.json` lesen.
2. `curl -sf -H "Authorization: Bearer $TOKEN" http://127.0.0.1:3100/api/companies/9cebf3cf-efe8-4597-a400-f06488900a87/approvals?status=pending`.
   - HTTP-Fehler → Skript bricht ab ohne State-Update, ohne Ansage.
3. State-Datei `~/.paperclip/state/homepod-watcher.json` lesen (oder mit leerer `announcedApprovalIds`-Liste initialisieren).
4. Diff: welche Approval-IDs aus der API-Response sind **nicht** in `announcedApprovalIds`?
   - Keine neuen → Skript endet.
5. Quiet-Hours-Check (`date +%H` in [22, 23, 0, 1, 2, 3, 4, 5, 6, 7]):
   - Quiet → State **trotzdem** mit allen aktuellen IDs updaten (damit es 08:00 nicht eine Schwall-Ansage gibt), Skript endet.
   - Aktiv → weiter.
6. Ansage-Text bauen (mit Type-Mapping aus dem Konstanten-Abschnitt):
   - 1 neue Approval: `"Paperclip Whitestag: neue Genehmigung — <Sprachbezeichnung>"`
   - >1: `"Paperclip Whitestag: <N> neue Genehmigungen — <Sprachbez1>, <Sprachbez2>, …"` (max. 3 Typen, danach "und weitere")
7. `homepod-speak.sh "$TEXT"` aufrufen.
   - Erfolg → State updaten (neue IDs zur `announcedApprovalIds`-Liste hinzufügen, `lastPolledAt` setzen).
   - Fehler → State **nicht** updaten, nächster Poll versucht's erneut.
8. State-Liste auf max. 200 IDs begrenzen (FIFO), damit sie nicht unbegrenzt wächst.

### 3. `~/.paperclip/state/homepod-watcher.json`

```json
{
  "announcedApprovalIds": ["uuid-1", "uuid-2", ...],
  "lastPolledAt": "2026-05-11T14:30:00Z",
  "lastSpokenAt": "2026-05-11T14:25:00Z"
}
```

### 4. `~/Library/LaunchAgents/ing.paperclip.homepod-watcher.plist`

launchd-Job:

- `Label`: `ing.paperclip.homepod-watcher`
- `ProgramArguments`: `["/bin/zsh", "/Users/walterschoenenbroecher.de/.paperclip/scripts/homepod-watcher.sh"]`
- `StartInterval`: `60` (alle 60 s ausführen)
- `RunAtLoad`: `true`
- `StandardOutPath` / `StandardErrorPath`: `~/Library/Logs/paperclip-homepod/watcher.log`
- Kein `KeepAlive` — `StartInterval` triggert das Skript immer neu, jeder Lauf ist One-Shot und beendet sich selbst.

## Komponenten (Pull-Pipeline, Siri/HomePod)

### iOS-Shortcut "Paperclip-Status"

Manuell auf dem iPhone in der Shortcuts-App anzulegen. Wird in der Spec **nur dokumentiert**, nicht automatisiert installiert (Shortcuts-Format ist binär .shortcut/iCloud-Link).

Aktionen:

1. **Get Contents of URL**:
   - URL: `https://company.whitestag.ai/api/companies/9cebf3cf-efe8-4597-a400-f06488900a87/approvals?status=pending`
   - Method: GET
   - Headers: `Authorization: Bearer pcp_board_…` (Walter trägt den Token aus `~/.paperclip/auth.json` einmalig ein)
2. **Get Dictionary from Input** → Liste der Approvals.
3. **Count Items**.
4. **If** Count = 0:
   - **Speak Text**: "Paperclip Whitestag: keine offenen Genehmigungen."
5. **Otherwise**:
   - **Repeat with Each** über die ersten 3 Einträge → die `type`-Felder mit dem Mapping aus dem Konstanten-Abschnitt in Sprachbezeichnungen umwandeln und mit Komma verkettet sammeln.
   - **Speak Text**: "Paperclip Whitestag: \<Count\> offene Genehmigungen — \<gesammelter Text\>."

> Hinweis: Das Mapping muss im Shortcut als IF-Kette dupliziert werden (Shortcuts hat keinen Import aus Bash). Walter pflegt es manuell — bei nur 2 echten Types überschaubar.

Sprach-Trigger: Der Shortcut-Name `Paperclip-Status` ist gleichzeitig die Siri-Phrase. "Hey Siri, Paperclip-Status" auf dem HomePod führt den Shortcut über das gepairte iPhone aus; die Sprachausgabe kommt auf dem HomePod, der die Anfrage gehört hat.

## Fehlerverhalten / Edge Cases

| Szenario | Verhalten |
|---|---|
| Paperclip-API down (curl-Fehler) | Watcher bricht still ab, kein State-Update, kein TTS. Nächster Poll versucht's. |
| HomePod offline (SwitchAudioSource fehlschlägt) | `homepod-speak.sh` exit ≠ 0 → Watcher updated State **nicht** → Ansage wird beim nächsten Poll erneut versucht. |
| Aktuelles Audio-Gerät offline beim Zurückwechseln | Fallback auf `Mac Studio-Lautsprecher`. |
| Quiet Hours, neue Approvals | State wird stillschweigend aktualisiert, keine Ansage, keine Nachhol-Salve um 08:00. |
| State-Datei korrupt | Initialisiere als leeres `announcedApprovalIds: []`, Re-Sync über die nächste API-Response. |
| Token fehlt / ungültig | curl HTTP 401 → behandelt wie "API down" (still abbrechen). |
| Cloudflare-Tunnel down (Pull-Pipeline) | Siri-Shortcut sagt "Konnte Paperclip nicht erreichen" (eingebaute Shortcut-Fehlerbehandlung). |

## Sicherheitsaspekte

- Board-Token aus `~/.paperclip/auth.json` ist sensitiv. Skripte loggen den Token **nicht**.
- Im iOS-Shortcut wird der Token im Klartext gespeichert (Shortcuts erlaubt keine echte Secret-Verwaltung). Walter übernimmt das Risiko.
- Keine neuen offenen Ports.

## Was NICHT Teil dieser Spec ist

- Andere Paperclip-Companies (Health Insights, Clara Sound).
- Andere Event-Typen (Comments, Issues, Agent-Status, Build-Errors).
- Multi-HomePod oder dynamisches Routing.
- Meeting-Aware Filterung (Kalender-/Zoom-/Teams-Check).
- Konfigurations-UI — alle Werte sind Konstanten in den Skripten.
- Automatisierte iOS-Shortcut-Erstellung (manuelle Doku reicht).

## Erfolgskriterien

1. Walter erstellt eine neue Approval in der WHITESTAG-Company → innerhalb von ≤90 s spricht der HomePod "Studio" eine Ansage.
2. Während Quiet Hours wird die Approval angemerkt (State aktualisiert), aber nicht gesprochen.
3. Walter sagt "Hey Siri, Paperclip-Status" → der HomePod liest die Anzahl und Typen offener Approvals vor.
4. HomePod offline → keine Fehler-Spam-Ansage, beim nächsten Online-Poll wird die Ansage nachgeholt.
5. Kein Eingriff in laufende Audio-Wiedergabe außerhalb der ~3 Sekunden Ansage.
