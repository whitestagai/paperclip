#!/bin/zsh
# de.whitestag.vault-tagger -- nächtlicher Obsidian-Frontmatter-Tagger
#
# Läuft täglich um 00:00 als launchd-Dienst, vor dem Vault-Maintainer-Agenten
# (der um 01:00 geweckt wird). Der Agent liest nur noch den Status aus
# ~/.paperclip/logs/vault-tagger-last.json und den Report aus dem Vault.
#
# Kein Timeout-Problem: der Job läuft unabhängig vom Agenten-Heartbeat durch.

set -uo pipefail

TAGGER_DIR="/Users/walterschoenenbroecher.de/Library/CloudStorage/SynologyDrive-Mac/Claude Code MAC/Paperclip/obsidian-tagger"
LOG="$HOME/.paperclip/logs/vault-tagger.log"
STATUS="$HOME/.paperclip/logs/vault-tagger-last.json"
MAILHUB_URL="http://127.0.0.1:5678/webhook/mailhub/send"
MAILHUB_SECRET="$(sed -n 's/^MAILHUB_SECRET=//p' "$HOME/.paperclip/instances/default/secrets/mailhub.env" 2>/dev/null | tr -d '\n' || true)"

mkdir -p "$(dirname "$LOG")"
echo "===== $(date '+%F %T') Vault-Tagger Start" >> "$LOG"

# --- Tagger ausführen -------------------------------------------------------
# stdout enthält alle log()-Zeilen (mit Zeitstempel) plus "REPORT_PATH=..."
RUN_OUT=$("$TAGGER_DIR/.venv/bin/python" "$TAGGER_DIR/tagger.py" --apply --limit 200 --report 2>&1)
EXIT_CODE=$?

printf '%s\n' "$RUN_OUT" >> "$LOG"
echo "===== $(date '+%F %T') Vault-Tagger Ende (exit $EXIT_CODE)" >> "$LOG"

# --- Relevante Felder extrahieren -------------------------------------------
REPORT_PATH=$(printf '%s\n' "$RUN_OUT" | grep '^REPORT_PATH=' | tail -1 | sed 's/^REPORT_PATH=//')
FERTIG=$(printf '%s\n' "$RUN_OUT" | grep 'Fertig\. ok=' | tail -1)

# --- Status-JSON für den Agenten schreiben ----------------------------------
/opt/homebrew/bin/python3 -c "
import json, sys
print(json.dumps({
    'timestamp': sys.argv[1],
    'exit_code': int(sys.argv[2]),
    'report_path': sys.argv[3],
    'fertig': sys.argv[4],
}, ensure_ascii=False, indent=2))
" \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  "$EXIT_CODE" \
  "${REPORT_PATH:-}" \
  "${FERTIG:-}" > "$STATUS"

# --- Fehler-Mail bei Exit != 0 ----------------------------------------------
if [[ "$EXIT_CODE" -ne 0 ]] && [[ -n "${MAILHUB_SECRET:-}" ]]; then
  LETZTE_ZEILEN=$(printf '%s\n' "$RUN_OUT" | tail -20)
  /usr/bin/curl -s -m 20 -X POST "$MAILHUB_URL" \
    -H "Content-Type: application/json" \
    -H "X-Mailhub-Secret: $MAILHUB_SECRET" \
    --data "$(/opt/homebrew/bin/python3 -c "
import json, sys
body = sys.argv[1]
print(json.dumps({
    'from': 'cto@whitestag.ai',
    'to': 'ws@whitestag.ai',
    'subject': 'Vault-Tagger: Nachtlauf fehlgeschlagen (exit $EXIT_CODE)',
    'text': body,
    'html': '<pre>' + body + '</pre>',
    'attachments': [],
}))
" "$LETZTE_ZEILEN")" >> "$LOG" 2>&1
fi
