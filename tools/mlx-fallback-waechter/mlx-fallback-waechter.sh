#!/bin/bash
# MLX-Fallback-Waechter (laeuft auf dem MacBook M5 Max)
#
# PROBLEM: `gemma-4-31b-it-mlx` ist das Fallback-Modell von 14 Agenten und des
# Wake-Satelliten. Es wird gelegentlich verdraengt und danach per JIT mit dem
# Standard-TTL von 1 h nachgeladen. Nach einer Stunde ohne Aufruf entlaedt es
# sich dann selbst — und weil es NUR Fallback ist, wird es selten aufgerufen.
# Ergebnis: das Netz verschwindet unbemerkt, und der erste echte Fallback-Fall
# laeuft in "Model unloaded" (am 22.08. eine ganze Fehlerwelle ausgeloest).
#
# LOESUNG: regelmaessig pruefen und bei gesetztem TTL bzw. fehlendem Modell
# OHNE `--ttl` nachladen — das ergibt ttlMs=null, also dauerhaft.
#
# WICHTIG:
#  - Vollen Pfad zu lms nutzen. Im PATH liegt ein npx-Wrapper aus nvm, der
#    jedes Kommando mit einer "Invalid usage"-Box quittiert OHNE etwas zu tun.
#  - Nie entladen, solange das Modell rechnet — das bricht einen laufenden
#    Agentenlauf ab.
#  - launchd startet bei StartInterval JEDEN Zyklus einen NEUEN Prozess.
#    Zaehler ueber Zyklen hinweg muessen deshalb in die State-Datei, nicht in
#    eine Shell-Variable.
set -u

MODELL="gemma-4-31b-it-mlx"
LMS="${LMS_BIN:-$HOME/.lmstudio/bin/lms}"   # Default = voller Pfad (npx-Wrapper-Falle); LMS_BIN nur fuer Tests
LOG="$HOME/.paperclip-logs/mlx-fallback-waechter.log"
STATE="$HOME/.paperclip-logs/mlx-fallback-waechter.state"
MAX_FEHLER=4          # danach eine Warnzeile ins Log (sichtbar fuer Menschen)

mkdir -p "$(dirname "$LOG")"
log(){ echo "$(date '+%Y-%m-%d %H:%M:%S')  $*" >> "$LOG"; }

zustand(){   # gibt "status|ttlMs" aus, sonst "FEHLT|-" bzw. "UNBEKANNT|-"
  "$LMS" ps --json 2>/dev/null | python3 -c "
import sys, json
ziel = '$MODELL'
try:
    daten = json.load(sys.stdin)
except Exception:
    print('UNBEKANNT|-'); raise SystemExit
if not isinstance(daten, list):
    daten = daten.get('models', [])
for m in daten:
    if m.get('modelKey') == ziel:
        print(str(m.get('status', '?')) + '|' + str(m.get('ttlMs')))
        break
else:
    print('FEHLT|-')
"
}

fehler_lesen(){ [ -f "$STATE" ] && cat "$STATE" || echo 0; }
fehler_schreiben(){ echo "$1" > "$STATE"; }

Z="$(zustand)"
STATUS="${Z%%|*}"
TTL="${Z##*|}"

case "$STATUS" in
  UNBEKANNT)
    n=$(( $(fehler_lesen) + 1 )); fehler_schreiben "$n"
    log "LM Studio nicht abfragbar (Fehler $n in Folge)"
    [ "$n" -ge "$MAX_FEHLER" ] && log "WARNUNG: seit $n Zyklen kein Kontakt zu LM Studio"
    exit 0
    ;;
  GENERATING|PROCESSINGPROMPT|processingPrompt|generating)
    # arbeitet gerade: nichts anfassen. TTL notfalls beim naechsten Zyklus.
    log "beschaeftigt ($STATUS, ttl=$TTL) — kein Eingriff"
    fehler_schreiben 0
    exit 0
    ;;
esac

fehler_schreiben 0

if [ "$STATUS" = "FEHLT" ]; then
  log "Modell NICHT geladen — lade ohne TTL nach"
  if "$LMS" load "$MODELL" --parallel 4 -y >>"$LOG" 2>&1; then
    log "  nachgeladen"
  else
    log "  FEHLER beim Laden"
  fi
elif [ "$TTL" != "None" ] && [ "$TTL" != "null" ] && [ -n "$TTL" ]; then
  log "TTL gesetzt ($TTL ms) — entlade und lade ohne TTL neu"
  "$LMS" unload "$MODELL" >>"$LOG" 2>&1
  sleep 3
  if "$LMS" load "$MODELL" --parallel 4 -y >>"$LOG" 2>&1; then
    NEU="$(zustand)"
    log "  neu geladen, Zustand jetzt: $NEU"
  else
    log "  FEHLER beim Neuladen — Fallback ist derzeit OHNE Netz"
  fi
fi

# Log begrenzen (launchd laeuft dauerhaft)
if [ -f "$LOG" ] && [ "$(wc -l < "$LOG")" -gt 2000 ]; then
  tail -800 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
fi
