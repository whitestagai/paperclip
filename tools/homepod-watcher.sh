#!/bin/zsh
# homepod-watcher.sh — alle 60 s via launchd ausgeführt.
# Pollt pending Approvals der WHITESTAG-Company, sagt neue Einträge
# über den HomePod "Studio" an, persistiert State, respektiert Quiet Hours.

set -u

WHITESTAG_COMPANY_ID="9cebf3cf-efe8-4597-a400-f06488900a87"
PAPERCLIP_BASE="${PAPERCLIP_API_URL:-http://127.0.0.1:3100}"
PAPERCLIP_BASE="${PAPERCLIP_BASE%/}"
API_BASE="$PAPERCLIP_BASE/api"
AUTH_FILE="$HOME/.paperclip/auth.json"
# auth.json ist nach der Ausstellungs-URL geschluesselt, die nicht mit
# PAPERCLIP_API_URL uebereinstimmen muss (localhost vs. 127.0.0.1).
AUTH_KEY="${PAPERCLIP_AUTH_KEY:-http://localhost:3100}"
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
# --- manual mute check (via /mute endpoint) ---
if [[ -f "$STATE_DIR/homepod-watcher.disabled" ]]; then
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
