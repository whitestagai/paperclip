#!/usr/bin/env bash
# Täglicher inkrementeller VACUUM für die n8n-SQLite-DB.
# Hintergrund: DB ist auto_vacuum=INCREMENTAL. n8n-Pruning löscht laufend alte
# Executions; deren Seiten landen auf der Freelist, werden aber erst durch
# incremental_vacuum (+ WAL-Checkpoint) an macOS zurückgegeben. Verhindert das
# erneute Aufblähen (war einmalig auf 52 GB gewachsen, 2026-06-15 auf 6,8 GB
# vacuumiert). Läuft GEGEN die LIVE-DB ohne n8n-Stop — SQLite/WAL regelt die
# Nebenläufigkeit, busy_timeout wartet auf den Schreib-Lock.
set -uo pipefail

DB="$HOME/.n8n/database.sqlite"
LOG="$HOME/.whitestag-logs/n8n-db-vacuum.log"
mkdir -p "$(dirname "$LOG")"

ts() { date '+%Y-%m-%d %H:%M:%S'; }

if [[ ! -f "$DB" ]]; then
  echo "[$(ts)] FEHLER: DB nicht gefunden: $DB" >>"$LOG"
  exit 1
fi

before=$(stat -f%z "$DB" 2>/dev/null || echo 0)

# busy_timeout: bis zu 2 min auf den Schreib-Lock warten, falls n8n gerade schreibt.
# incremental_vacuum gibt Freelist-Seiten frei; wal_checkpoint(TRUNCATE) materialisiert
# die Verkleinerung der Hauptdatei und kappt das WAL.
out=$(/usr/bin/sqlite3 "$DB" \
  "PRAGMA busy_timeout=120000; PRAGMA incremental_vacuum; PRAGMA wal_checkpoint(TRUNCATE);" 2>&1)
rc=$?

after=$(stat -f%z "$DB" 2>/dev/null || echo 0)
freed_mb=$(( (before - after) / 1024 / 1024 ))

if [[ $rc -eq 0 ]]; then
  echo "[$(ts)] OK  vorher=$((before/1024/1024))MB nachher=$((after/1024/1024))MB freigegeben=${freed_mb}MB" >>"$LOG"
else
  echo "[$(ts)] WARN rc=$rc out='${out}' (nächster Lauf versucht es erneut)" >>"$LOG"
fi
exit 0
