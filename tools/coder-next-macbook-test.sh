#!/bin/bash
# Einmaliger Nacht-Test (2026-07-24): Passt qwen3-coder-next real auf den MacBook?
# Das --estimate-only-Tool lieferte fuer coder-next eine konstante, unglaubwuerdige
# Zahl (110.39 GiB egal welcher ctx/parallel). Deshalb hier ein echter Ladeversuch
# mit Selbst-Aufraeumen. Additiv + konservativ: laedt coder-next ZUSAETZLICH auf den
# MacBook (der aktuell ~88 GB frei hat), prueft Koexistenz mit den vorhandenen
# Modellen, entlaedt wieder und stellt preferred=Studio wieder her.
set +e
LMS="$HOME/.lmstudio/bin/lms"
LOG="$HOME/.paperclip/logs/coder-next-macbook-test.log"
mkdir -p "$HOME/.paperclip/logs"
ts(){ date "+%Y-%m-%d %H:%M:%S"; }
log(){ echo "[$(ts)] $*" >>"$LOG"; }

log "===== Nacht-Test coder-next @ MacBook START ====="

MACBOOK_ID=$("$LMS" link status --json 2>/dev/null | python3 -c "import sys,json;d=json.load(sys.stdin);print(next((p['deviceIdentifier'] for p in d.get('peers',[]) if 'acbook' in p.get('deviceName','')),''))")
STUDIO_ID=$("$LMS" link status --json 2>/dev/null | python3 -c "import sys,json;print(json.load(sys.stdin).get('deviceIdentifier',''))")
log "MacBook-ID=$MACBOOK_ID Studio-ID=$STUDIO_ID"

log "--- Ist-Zustand VOR Test ---"
"$LMS" ps >>"$LOG" 2>&1

# Merken, welche Modelle vor dem Test auf dem MacBook lagen (zum Wiederherstellen)
BEFORE=$("$LMS" ps --json 2>/dev/null)

"$LMS" link set-preferred-device "$MACBOOK_ID" >>"$LOG" 2>&1
log "preferred -> MacBook"

for P in 1 4; do
  log "--- Ladeversuch coder-next -c 65000 --parallel $P ---"
  OUT=$("$LMS" load qwen/qwen3-coder-next -c 65000 --parallel "$P" -y 2>&1)
  RC=$?
  log "rc=$RC out=$(echo "$OUT" | tr '\n' ' ' | tail -c 400)"
  if [ $RC -eq 0 ]; then
    log "GELADEN (parallel $P). Ist-Zustand danach:"
    "$LMS" ps >>"$LOG" 2>&1
    # Koexistenz-Check: sind gemma-4-31b UND openbiollm noch da?
    STILL=$("$LMS" ps 2>/dev/null | grep -cE "gemma-4-31b-it-mlx|openbiollm")
    log "Koexistenz: $STILL/2 der urspruenglichen MacBook-Modelle noch geladen (2 = gut, <2 = coder-next hat verdraengt)"
    log "ERGEBNIS parallel $P: PASST (rc=0)"
    "$LMS" unload qwen/qwen3-coder-next >>"$LOG" 2>&1
    log "coder-next wieder entladen."
    break
  else
    log "ERGEBNIS parallel $P: PASST NICHT (Guardrail/Fehler)"
  fi
done

# Falls ein urspruengliches MacBook-Modell verdraengt wurde -> nachladen
for M in gemma-4-31b-it-mlx openbiollm-llama3-8b.gguf; do
  if echo "$BEFORE" | python3 -c "import sys,json;d=json.load(sys.stdin);import sys as s;s.exit(0 if any(m.get('modelKey')=='$M' for m in (d if isinstance(d,list) else d.get('models',[]))) else 1)" 2>/dev/null; then
    if ! "$LMS" ps 2>/dev/null | grep -q "$M"; then
      log "WIEDERHERSTELLUNG: $M war weg -> nachladen"
      "$LMS" load "$M" -y >>"$LOG" 2>&1
    fi
  fi
done

"$LMS" link set-preferred-device "$STUDIO_ID" >>"$LOG" 2>&1
log "preferred -> Studio (wiederhergestellt)"
log "--- Ist-Zustand am ENDE ---"
"$LMS" ps >>"$LOG" 2>&1
log "===== Nacht-Test coder-next @ MacBook ENDE ====="

# Selbst-Deregistrierung (Einmal-Test)
launchctl bootout "gui/$(id -u)/de.whitestag.coder-next-test" 2>/dev/null
rm -f "$HOME/Library/LaunchAgents/de.whitestag.coder-next-test.plist"
log "launchd-Job entfernt (Einmal-Test erledigt)."
