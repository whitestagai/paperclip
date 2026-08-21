#!/usr/bin/env bash
# Board-API-Key-Wächter
#
# Der Paperclip-Board-API-Key in agent-learning.secret läuft 30 Tage nach
# Ausstellung ab. Danach brechen de.whitestag.agent-learning.knowledge und
# .lessons still mit HTTP 401 ab — sichtbar nur im /tmp-Log, das niemand liest.
# Genau so ist der Key am 2026-05-12 ausgestellt, am 2026-06-11 abgelaufen und
# das Ausbleiben der Lernschleifen erst am 2026-08-04 aufgefallen.
#
# Dieser Wächter läuft täglich und meldet per Mailhub:
#   - Key ist tot        (Live-Check gegen die API liefert 401)
#   - Key läuft bald ab  (<= WARN_DAYS Resttage laut "# Created:"-Header)
#
# Läuft als launchd-Dienst de.whitestag.board-key-monitor.

set -uo pipefail

INSTANCE="$HOME/.paperclip/instances/default"
SECRET_FILE="${SECRET_FILE:-$INSTANCE/agent-learning.secret}"
CONFIG_FILE="${CONFIG_FILE:-$INSTANCE/agent-learning.config.yaml}"
LOG="$HOME/.paperclip/logs/board-key-monitor.log"
STATUS="$HOME/.paperclip/logs/board-key-monitor-last.json"
# 5 Tage, nicht 7: der Autorenew verlaengert bereits ab 7 Resttagen. Wer bei 7
# warnt, meldet dessen Normalbetrieb als Stoerung. Was hier ankommt, heisst:
# der Autorenew hat zwei Laeufe hintereinander nicht gegriffen.
WARN_DAYS="${WARN_DAYS:-5}"
PSQL_DSN="${PSQL_DSN:-postgresql://paperclip:paperclip@localhost:54329/paperclip}"

MAILHUB_URL="http://127.0.0.1:5678/webhook/mailhub/send"
MAILHUB_SECRET="$(sed -n 's/^MAILHUB_SECRET=//p' "$INSTANCE/secrets/mailhub.env" 2>/dev/null | tr -d '\n' || true)"

PY=/opt/homebrew/bin/python3

mkdir -p "$(dirname "$LOG")"
log() { echo "[$(date '+%F %T')] $*" >> "$LOG"; }

log "===== Board-Key-Check Start"

# --- Key und Konfiguration laden --------------------------------------------
if [[ ! -f "$SECRET_FILE" ]]; then
  log "FEHLER: Secret-Datei nicht gefunden: $SECRET_FILE"
  ZUSTAND="missing"; RESTTAGE=""; HTTP_CODE=""; ABLAUF=""
else
  # shellcheck disable=SC1090
  set -a; . "$SECRET_FILE"; set +a
  API_BASE=$(yq -r '.paperclip.api_base' "$CONFIG_FILE" 2>/dev/null)
  COMPANY_ID=$(yq -r '.companies.whitestag.id' "$CONFIG_FILE" 2>/dev/null)

  # --- Restlaufzeit aus der Datenbank ----------------------------------------
  # Der Token kommt aus auth.json und wird von ing.paperclip.board-token-autorenew
  # verlaengert; ein Datum in dieser Datei waere sofort veraltet. Die Wahrheit
  # steht in board_api_keys, adressiert ueber den sha256 des Tokens.
  KEY_HASH=$(printf '%s' "${PAPERCLIP_BOARD_API_KEY:-}" | shasum -a 256 | cut -d' ' -f1)
  ABLAUF=$(psql "$PSQL_DSN" -At -c \
    "SELECT expires_at::date FROM board_api_keys WHERE key_hash='$KEY_HASH' AND revoked_at IS NULL ORDER BY expires_at DESC LIMIT 1;" \
    2>/dev/null)
  if [[ -n "$ABLAUF" ]]; then
    RESTTAGE=$(( ( $(date -j -f %Y-%m-%d "$ABLAUF" +%s 2>/dev/null) - $(date +%s) ) / 86400 ))
  fi

  # --- Live-Check: das ist die verlässliche Quelle ----------------------------
  # Der Header kann nach einer Key-Erneuerung veraltet sein, die API nicht.
  HTTP_CODE=$(curl -s -m 15 -o /dev/null -w '%{http_code}' \
    -H "Authorization: Bearer ${PAPERCLIP_BOARD_API_KEY:-}" \
    "$API_BASE/api/companies/$COMPANY_ID/agents" 2>/dev/null)

  case "$HTTP_CODE" in
    200)         ZUSTAND="ok" ;;
    401|403)     ZUSTAND="expired" ;;
    000)         ZUSTAND="api_down" ;;   # Paperclip läuft nicht — kein Key-Problem
    *)           ZUSTAND="unerwartet" ;;
  esac

  # Gültiger Key, aber Ablauf in Sichtweite
  if [[ "$ZUSTAND" == "ok" && -n "${RESTTAGE:-}" && "$RESTTAGE" -le "$WARN_DAYS" ]]; then
    ZUSTAND="laeuft_bald_ab"
  fi
fi

log "Zustand=$ZUSTAND HTTP=$HTTP_CODE Ablauf=${ABLAUF:-?} Resttage=${RESTTAGE:-?}"

