# Paperclip → HomePod "Studio" Voice-Bridge — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Walter hört Paperclip-Aufmerksamkeitsereignisse (neue pending Approvals der WHITESTAG-Company) automatisch über den HomePod "Studio" und kann via "Hey Siri, Paperclip-Status" jederzeit den aktuellen Stand abrufen.

**Architecture:** Lokaler launchd-Watcher pollt die Paperclip-API alle 60 s, vergleicht gegen ein State-File und ruft bei neuen Approvals einen Shared-TTS-Helper auf, der das System-Audio kurzzeitig auf den HomePod "Studio" umschaltet (`SwitchAudioSource`), `say` ausführt und zurückwechselt. Der Pull-Pfad ist ein iOS-Shortcut, der die gleiche API direkt aufruft und das Ergebnis vorliest.

**Tech Stack:** zsh-Skripte, launchd, `switchaudio-osx` (Homebrew), `jq`, macOS `say`, iOS Shortcuts.

**Spec:** [`docs/superpowers/specs/2026-05-11-paperclip-homepod-bridge-design.md`](../specs/2026-05-11-paperclip-homepod-bridge-design.md)

---

## File Structure

| Datei | Verantwortlichkeit |
|---|---|
| `~/.paperclip/scripts/homepod-speak.sh` | Reine TTS-Routing-Funktion: aktuelles Audio-Device merken → "Studio" wählen → `say` → zurück |
| `~/.paperclip/scripts/homepod-watcher.sh` | Polling-Loop, State-Diff, Type-Mapping, Quiet-Hours-Check, ruft `homepod-speak.sh` |
| `~/.paperclip/state/homepod-watcher.json` | Persistenter State (announced approval IDs, Zeitstempel) — wird vom Skript erzeugt |
| `~/Library/LaunchAgents/ing.paperclip.homepod-watcher.plist` | launchd-Definition: alle 60 s `homepod-watcher.sh` ausführen |
| `~/Library/Logs/paperclip-homepod/watcher.log` | stdout/stderr des Watchers — wird von launchd erzeugt |

iOS-Shortcut "Paperclip-Status" wird manuell von Walter angelegt (Shortcuts hat kein automatisierbares Install-Format, das ohne iCloud auskommt). Der Plan dokumentiert die Schritt-für-Schritt-Anleitung.

---

## Task 1: Dependency installieren und HomePod-Verfügbarkeit prüfen

**Files:**
- Keine — nur Homebrew-Install und Verifikation

- [ ] **Step 1: SwitchAudioSource installieren**

```bash
brew install switchaudio-osx
```

Expected: Homebrew installiert das Paket fehlerfrei.

- [ ] **Step 2: Verfügbare Output-Devices listen**

```bash
SwitchAudioSource -a -t output
```

Expected: Die Ausgabe enthält eine Zeile mit `Studio` (ggf. mit Suffix wie `(AirPlay)`). Notiere den **exakten Namen**, falls er von "Studio" abweicht — dann später in den Skripten anpassen.

- [ ] **Step 3: Manueller Routing-Smoketest**

```bash
ORIG=$(SwitchAudioSource -c) && \
  SwitchAudioSource -s "Studio" && \
  say "Test eins zwei drei" && \
  SwitchAudioSource -s "$ORIG"
```

Expected: HomePod "Studio" sagt hörbar "Test eins zwei drei", danach ist der ursprüngliche Output wieder aktiv. Wenn der HomePod schweigt: Name in Step 2 prüfen.

- [ ] **Step 4: Spec-Drift festhalten, falls Name abweicht**

Wenn der tatsächliche Device-Name nicht "Studio" ist, in der Spec [`docs/superpowers/specs/2026-05-11-paperclip-homepod-bridge-design.md`](../specs/2026-05-11-paperclip-homepod-bridge-design.md) im Konstanten-Abschnitt ersetzen und committen:

