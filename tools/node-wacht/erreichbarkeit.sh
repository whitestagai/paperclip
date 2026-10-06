#!/bin/zsh
# Protokolliert die Erreichbarkeit des LM-Link-Node WHITESTAG-AI.
# Reine Beobachtung: schreibt eine Zeile je Lauf, alarmiert NICHT.
# Zweck: Entscheidungsgrundlage fuer Welle B (die 12 qwen-Agenten inkl.
# C-Suite auf den Node-Fallback umstellen) — dafuer muss belegt sein, dass
# der Node durchlaeuft. Siehe
# docs/superpowers/specs/2026-10-06-whitestag-ai-node-farm-einbindung-design.md

LMS="$HOME/.lmstudio/bin/lms"
LOG="$HOME/.paperclip/logs/node-erreichbarkeit.log"
NODE="WHITESTAG-AI"
TS=$(date "+%Y-%m-%d %H:%M:%S")

mkdir -p "$(dirname "$LOG")"

# Status aus lms link status: die zwei Zeilen nach dem Geraetenamen.
# "Status: disconnected" enthaelt "connected" als Teilstring — darum auf
# den vollen Ausdruck pruefen.
# ACHTUNG: `lms link status` schreibt seine Ausgabe auf STDERR, nicht
# stdout (geprueft 06.10.2026: 0 Zeilen stdout, 17 Zeilen stderr).
# Ein `2>/dev/null` verwirft genau das, was hier gebraucht wird.
STATUS_BLOCK=$("$LMS" link status 2>&1 | grep -A4 "$NODE")
if [[ -z "$STATUS_BLOCK" ]]; then
  echo "$TS | UNBEKANNT | lms link status lieferte nichts (LM Studio hier aus?)" >> "$LOG"
  exit 0
fi

if echo "$STATUS_BLOCK" | grep -q "Status: connected"; then
  VERB="connected"
else
  VERB="disconnected"
fi

# Gegenprobe ueber die API: loesen die beiden Fallback-Modelle auf?
# Das ist der Zustand, auf den es fuer die Agenten ankommt — die fragen
# ueber localhost:1234 an, nicht ueber lms.
MODELLE=""
for ID in gemma-4-31b-win qwen3.6-35b-win; do
  CODE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 \
         "http://127.0.0.1:1234/api/v0/models/$ID" 2>/dev/null)
  MODELLE="$MODELLE $ID=$CODE"
done

echo "$TS | $VERB |$MODELLE" >> "$LOG"
