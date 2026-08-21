#!/bin/zsh
# de.whitestag.hdd-katalog -- taeglicher Katalog-Lauf
#
# Findet neue/geaenderte Dokumente auf dem Archiv-Share, klassifiziert sie
# (LM Studio / Mistral, neue Bild-PDFs per OCR) und schreibt Katalog-Notizen
# in den Obsidian-Vault. Inkrementell und idempotent -- der Ledger merkt sich
# alles, ein Doppellauf schadet nicht.
#
# Bewusst NICHT --reaktiviere: der kein_text-Rueckstand (zurueckgestellte
# Alt-Scans) wird hier nicht angefasst, nur frisch hinzugekommene Dokumente.

set -uo pipefail

KAT="/Users/walterschoenenbroecher.de/Library/CloudStorage/SynologyDrive-Mac/Claude Code MAC/Obsidian"
P="/opt/homebrew/bin/python3"
MAP="$KAT/hdd-map.yaml"
LOG="$HOME/.paperclip/logs/hdd-katalog.log"
LM="http://localhost:1234/v1/models"

mkdir -p "$(dirname "$LOG")"
cd "$KAT" || { echo "$(date '+%F %T') Projektverzeichnis fehlt" >> "$LOG"; exit 1; }


# --- Meldung bei uebersprungenem Lauf ------------------------------------------
# Am 29.07. fiel ein Lauf aus, ohne dass es jemand bemerkte: das Skript bricht
# bei fehlendem Share oder offline LM Studio bewusst sauber ab, schrieb das aber
# nur ins Log. Ein stiller Ausfall ueber mehrere Tage waere unsichtbar geblieben.
MAILHUB_URL="http://127.0.0.1:5678/webhook/mailhub/send"
MAILHUB_SECRET="$(sed -n 's/^MAILHUB_SECRET=//p' "$HOME/.paperclip/instances/default/secrets/mailhub.env" 2>/dev/null | tr -d '\n' || true)"
[ -n "${MAILHUB_SECRET:-}" ] || { echo "FEHLER: MAILHUB_SECRET nicht aus ~/.paperclip/instances/default/secrets/mailhub.env lesbar" >&2; exit 2; }

melde_uebersprungen() {
  local grund="$1"
  local betreff="HDD-Katalog: Nachtlauf uebersprungen ($grund)"
  local text="Der naechtliche Katalog-Lauf wurde am $(date '+%F um %H:%M') uebersprungen.

Grund: $grund

Es wurde nichts veraendert -- der Lauf versucht es in der naechsten Nacht erneut.
Bleibt die Meldung mehrere Tage in Folge aus dem gleichen Grund, stimmt etwas
Grundsaetzliches nicht (Share nicht gemountet, LM Studio dauerhaft aus).

Log: $LOG"
  /usr/bin/curl -s -m 20 -X POST "$MAILHUB_URL" \
    -H "Content-Type: application/json" \
    -H "X-Mailhub-Secret: $MAILHUB_SECRET" \
    --data "$(/opt/homebrew/bin/python3 -c '
import json,sys
print(json.dumps({"from":"cto@whitestag.ai","to":"ws@whitestag.ai",
                  "subject":sys.argv[1],"text":sys.argv[2],
                  "html":"<pre>"+sys.argv[2]+"</pre>","attachments":[]}))
' "$betreff" "$text")" >> "$LOG" 2>&1
  echo "" >> "$LOG"
}

echo "===== $(date '+%F %T') Katalog-Lauf Start" >> "$LOG"

# 1. Spaeher -- neue/geaenderte Dokumente finden.
#    Exit 2 = Share nicht gemountet / Scan unvollstaendig -> heute abbrechen,
#    nichts kaputtmachen, morgen erneut versuchen.
"$P" -m hdd_katalog.cli scan --map "$MAP" >> "$LOG" 2>&1
rc=$?
if [ "$rc" -eq 2 ]; then
  echo "$(date '+%F %T') Share nicht verfuegbar -- Abbruch, morgen erneut" >> "$LOG"
  echo "===== $(date '+%F %T') Ende (uebersprungen)" >> "$LOG"
  melde_uebersprungen "Share nicht gemountet"
  exit 0
fi

# 2. LM Studio erreichbar? Sonst Klassifikation ueberspringen -- die neuen
#    Dokumente bleiben 'neu' und werden in der naechsten Nacht geholt.
if ! curl -s --max-time 10 "$LM" >/dev/null 2>&1; then
  echo "$(date '+%F %T') LM Studio nicht erreichbar -- Klassifikation uebersprungen" >> "$LOG"
  melde_uebersprungen "LM Studio nicht erreichbar"
  echo "===== $(date '+%F %T') Ende (LM Studio offline)" >> "$LOG"
  exit 0
fi

# 3. Klassifizieren -- neue Textdokumente + neue Bild-PDFs (--ocr) inline.
#    Exitcode wird geprueft: ein Absturz hier hinterliess bisher nur einen
#    Traceback mitten im Log und lief danach still weiter, als waere alles gut.
#    Der Lauf wird trotzdem fortgesetzt (Veroeffentlichung des bereits
#    Klassifizierten ist immer noch richtig), aber die Zeile steht sichtbar im
#    Log und ist greppbar.
"$P" -m hdd_katalog.cli klassifiziere --backend lmstudio --ocr --limit 800 >> "$LOG" 2>&1
rc=$?
if [ "$rc" -ne 0 ]; then
  echo "$(date '+%F %T') FEHLER: klassifiziere endete mit Exitcode $rc -- Traceback oben im Log. Der 'neu'-Bestand ist NICHT abgearbeitet." >> "$LOG"
fi

# 4. Veroeffentlichen -- hohe Konfidenz -> Katalog/, Unsicheres -> _INBOX/.
"$P" -m hdd_katalog.cli publish --live >> "$LOG" 2>&1

"$P" -m hdd_katalog.cli status >> "$LOG" 2>&1
echo "===== $(date '+%F %T') Ende" >> "$LOG"