```bash
git add docs/superpowers/specs/2026-05-11-paperclip-homepod-bridge-design.md
git commit -m "docs(superpowers): correct HomePod device name in homepod-bridge spec"
```

(Wenn keine Abweichung: Step überspringen.)

---

## Task 2: `homepod-speak.sh` erstellen

**Files:**
- Create: `~/.paperclip/scripts/homepod-speak.sh`

- [ ] **Step 1: Skript schreiben**

Inhalt der Datei `~/.paperclip/scripts/homepod-speak.sh`:

```bash
#!/bin/zsh
# homepod-speak.sh — TTS-Routing-Helper.
# Usage: homepod-speak.sh "Text der gesprochen werden soll"
# Schaltet System-Audio kurzzeitig auf HomePod "Studio", spricht den Text,
# stellt das vorherige Audio-Device wieder her.

set -u

TARGET_DEVICE="Studio"
FALLBACK_DEVICE="Mac Studio-Lautsprecher"
LOG_DIR="$HOME/.paperclip/state"
LOG_FILE="$LOG_DIR/homepod-speak.log"

mkdir -p "$LOG_DIR"

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 \"text to speak\"" >&2
  exit 2
fi

TEXT="$1"
TS=$(date '+%Y-%m-%dT%H:%M:%S%z')

ORIG=$(SwitchAudioSource -c 2>/dev/null)

if ! SwitchAudioSource -s "$TARGET_DEVICE" >/dev/null 2>&1; then
  echo "$TS [error] could not switch to $TARGET_DEVICE; aborting" >> "$LOG_FILE"
  exit 1
fi

say "$TEXT"
SAY_RC=$?

RESTORE="${ORIG:-$FALLBACK_DEVICE}"
if ! SwitchAudioSource -s "$RESTORE" >/dev/null 2>&1; then
  SwitchAudioSource -s "$FALLBACK_DEVICE" >/dev/null 2>&1
  echo "$TS [warn] could not restore $RESTORE, fell back to $FALLBACK_DEVICE" >> "$LOG_FILE"
fi

echo "$TS [ok] spoke=$(printf '%q' "$TEXT") say_rc=$SAY_RC restored=$RESTORE" >> "$LOG_FILE"
exit $SAY_RC
```

- [ ] **Step 2: Ausführbar machen**

```bash
chmod +x ~/.paperclip/scripts/homepod-speak.sh
```

- [ ] **Step 3: Smoke-Test**

```bash
~/.paperclip/scripts/homepod-speak.sh "Sprechtest aus dem Skript"
```

Expected: HomePod "Studio" spricht "Sprechtest aus dem Skript". Vorheriges Audio-Device ist wieder aktiv. `~/.paperclip/state/homepod-speak.log` enthält eine `[ok]`-Zeile.

- [ ] **Step 4: Log prüfen**

```bash
tail -1 ~/.paperclip/state/homepod-speak.log
```

Expected: Eine Zeile mit `[ok] spoke=...Sprechtest... say_rc=0 restored=...`.

- [ ] **Step 5: Negative-Test (optional, nur wenn HomePod ausschaltbar)**

HomePod "Studio" ausschalten / vom Strom nehmen, dann erneut:

```bash
~/.paperclip/scripts/homepod-speak.sh "darf nicht zu hören sein"
echo "exit=$?"
tail -1 ~/.paperclip/state/homepod-speak.log
```

Expected: Exit ≠ 0, Log enthält `[error] could not switch to Studio`. Kein lokaler Sound. HomePod danach wieder einschalten.

- [ ] **Step 6: Commit (im Paperclip-Repo nicht relevant — Skript liegt außerhalb)**

Das Skript liegt unter `~/.paperclip/scripts/` und gehört nicht ins Paperclip-Repo. Kein Commit. (Falls Walter ein eigenes Dotfiles-Repo dafür pflegt, dort committen.)

---

## Task 3: `homepod-watcher.sh` erstellen

**Files:**
- Create: `~/.paperclip/scripts/homepod-watcher.sh`

