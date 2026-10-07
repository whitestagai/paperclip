#!/bin/zsh
# Protokolliert die Erreichbarkeit des LM-Link-Node WHITESTAG-AI.
# Reine Beobachtung: schreibt eine Zeile je Lauf, alarmiert NICHT. Ein
# Ausfall faellt deshalb erst beim naechsten Lauf der Modell-Aufsicht auf
# (einmal taeglich) — der 15-Minuten-Takt ist Aufzeichnungsdichte, keine
# Reaktionszeit.
#
# Zweck: Entscheidungsgrundlage dafuer, ob der Node als Fallback-Geraet
# von 37 Agenten dauerhaft taugt. Siehe
# docs/superpowers/specs/2026-10-06-whitestag-ai-node-farm-einbindung-design.md
#
# Die drei *_BIN/_FILE-Variablen sind nur fuer test_erreichbarkeit.py da.

LMS="${LMS_BIN:-$HOME/.lmstudio/bin/lms}"
CURL="${CURL_BIN:-curl}"
LOG="${LOG_FILE:-$HOME/.paperclip/logs/node-erreichbarkeit.log}"
TIMEOUT_BIN="${TIMEOUT_BIN:-/opt/homebrew/bin/timeout}"
NODE="WHITESTAG-AI"
TS=$(date "+%Y-%m-%d %H:%M:%S")

mkdir -p "$(dirname "$LOG")"

# `lms link status` schreibt seine Ausgabe auf STDERR, nicht stdout
# (geprueft 06.10.2026: 0 Zeilen stdout, 17 Zeilen stderr). Ein
# `2>/dev/null` verwirft genau das, was hier gebraucht wird.
#
# Mit Zeitgrenze: haengt LM Link bei gestoertem Netz, laeuft der Job sonst
# unbegrenzt — und launchd startet bei StartInterval KEINE zweite Kopie
# desselben Jobs. Die Aufzeichnung stuende dann still und das Log zeigte
# nur eine Luecke, die wie "nichts passiert" aussieht statt wie "Node weg".
if [[ -x "$TIMEOUT_BIN" ]]; then
  ROH=$("$TIMEOUT_BIN" 30 "$LMS" link status 2>&1)
else
  ROH=$("$LMS" link status 2>&1)
fi

# Den Block des Geraets am NAECHSTEN Geraeteeintrag beenden, nicht nach
# fester Zeilenzahl: ein getrennter Node hat keine "Loaded Models
# Instances", sein Block ist also kuerzer. Ein `grep -A4` liest dann in das
# naechste Geraet hinein und findet dort "Status: connected" — der Node
# wuerde als verbunden protokolliert, obwohl er weg ist. Siehe
# test_erreichbarkeit.py::test_getrennter_node_mit_folgendem_geraet_*
STATUS_BLOCK=$(echo "$ROH" | awk -v n="$NODE" '/^  - /{p=(index($0,n)>0)} p')

if [[ -z "$STATUS_BLOCK" ]]; then
  echo "$TS | UNBEKANNT | $NODE nicht in der Geraeteliste (LM Studio hier aus, oder Zeitgrenze)" >> "$LOG"
  exit 0
fi

# "Status: disconnected" enthaelt "connected" als Teilstring — darum auf
# den vollen Ausdruck pruefen.
if echo "$STATUS_BLOCK" | grep -q "Status: connected"; then
  VERB="connected"
else
  VERB="disconnected"
fi

# Gegenprobe ueber die API: loesen die beiden Fallback-Modelle auf? Das ist
# der Zustand, auf den es fuer die Agenten ankommt — die fragen ueber
# localhost:1234 an, nicht ueber lms.
MODELLE=""
for ID in gemma-4-31b-win qwen3.6-35b-win; do
  CODE=$("$CURL" -s -o /dev/null -w '%{http_code}' --max-time 20 \
         "http://127.0.0.1:1234/api/v0/models/$ID" 2>/dev/null)
  MODELLE="$MODELLE $ID=${CODE:-000}"
done

echo "$TS | $VERB |$MODELLE" >> "$LOG"

# Log beschneiden, damit es nicht unbegrenzt waechst (96 Zeilen/Tag).
if [[ -f "$LOG" ]]; then
  ZEILEN=$(wc -l < "$LOG")
  if (( ZEILEN > 20000 )); then
    tail -n 15000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
  fi
fi
