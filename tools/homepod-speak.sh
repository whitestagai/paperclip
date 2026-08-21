#!/bin/zsh
# homepod-speak.sh — sendet TTS direkt zum HomePod "Studio" via pyatv.
# Usage: homepod-speak.sh "Text der gesprochen werden soll"
# Greift NICHT in das System-Audio-Routing ein — Mac-Wiedergabe läuft parallel weiter.

set -u

HOMEPOD_ID="1E:61:61:14:AC:8B"
ATVREMOTE="$HOME/.local/bin/atvremote"
LOG_DIR="$HOME/.paperclip/state"
LOG_FILE="$LOG_DIR/homepod-speak.log"

mkdir -p "$LOG_DIR"

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 \"text to speak\"" >&2
  exit 2
fi

TEXT="$1"
TS=$(date '+%Y-%m-%dT%H:%M:%S%z')
TMPFILE="/tmp/homepod-speak-$$-$(date +%s).wav"
trap "rm -f $TMPFILE" EXIT

# WAV (Microsoft-PCM 16-bit 44.1 kHz) — pyatv/miniaudio kann AIFF nicht dekodieren
if ! say -v Anna -o "$TMPFILE" --data-format=LEI16@44100 --file-format=WAVE "$TEXT" 2>/dev/null; then
  echo "$TS [error] say failed for text=$(printf '%q' "$TEXT")" >> "$LOG_FILE"
  exit 1
fi

if "$ATVREMOTE" --id "$HOMEPOD_ID" stream_file="$TMPFILE" >/dev/null 2>&1; then
  echo "$TS [ok] spoke=$(printf '%q' "$TEXT")" >> "$LOG_FILE"
  exit 0
fi

echo "$TS [error] atvremote stream failed text=$(printf '%q' "$TEXT")" >> "$LOG_FILE"
exit 1