- [ ] **Step 1: Skript schreiben**

Inhalt der Datei `~/.paperclip/scripts/homepod-watcher.sh`:

```bash
#!/bin/zsh
# homepod-watcher.sh — alle 60 s via launchd ausgeführt.
# Pollt pending Approvals der WHITESTAG-Company, sagt neue Einträge
# über den HomePod "Studio" an, persistiert State, respektiert Quiet Hours.

set -u

WHITESTAG_COMPANY_ID="9cebf3cf-efe8-4597-a400-f06488900a87"
API_BASE="http://127.0.0.1:3100/api"
AUTH_FILE="$HOME/.paperclip/auth.json"
AUTH_KEY="http://localhost:3100"
STATE_DIR="$HOME/.paperclip/state"
STATE_FILE="$STATE_DIR/homepod-watcher.json"
SPEAK_SCRIPT="$HOME/.paperclip/scripts/homepod-speak.sh"
QUIET_START=22  # 22:00 inclusive
QUIET_END=8     # 08:00 exclusive
MAX_STATE_IDS=200

mkdir -p "$STATE_DIR"

# --- read token ---
TOKEN=$(jq -r --arg k "$AUTH_KEY" '.credentials[$k].token // empty' "$AUTH_FILE" 2>/dev/null)
if [[ -z "$TOKEN" ]]; then
  echo "[error] no token in $AUTH_FILE" >&2
  exit 1
fi

# --- fetch pending approvals ---
RESPONSE=$(curl -sf -H "Authorization: Bearer $TOKEN" \
  "$API_BASE/companies/$WHITESTAG_COMPANY_ID/approvals?status=pending" 2>/dev/null) || {
  # API down or auth fail — silent exit, no state change
  exit 0
}

# Normalize: ensure array
if ! echo "$RESPONSE" | jq -e 'type == "array"' >/dev/null 2>&1; then
  exit 0
fi

CURRENT_IDS=$(echo "$RESPONSE" | jq -r '.[].id')

# --- read state ---
if [[ -f "$STATE_FILE" ]] && jq -e 'type == "object"' "$STATE_FILE" >/dev/null 2>&1; then
  ANNOUNCED=$(jq -r '.announcedApprovalIds[]?' "$STATE_FILE")
else
  ANNOUNCED=""
fi

# --- diff: new IDs ---
NEW_IDS=$(comm -23 <(echo "$CURRENT_IDS" | sort -u) <(echo "$ANNOUNCED" | sort -u))

if [[ -z "$NEW_IDS" ]]; then
  exit 0
fi

# --- type mapping ---
type_to_label() {
  case "$1" in
    hire_agent) echo "Einstellung" ;;
    approve_ceo_strategy) echo "Strategie-Freigabe" ;;
    *) echo "${1//_/ }" ;;
  esac
}

# --- build labels for new approvals (max 3, then "und weitere") ---
NEW_LABELS=()
NEW_COUNT=0
while IFS= read -r id; do
  [[ -z "$id" ]] && continue
  TYPE=$(echo "$RESPONSE" | jq -r --arg i "$id" '.[] | select(.id==$i) | .type')
  NEW_LABELS+=("$(type_to_label "$TYPE")")
  NEW_COUNT=$((NEW_COUNT + 1))
done <<< "$NEW_IDS"

if [[ $NEW_COUNT -le 3 ]]; then
  LABEL_TEXT="${(j:, :)NEW_LABELS}"
else
  FIRST_THREE=("${NEW_LABELS[@]:0:3}")
  LABEL_TEXT="${(j:, :)FIRST_THREE} und weitere"
fi

if [[ $NEW_COUNT -eq 1 ]]; then
  TEXT="Paperclip Whitestag: neue Genehmigung — $LABEL_TEXT"
else
  TEXT="Paperclip Whitestag: $NEW_COUNT neue Genehmigungen — $LABEL_TEXT"
fi

# --- quiet hours check ---
HOUR=$(date +%H)
HOUR=${HOUR#0}  # strip leading zero
IS_QUIET=0
if [[ $HOUR -ge $QUIET_START || $HOUR -lt $QUIET_END ]]; then
  IS_QUIET=1
fi

# --- speak (unless quiet) ---
SPOKE=0
if [[ $IS_QUIET -eq 0 ]]; then
  if "$SPEAK_SCRIPT" "$TEXT"; then
    SPOKE=1
  else
    # speak failed (e.g. HomePod offline) — DO NOT update state, retry next poll
    exit 1
  fi
fi

# --- update state ---
# Merge: announced = (announced ∪ current_ids), capped at MAX_STATE_IDS (FIFO)
NOW=$(date -u '+%Y-%m-%dT%H:%M:%SZ')

# Determine lastSpokenAt: $NOW if we spoke this run, else previous value (or omitted)
if [[ $SPOKE -eq 1 ]]; then
  LAST_SPOKEN="$NOW"
else
  LAST_SPOKEN=$(jq -r '.lastSpokenAt // ""' "$STATE_FILE" 2>/dev/null || echo "")
fi

PREV_JSON=$(jq -c '.announcedApprovalIds // []' "$STATE_FILE" 2>/dev/null || echo '[]')
CURR_JSON=$(echo "$CURRENT_IDS" | jq -R . | jq -s .)

NEW_STATE=$(jq -n \
  --argjson cap "$MAX_STATE_IDS" \
  --arg now "$NOW" \
  --arg lastSpoken "$LAST_SPOKEN" \
  --argjson prev "$PREV_JSON" \
  --argjson curr "$CURR_JSON" \
  '
  ($prev + $curr) | unique as $merged |
  ($merged | (if length > $cap then .[(length - $cap):] else . end)) as $capped |
  {
    announcedApprovalIds: $capped,
    lastPolledAt: $now
  }
  | if $lastSpoken != "" then . + {lastSpokenAt: $lastSpoken} else . end
  ')

echo "$NEW_STATE" > "$STATE_FILE.tmp" && mv "$STATE_FILE.tmp" "$STATE_FILE"
exit 0
```

