#!/usr/bin/env bash
# send_advisor_mail.sh — sendet die Advisor-Mail an Walter über den n8n-Mailhub.
# Usage: send_advisor_mail.sh --subject "..." --html-file /pfad/body.html [--text-file /pfad/body.txt] [--dry-run]
# Exit: 0 ok/dry-run, 1 Argument-/Validierungsfehler, 2 Webhook-/HTTP-Fehler
set -euo pipefail

WEBHOOK_URL="http://127.0.0.1:5678/webhook/mailhub/send"
MAILHUB_SECRET="$(sed -n 's/^MAILHUB_SECRET=//p' "$HOME/.paperclip/instances/default/secrets/mailhub.env" 2>/dev/null | tr -d '\n' || true)"
[ -n "${MAILHUB_SECRET:-}" ] || { echo "FEHLER: MAILHUB_SECRET nicht aus ~/.paperclip/instances/default/secrets/mailhub.env lesbar" >&2; exit 2; }
FROM_ADDR="cto@whitestag.ai"
TO_ADDR="ws@whitestag.ai"

SUBJECT=""; HTML_FILE=""; TEXT_FILE=""; DRY=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --subject) SUBJECT="$2"; shift 2;;
    --html-file) HTML_FILE="$2"; shift 2;;
    --text-file) TEXT_FILE="$2"; shift 2;;
    --dry-run) DRY="1"; shift;;
    *) echo "unbekanntes Argument: $1" >&2; exit 1;;
  esac
done
[[ -n "$SUBJECT" && -f "$HTML_FILE" ]] || { echo "subject und gueltige --html-file noetig" >&2; exit 1; }

# Plain-Text-Fallback: aus --text-file ODER grob aus dem HTML gestrippt
build_payload() {
python3 - "$FROM_ADDR" "$TO_ADDR" "$SUBJECT" "$HTML_FILE" "${TEXT_FILE:-}" <<'PY'
import json, sys, re
frm, to, subject, html_file, text_file = sys.argv[1:6]
html = open(html_file, encoding="utf-8").read()
if text_file:
    text = open(text_file, encoding="utf-8").read()
else:
    text = re.sub(r"<[^>]+>", "", html)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
print(json.dumps({"from": frm, "to": to, "subject": subject,
                  "text": text, "html": html, "attachments": []}))
PY
}

payload="$(build_payload)"

if [[ -n "$DRY" ]]; then
  echo "[dry-run] wuerde senden an $TO_ADDR: $SUBJECT (${#payload} bytes payload)"
  exit 0
fi

http_code="$(curl -sS -o /tmp/advisor-mail-resp.out -w '%{http_code}' -m 30 \
  -X POST "$WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -H "X-Mailhub-Secret: $MAILHUB_SECRET" \
  -d "$payload" || echo "000")"

if [[ "$http_code" =~ ^2 ]]; then
  echo "gesendet ($http_code): $SUBJECT"
else
  echo "FEHLER beim Senden (HTTP $http_code): $(cat /tmp/advisor-mail-resp.out 2>/dev/null | head -c 300)" >&2
  exit 2
fi
