#!/bin/bash
# ============================================================
# iCloud Health-Export "keep-warm"
# ------------------------------------------------------------
# Grund: macOS "Optimize Mac Storage" (com.apple.bird
# optimize-storage=1) lagert einzelne Export-JSONs in die iCloud
# aus ("dataless"). Der n8n-Workflow "health-ingest V9"
# (0wu9MeDHTxTgIwmo) liest per Glob ALLE Dateien; ein einziges
# dataless-File -> read() liefert errno 11 (EAGAIN) ->
# "Unknown system error -11" -> ganzer Workflow errort (und hat
# schon einmal n8n komplett wedged). Siehe WHI-2597 / WHI-2595.
#
# Dieser Job re-materialisiert regelmaessig alle ausgelagerten
# Dateien, damit der Read-Node nie wieder auf ein dataless-File
# stoesst. Laeuft via launchd de.whitestag.icloud-health-keepwarm.
# Bewusst /bin/bash-3.2-kompatibel (kein mapfile).
# ============================================================
set -uo pipefail

DIR="/Users/walterschoenenbroecher.de/Library/Mobile Documents/iCloud~com~ifunography~HealthExport/Documents/Daily Export Gesundheit"
LOG="$HOME/.whitestag-logs/icloud-health-keepwarm.log"
mkdir -p "$(dirname "$LOG")"

ts() { date '+%Y-%m-%d %H:%M:%S'; }
log() { echo "[$(ts)] $*" >>"$LOG"; }

if [ ! -d "$DIR" ]; then
  log "FEHLER: Verzeichnis fehlt: $DIR"
  exit 0
fi

# Ausgelagerte (dataless) Dateien einsammeln. Der Ordnername enthaelt
# LEERZEICHEN ("Daily Export Gesundheit") -> NICHT die ls-Ausgabe per
# awk $NF parsen (zerbricht am Space). Stattdessen den Glob direkt
# iterieren und je Datei einzeln das "dataless"-Flag pruefen.
tmp="$(mktemp)"
for f in "$DIR"/*.json; do
  [ -e "$f" ] || continue
  if ls -ldO "$f" 2>/dev/null | grep -q dataless; then
    printf '%s\n' "$f" >>"$tmp"
  fi
done

count="$(wc -l <"$tmp" | tr -d ' ')"
if [ "$count" -eq 0 ]; then
  # Alles warm — kein Log-Spam alle 15 Min.
  rm -f "$tmp"
  exit 0
fi

log "dataless gefunden: $count Datei(en) -> materialisiere"
ok=0; fail=0
while IFS= read -r f; do
  [ -n "$f" ] || continue
  # brctl download ist ASYNCHRON -> anstossen, dann bis zu 30s auf
  # Materialisierung pollen (direktes cat wuerde in die laufende
  # Ladung rennen: errno 11 / EAGAIN).
  brctl download "$f" >/dev/null 2>&1 || true
  warmed=0
  for _ in $(seq 1 30); do
    if ! ls -lO "$f" 2>/dev/null | grep -q dataless; then warmed=1; break; fi
    sleep 1
  done
  if [ "$warmed" -eq 1 ] && cat "$f" >/dev/null 2>&1; then
    ok=$((ok+1))
  else
    fail=$((fail+1))
    log "  WARN: konnte nicht materialisieren: $(basename "$f")"
  fi
done <"$tmp"
rm -f "$tmp"
log "materialisiert OK=$ok FEHLER=$fail"

remain="$(ls -lO "$DIR"/*.json 2>/dev/null | grep -c dataless | tr -d ' ')"
log "verbleibend dataless nach Lauf: $remain"