- [ ] **Step 2: Ausführbar machen**

```bash
chmod +x ~/.paperclip/scripts/homepod-watcher.sh
```

- [ ] **Step 3: Trockenlauf — State leer, prüfen was passieren würde**

State wegräumen (falls vorhanden) und Skript einmal manuell ausführen:

```bash
rm -f ~/.paperclip/state/homepod-watcher.json
~/.paperclip/scripts/homepod-watcher.sh
echo "exit=$?"
cat ~/.paperclip/state/homepod-watcher.json 2>/dev/null
```

Expected:
- Wenn aktuell **keine** pending Approvals existieren: Skript endet mit Exit 0, State-File **wird nicht** angelegt (kein Diff zu announcen).
- Wenn pending Approvals existieren: HomePod sagt sie an, State-File enthält `announcedApprovalIds` mit allen aktuellen IDs.

- [ ] **Step 4: Re-run — sollte still bleiben**

```bash
~/.paperclip/scripts/homepod-watcher.sh
echo "exit=$?"
```

Expected: Exit 0, kein TTS, kein Sound — alle aktuellen IDs sind bereits in `announcedApprovalIds`.

- [ ] **Step 5: Quiet-Hours-Verhalten testen (Zeit-Override)**

Quiet-Hours-Logik durch Erzwingen einer Nacht-Stunde testen:

```bash
# Simuliere: State leeren, dann Skript mit gefakter Stunde laufen lassen.
rm -f ~/.paperclip/state/homepod-watcher.json
HOUR_OVERRIDE=23 zsh -c '
  source ~/.paperclip/scripts/homepod-watcher.sh 2>/dev/null
' || true
# Alternative: Skript editieren, HOUR fest auf 23 setzen, einmal ausführen, danach zurückeditieren.
```