# --- Status-JSON ------------------------------------------------------------
# Werte via Umgebung statt argv: der Alarmtext ist mehrzeilig und enthaelt
# Anfuehrungszeichen — als Shell-Argument in verschachtelten Quotes zerlegt
# das den Python-Aufruf.
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
ZUSTAND="$ZUSTAND" HTTP_CODE="${HTTP_CODE:-}" ABLAUF="${ABLAUF:-}" RESTTAGE="${RESTTAGE:-}" \
"$PY" > "$STATUS" <<'PY'
import json, os
print(json.dumps({
    'timestamp': os.environ['TS'],
    'zustand': os.environ['ZUSTAND'],
    'http_code': os.environ['HTTP_CODE'],
    'ablauf': os.environ['ABLAUF'],
    'resttage': os.environ['RESTTAGE'],
}, ensure_ascii=False, indent=2))
PY

# --- Alarm ------------------------------------------------------------------
case "$ZUSTAND" in
  expired)
    BETREFF="Board-API-Key abgelaufen — agent-learning steht still"
    TEXT="Der Board-Token wird von der API abgelehnt (HTTP $HTTP_CODE).

Folge: de.whitestag.agent-learning.knowledge (taeglich 01:00) und
de.whitestag.agent-learning.lessons (taeglich 02:00) brechen jede Nacht ab.

Ablauf laut Datenbank: ${ABLAUF:-kein passender Key in board_api_keys}

Der Token kommt aus ~/.paperclip/auth.json und wird eigentlich von
ing.paperclip.board-token-autorenew (taeglich 05:00) gueltig gehalten.
Dass er trotzdem abgelehnt wird, heisst: dieser Dienst arbeitet nicht.

Pruefen:
  launchctl list ing.paperclip.board-token-autorenew
  tail -30 ~/Library/Logs/paperclip-board-token-autorenew/autorenew.log"
    ;;
  laeuft_bald_ab)
    BETREFF="Board-Token laeuft in $RESTTAGE Tag(en) ab — Autorenew greift nicht"
    TEXT="Der Board-Token ist noch gueltig (bis $ABLAUF), haette aber laengst
verlaengert sein muessen: ing.paperclip.board-token-autorenew verlaengert
taeglich um 05:00, sobald weniger als 7 Tage Restlaufzeit bleiben.

Bei $RESTTAGE Resttagen hat er also mehrfach nicht gegriffen. Laeuft der Token
ab, brechen die agent-learning-Schleifen (knowledge 01:00, lessons 02:00) ab.

Pruefen:
  launchctl list ing.paperclip.board-token-autorenew
  tail -30 ~/Library/Logs/paperclip-board-token-autorenew/autorenew.log"
    ;;
  missing)
    BETREFF="Board-Key-Datei fehlt"
    TEXT="Die Secret-Datei $SECRET_FILE existiert nicht. Die agent-learning-Schleifen koennen nicht laufen."
    ;;
  unerwartet)
    BETREFF="Board-API-Key-Check: unerwartete Antwort (HTTP $HTTP_CODE)"
    TEXT="Der Live-Check gegen $API_BASE lieferte HTTP $HTTP_CODE. Bitte pruefen."
    ;;
  *)
    # ok oder api_down (Paperclip nicht erreichbar ist kein Key-Problem)
    log "Kein Alarm noetig."
    log "===== Ende"
    exit 0
    ;;
esac

if [[ -z "$MAILHUB_SECRET" ]]; then
  log "WARNUNG: kein MAILHUB_SECRET — Alarm '$BETREFF' konnte nicht gemailt werden."
  log "===== Ende"
  exit 1
fi

PAYLOAD=$(BETREFF="$BETREFF" TEXT="$TEXT" "$PY" <<'PY'
import json, os
betreff, body = os.environ['BETREFF'], os.environ['TEXT']
print(json.dumps({
    'from': 'cto@whitestag.ai',
    'to': 'ws@whitestag.ai',
    'subject': betreff,
    'text': body,
    'html': '<pre>' + body + '</pre>',
    'attachments': [],
}, ensure_ascii=False))
PY
)

if [[ -z "$PAYLOAD" ]]; then
  log "FEHLER: Mail-Payload konnte nicht gebaut werden — Alarm '$BETREFF' nicht versendet."
  log "===== Ende"
  exit 1
fi

MAIL_ANTWORT=$(curl -s -m 20 -w '\nHTTP=%{http_code}' -X POST "$MAILHUB_URL" \
  -H "Content-Type: application/json" \
  -H "X-Mailhub-Secret: $MAILHUB_SECRET" \
  --data "$PAYLOAD" 2>&1)
MAIL_HTTP=$(printf '%s' "$MAIL_ANTWORT" | sed -n 's/.*HTTP=\([0-9]*\)$/\1/p')

if [[ "$MAIL_HTTP" == "200" ]]; then
  log "Alarm gemailt: $BETREFF"
else
  log "FEHLER: Mailversand fehlgeschlagen (HTTP ${MAIL_HTTP:-?}) — Alarm '$BETREFF' kam NICHT an."
  log "Mailhub-Antwort: $(printf '%s' "$MAIL_ANTWORT" | tr '\n' ' ' | head -c 300)"
  log "===== Ende"
  exit 1
fi

log "===== Ende"