Wenn der `HOUR_OVERRIDE`-Trick wegen `set -u` nicht greift: temporär `HOUR=23` direkt nach der `HOUR=$(date +%H)`-Zeile einfügen, Skript einmal mit nicht-leerem Approval-Pool laufen lassen, prüfen dass **kein TTS** kommt aber State **trotzdem** aktualisiert wird, danach Override entfernen.

Expected: Kein Sound, aber `announcedApprovalIds` im State enthält die aktuellen IDs. (Damit es nicht morgens um 08:00 alles nachholt.)

- [ ] **Step 6: Commit (außerhalb des Repos — kein git commit)**

Skript liegt unter `~/.paperclip/scripts/`, kein Commit ins Paperclip-Repo.

---

## Task 4: launchd-Job einrichten

**Files:**
- Create: `~/Library/LaunchAgents/ing.paperclip.homepod-watcher.plist`

- [ ] **Step 1: plist schreiben**

Inhalt der Datei `~/Library/LaunchAgents/ing.paperclip.homepod-watcher.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>ing.paperclip.homepod-watcher</string>

    <key>ProgramArguments</key>
    <array>
        <string>/bin/zsh</string>
        <string>/Users/walterschoenenbroecher.de/.paperclip/scripts/homepod-watcher.sh</string>
    </array>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
        <key>HOME</key>
        <string>/Users/walterschoenenbroecher.de</string>
    </dict>

    <key>StartInterval</key>
    <integer>60</integer>

    <key>RunAtLoad</key>
    <true/>

    <key>StandardOutPath</key>
    <string>/Users/walterschoenenbroecher.de/Library/Logs/paperclip-homepod/watcher.log</string>

    <key>StandardErrorPath</key>
    <string>/Users/walterschoenenbroecher.de/Library/Logs/paperclip-homepod/watcher.err.log</string>
</dict>
</plist>
```

- [ ] **Step 2: Log-Verzeichnis anlegen**

```bash
mkdir -p ~/Library/Logs/paperclip-homepod
```

- [ ] **Step 3: launchd laden**

```bash
launchctl unload ~/Library/LaunchAgents/ing.paperclip.homepod-watcher.plist 2>/dev/null
launchctl load ~/Library/LaunchAgents/ing.paperclip.homepod-watcher.plist
```

Expected: Kein Fehler. (`unload` darf "no such job" sagen — wird ignoriert.)

- [ ] **Step 4: Job-Status prüfen**

```bash
launchctl list | grep ing.paperclip.homepod-watcher
```

Expected: Eine Zeile mit dem Label, PID-Spalte ggf. `-` (Skript ist One-Shot, läuft nur 1–2 s pro Tick), Exit-Code `0`.

- [ ] **Step 5: Eine Minute warten und Log prüfen**

```bash
sleep 65 && \
  ls -l ~/Library/Logs/paperclip-homepod/ && \
  cat ~/Library/Logs/paperclip-homepod/watcher.err.log
```

Expected: Log-Dateien existieren, `watcher.err.log` ist leer (oder enthält nur jq-Warnungen, die nicht fatal sind).

- [ ] **Step 6: State nach mindestens einem Tick prüfen**

```bash
cat ~/.paperclip/state/homepod-watcher.json 2>/dev/null || echo "no state yet (= keine pending approvals existierten)"
```

Expected: Entweder gültiges JSON mit `lastPolledAt`-Zeitstempel der letzten Minute, oder "no state yet" (wenn keine Approvals zum Tracken da waren).

---

## Task 5: End-to-End-Test der Push-Pipeline

**Files:**
- Keine (Verifikation)

- [ ] **Step 1: Aktuelle Pending-Approvals prüfen**

```bash
TOKEN=$(jq -r '.credentials["http://localhost:3100"].token' ~/.paperclip/auth.json)
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:3100/api/companies/9cebf3cf-efe8-4597-a400-f06488900a87/approvals?status=pending" | \
  jq '[.[] | {id, type, createdAt}]'
```

Expected: Liste (evtl. leer) der aktuell pending Approvals.

- [ ] **Step 2a: Wenn pending Approvals existieren — State leeren und auf nächsten Tick warten**

```bash
rm -f ~/.paperclip/state/homepod-watcher.json
echo "Warte bis zu 60 s auf den nächsten Watcher-Tick…"
```

Expected: Innerhalb der nächsten Minute sagt der HomePod "Studio" die Approvals an.

- [ ] **Step 2b: Wenn KEINE pending Approvals existieren — manuell eine triggern**

Walter triggert in der Paperclip-UI eine Aktion, die einen Approval erzeugt (z.B. neuen Agent in WHITESTAG vorschlagen → erzeugt `hire_agent`-Approval), oder er nutzt die API:

```bash
TOKEN=$(jq -r '.credentials["http://localhost:3100"].token' ~/.paperclip/auth.json)
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"HomePod-Test-Agent","role":"researcher","capabilities":"Test","budgetMonthlyCents":100}' \
  "http://127.0.0.1:3100/api/companies/9cebf3cf-efe8-4597-a400-f06488900a87/agent-hires"
```

Innerhalb von ≤60 s muss der HomePod "Studio" sagen: "Paperclip Whitestag: neue Genehmigung — Einstellung". Falls die Test-Approval nicht gewünscht ist, danach via Paperclip-UI ablehnen.

- [ ] **Step 3: State nach Ansage prüfen**

```bash
jq '.' ~/.paperclip/state/homepod-watcher.json
```

Expected: `announcedApprovalIds` enthält die getestete Approval-ID, `lastSpokenAt` ist innerhalb der letzten Minute.

- [ ] **Step 4: Re-Test — kein erneutes Sprechen**

```bash
sleep 65
jq '.lastPolledAt, .lastSpokenAt' ~/.paperclip/state/homepod-watcher.json
```

Expected: `lastPolledAt` aktualisiert, `lastSpokenAt` **unverändert** (es kam keine zweite Ansage zum gleichen Eintrag).

---

## Task 6: iOS-Shortcut "Paperclip-Status" anlegen (manuell durch Walter)

**Files:**
- Anleitung — keine Datei zum Generieren

> Dieser Task erfordert manuelle Aktionen auf Walters iPhone. Der Subagent/Engineer dokumentiert die Schritte und prüft am Ende, ob die Pull-Pipeline funktioniert.

- [ ] **Step 1: Shortcut anlegen**

Auf dem iPhone in der Shortcuts-App:

1. Plus-Button → "Neuer Kurzbefehl".
2. Name: **Paperclip-Status** (exakt — wird gleichzeitig die Siri-Phrase).

- [ ] **Step 2: Aktion "Inhalte von URL abrufen" hinzufügen**

- Aktion suchen: "Inhalte von URL abrufen"
- URL: `https://company.whitestag.ai/api/companies/9cebf3cf-efe8-4597-a400-f06488900a87/approvals?status=pending`
- Methode: `GET`
- Header (Plus → Header hinzufügen):
  - Schlüssel: `Authorization`
  - Wert: `Bearer pcp_board_985880896179574eedaddb10a734d3a65f1306778501e4f1`
  
  > Token aus `~/.paperclip/auth.json` Walter trägt ihn einmalig manuell ein. Bei Token-Rotation erneut anpassen.

- [ ] **Step 3: Aktion "JSON dekodieren" / "Wörterbuch aus Eingabe abrufen"**

- Aktion: "Wörterbuch aus Eingabe abrufen" — Input = vorherige URL-Antwort. Liefert eine Liste.

- [ ] **Step 4: Aktion "Anzahl ermitteln"**

- Aktion: "Anzahl" → Eingabe: das Wörterbuch aus Step 3.
- Ergebnis-Variable: **Anzahl**.

- [ ] **Step 5: IF-Verzweigung auf Anzahl**

- Aktion: "Wenn" → Variable **Anzahl**, Bedingung "ist gleich", Wert `0`.
- **Wenn-Zweig:** Aktion "Text vorlesen", Text: `Paperclip Whitestag: keine offenen Genehmigungen.`
- **Andernfalls-Zweig:**
  - Aktion: "Wiederhole mit jedem Eintrag" über das Wörterbuch (max. 3 Iterationen — manuell durch IF auf Index begrenzen oder einfach alle iterieren, wenn überschaubar).
  - In der Schleife: "Wörterbuchwert abrufen" für Schlüssel `type` → das Type-Mapping als IF-Kette anwenden:
    - `type == "hire_agent"` → Text "Einstellung"
    - `type == "approve_ceo_strategy"` → Text "Strategie-Freigabe"
    - sonst → Text-Variable mit dem Roh-Type
  - Ergebnis in eine Sammel-Text-Variable anhängen (mit ", " als Trenner).
  - Nach der Schleife: Aktion "Text vorlesen", Text:
    `Paperclip Whitestag: [Anzahl] offene Genehmigungen — [Sammel-Text].`

- [ ] **Step 6: Auf HomePod / iPhone testen**

1. Auf dem iPhone: Shortcut starten (Play-Button).

   Expected: iPhone liest die korrekte Anzahl + Typen vor.

2. Auf dem HomePod: "Hey Siri, Paperclip-Status".

   Expected: HomePod führt Shortcut über das gepairte iPhone aus, spricht das Ergebnis. Setzt voraus, dass am HomePod "Persönliche Anfragen" aktiv sind und das iPhone in Reichweite ist.

- [ ] **Step 7: Cloudflare-Tunnel-Erreichbarkeit verifizieren (falls Pull-Test fehlschlägt)**

```bash
curl -sv -H "Authorization: Bearer $(jq -r '.credentials[\"http://localhost:3100\"].token' ~/.paperclip/auth.json)" \
  "https://company.whitestag.ai/api/companies/9cebf3cf-efe8-4597-a400-f06488900a87/approvals?status=pending" | head -20
```

Expected: HTTP 200 mit JSON-Array. Wenn 404 / 5xx: prüfen, ob `company.whitestag.ai` als allowed Hostname im `~/.paperclip/scripts/launchd-paperclip.sh` (`PAPERCLIP_ALLOWED_HOSTNAMES`) eingetragen ist.

---

## Task 7: Final-Check & Tagesprotokoll

- [ ] **Step 1: Beide Pipelines laufen**

- Push: launchd-Job aktiv (`launchctl list | grep ing.paperclip.homepod-watcher`).
- Pull: "Hey Siri, Paperclip-Status" liefert vom HomePod aus eine Sprachantwort.

- [ ] **Step 2: Konsistenz-Check der Spec**

Spec [`docs/superpowers/specs/2026-05-11-paperclip-homepod-bridge-design.md`](../specs/2026-05-11-paperclip-homepod-bridge-design.md) durchlesen — wenn beim Bauen Abweichungen entstanden sind (z.B. anderer Device-Name, anderer API-Pfad, andere Stimme), Spec aktualisieren und committen.

- [ ] **Step 3: Tagesprotokoll & Chatverlauf gemäß CLAUDE.md erstellen**

Wird automatisch beim nächsten Feierabend-Signal angestoßen.

---

## Verifikation am Ende

| Erfolgskriterium aus Spec | Geprüft in Task |
|---|---|
| Neue Approval → ≤90 s Ansage | Task 5 Step 2/3 |
| Quiet Hours → kein Sprechen, State trotzdem aktualisiert | Task 3 Step 5 |
| Siri-Pull liest Status vor | Task 6 Step 6 |
| HomePod offline → kein Spam, retry später | Task 2 Step 5 + Task 3 Logik (kein State-Update bei Speak-Fail) |
| Kein Eingriff in laufendes Audio außer ~3 s | Task 2 Step 3 (manuelle Beobachtung) |
