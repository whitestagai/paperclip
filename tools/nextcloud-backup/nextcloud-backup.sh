#!/usr/bin/env bash
# Auswaerts-Sicherung nach Hetzner/Nextcloud: Paperclip-Datenbank + Claude-Code-Ordner.
#
# Usage: nextcloud-backup.sh [--nur-db] [--nur-code] [--nur-vault] [--kein-versand]
#
# WICHTIG: Nicht direkt per launchd starten. macOS verweigert einem launchd-Job
# aus zsh/bash den Zugriff auf CloudStorage (SynologyDrive) UND auf
# SMB-Freigaben — TCC, "Operation not permitted". Der Einstieg laeuft ueber
# `run-nextcloud-backup.js` unter node, das die Berechtigung hat und sie an
# Kindprozesse vererbt. Am 21.08.2026 unter launchd nachgemessen.
#
# Das Repo ist dasselbe wie fuer den Vault (`restic-mac-studio`), die
# Datensaetze werden ueber SCHLAGWORTE getrennt. Jeder Datensatz raeumt selbst
# auf, mit `forget --tag`; deshalb wurde auch backup-vault.sh am 21.08. auf
# `--tag obsidian-vault` umgestellt. Ein `forget` ohne Tagfilter in einem
# geteilten Repo ist ein Minenfeld.
set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- Konfiguration ---------------------------------------------------------
export RESTIC_REPOSITORY="rclone:hetzner-nc:Backups/MacStudio-WHITESTAG/restic-mac-studio"
# Vorbelegung aus der Umgebung nur fuer die Tests; im Betrieb ist sie leer.
export RESTIC_PASSWORD_FILE="${RESTIC_PASSWORD_FILE:-$HOME/.restic/repo.pass}"
export PATH="/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"

RESTIC="/opt/homebrew/bin/restic"
PG_DUMP="/opt/homebrew/bin/pg_dump"
PG_RESTORE="/opt/homebrew/bin/pg_restore"

CODE_DIR="$HOME/Library/CloudStorage/SynologyDrive-Mac/Claude Code MAC"
VAULT_DIR="$HOME/Obsidian/WHITESTAG-Vault"
AUSSCHLUSS="$DIR/ausschluss-claude-code.txt"
ARBEIT="$HOME/.paperclip/backups/nextcloud"
LOG="$HOME/.paperclip/logs/nextcloud-backup.log"
STATUS="$HOME/.paperclip/logs/nextcloud-backup-last.json"
LOCK="$ARBEIT/backup.lock"

TAG_DB="paperclip-db"
TAG_CODE="claude-code"
TAG_VAULT="obsidian-vault"
HOST="MacStudio"

# Restic wartet auf eine fremde Repo-Sperre, statt abzubrechen: das
# Vault-Backup laeuft sonntags 03:30 im selben Repo.
# NC_RETRY_LOCK kuerzt die Wartezeit fuer die Tests — im Betrieb nie gesetzt.
WARTEN="--retry-lock ${NC_RETRY_LOCK:-30m}"

PGHOST="127.0.0.1"; PGPORT="54329"; PGUSER="paperclip"; PGDATABASE="paperclip"
export PGPASSWORD="paperclip"

MAILHUB_URL="http://127.0.0.1:5678/webhook/mailhub/send"
MAILHUB_ENV="$HOME/.paperclip/instances/default/secrets/mailhub.env"
VON="cto@whitestag.ai"; AN="ws@whitestag.ai"

MACH_DB=1; MACH_CODE=1; MACH_VAULT=1; VERSAND=1
# Mehrere --nur-* lassen sich kombinieren: das erste schaltet alles ab und
# waehlt seinen Datensatz, jedes weitere legt einen dazu. Einzeln benutzt
# verhaelt es sich unveraendert.
AUSWAHL=0
waehle() {
  if [ "$AUSWAHL" -eq 0 ]; then
    MACH_DB=0; MACH_CODE=0; MACH_VAULT=0; AUSWAHL=1
  fi
}
while [ $# -gt 0 ]; do
  case "$1" in
    --nur-db)       waehle; MACH_DB=1; shift ;;
    --nur-code)     waehle; MACH_CODE=1; shift ;;
    --nur-vault)    waehle; MACH_VAULT=1; shift ;;
    --kein-versand) VERSAND=0; shift ;;
    # Nur fuer die Tests: ein Wegwerf-Repo in tmp_path statt Hetzner.
    --repo)         export RESTIC_REPOSITORY="$2"; shift 2 ;;
    *) echo "unbekanntes Argument: $1" >&2; exit 2 ;;
  esac
done

mkdir -p "$ARBEIT" "$(dirname "$LOG")"
ts() { date '+%Y-%m-%d %H:%M:%S'; }
log() { echo "$(ts)  $*" | tee -a "$LOG"; }

melde_fehler() {
  local grund="$1"
  log "ABBRUCH: $grund"
  printf '{"stand":"fehler","zeit":"%s","grund":"%s"}\n' \
    "$(ts)" "${grund//\"/\'}" > "$STATUS"
  if [ "$VERSAND" -eq 1 ] && [ -f "$MAILHUB_ENV" ]; then
    local secret
    secret="$(grep '^MAILHUB_SECRET=' "$MAILHUB_ENV" | cut -d= -f2- | tr -d '"' | tr -d '\n')"
    if [ -n "$secret" ]; then
      /usr/bin/python3 - "$MAILHUB_URL" "$secret" "$VON" "$AN" "$grund" "$LOG" <<'PY' 2>&1 | tee -a "$LOG" || true
import json, sys, urllib.request
url, secret, von, an, grund, logpfad = sys.argv[1:7]
try:
    with open(logpfad, encoding="utf-8", errors="replace") as fh:
        schwanz = "".join(fh.readlines()[-25:])
except OSError:
    schwanz = "(Log nicht lesbar)"
betreff = "FEHLER: Auswaerts-Sicherung (Nextcloud)"
html = (f"<p>Die Sicherung nach Hetzner/Nextcloud ist abgebrochen.</p>"
        f"<p><b>Grund:</b> {grund}</p>"
        f"<pre style='font-size:12px;background:#f1f3f4;padding:8px'>{schwanz}</pre>"
        f"<p style='color:#5f6368;font-size:12px'>Bereits vorhandene Snapshots "
        f"sind unveraendert — es wurde nichts geloescht.</p>")
daten = json.dumps({"from": von, "to": an, "subject": betreff,
                    "text": betreff + ": " + grund, "html": html}).encode()
req = urllib.request.Request(url, data=daten,
    headers={"Content-Type": "application/json", "X-Mailhub-Secret": secret})
try:
    with urllib.request.urlopen(req, timeout=30) as a:
        print(f"Fehlermail an {an} gesendet (HTTP {a.status}).")
except Exception as exc:
    print("Fehlermail konnte NICHT gesendet werden:", exc)
PY
    fi
  fi
  rm -f "$LOCK"
  exit 1
}

# Gescheiterter EINZELNER Datensatz: merken und weitermachen.
#
# Bis zum 16.09.2026 beendete jeder Fehler den ganzen Lauf. An dem Tag
# blieb der Claude-Code-Ordner an sieben unlesbaren Verzeichnissen haengen —
# und weil danach `exit 1` kam, wurde der Obsidian-Vault an diesem Tag
# ueberhaupt nicht ausgelagert. Aus einem Teilausfall wurde so ein groesserer,
# und die Mail nannte nur den Code-Ordner, nicht den fehlenden Vault.
#
# Ein nicht lesbarer Datensatz sagt nichts darueber, ob der naechste sicherbar
# ist. Also: jeden einzeln versuchen, alle Fehler sammeln, am Ende zusammen
# melden. `melde_fehler` bleibt fuer das, was den Lauf wirklich unmoeglich
# macht (fehlendes restic, belegte Sperre).
#
# Bewusst Zaehler + Text statt eines Arrays: /bin/bash auf macOS ist 3.2, und
# dort stolpert `${#arr[@]}` bei leerem Array ueber `set -u`.
FEHLER_ANZAHL=0
FEHLER_TEXT=""
merke_fehler() {
  log "FEHLER: $1"
  FEHLER_ANZAHL=$((FEHLER_ANZAHL + 1))
  if [ -z "$FEHLER_TEXT" ]; then FEHLER_TEXT="$1"; else FEHLER_TEXT="$FEHLER_TEXT; $1"; fi
}

# --- Sperre ---------------------------------------------------------------
if [ -e "$LOCK" ]; then
  ALT="$(cat "$LOCK" 2>/dev/null || echo '?')"
  if kill -0 "$ALT" 2>/dev/null; then
    log "Laeuft bereits (PID $ALT) — Abbruch ohne Fehler."
    exit 0
  fi
  log "Verwaiste Sperre von PID $ALT entfernt."
  rm -f "$LOCK"
fi
echo $$ > "$LOCK"
trap 'rm -f "$LOCK"' EXIT

log "===== Start Auswaerts-Sicherung"

[ -x "$RESTIC" ] || melde_fehler "restic nicht gefunden: $RESTIC"

# --- 1. Datenbank ----------------------------------------------------------
sichere_datenbank() {
  DUMP="$ARBEIT/paperclip.dump"
  # -Z0 = UNKOMPRIMIERT, und das ist der springende Punkt: restic kann einen
  # rohen Dump zerhacken und selbst komprimieren. Gemessen am 21.08.2026 ist
  # er im Repo sogar KLEINER als der gzip-komprimierte (287 statt 366 MB) und
  # dedupliziert am Folgetag siebenmal besser (8,4 statt 57,5 MB Zuwachs).
  # Bei gzip verwuerfelt jede Aenderung den Bytestrom dahinter.
  log "Erzeuge rohen Dump (-Z0) ..."
  if ! "$PG_DUMP" -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" \
        -Fc -Z0 -f "$DUMP" 2>>"$LOG"; then
    merke_fehler "pg_dump fehlgeschlagen"; return 1
  fi
  log "Dump erstellt: $(du -h "$DUMP" | cut -f1)"

  # Vollstaendig lesen, nicht nur das Inhaltsverzeichnis: das steht am Anfang
  # der Datei, ein abgeschnittener Dump besteht `--list` sonst anstandslos.
  if ! "$PG_RESTORE" -f /dev/null "$DUMP" >/dev/null 2>>"$LOG"; then
    merke_fehler "Dump ist unbrauchbar (abgeschnitten?) — nichts hochgeladen"
    return 1
  fi
  log "Dump verifiziert."

  if ! "$RESTIC" backup "$DUMP" --tag "$TAG_DB" --host "$HOST" $WARTEN \
        >>"$LOG" 2>&1; then
    merke_fehler "restic-Sicherung der Datenbank fehlgeschlagen"; return 1
  fi
  log "Datenbank gesichert (Schlagwort $TAG_DB)."
  rm -f "$DUMP"
}
[ "$MACH_DB" -eq 1 ] && sichere_datenbank

# --- 2. Claude-Code-Ordner -------------------------------------------------
sichere_code() {
  [ -d "$CODE_DIR" ] || { merke_fehler "Ordner nicht erreichbar: $CODE_DIR"; return 1; }
  [ -f "$AUSSCHLUSS" ] || { merke_fehler "Ausschlussliste fehlt: $AUSSCHLUSS"; return 1; }
  log "Sichere $CODE_DIR ..."
  if ! "$RESTIC" backup "$CODE_DIR" --tag "$TAG_CODE" --host "$HOST" \
        --exclude-file "$AUSSCHLUSS" $WARTEN >>"$LOG" 2>&1; then
    merke_fehler "restic-Sicherung des Claude-Code-Ordners fehlgeschlagen"
    return 1
  fi
  log "Claude-Code-Ordner gesichert (Schlagwort $TAG_CODE)."
}
[ "$MACH_CODE" -eq 1 ] && sichere_code

# --- 3. Obsidian-Vault -----------------------------------------------------
# Seit 22.08.2026 TAEGLICH statt sonntags. Vorher lag zwischen zwei Sonntagen
# im schlimmsten Fall eine Woche Arbeit nur auf dem Mac und der NAS — beide im
# selben Gebaeude. Uebernommen aus ~/.restic/backup-vault.sh; Schlagworte und
# Host bleiben gleich, damit die Snapshot-Historie ab Mai 2026 fortlaeuft.
#
# Ausschluesse wie beim NAS-Spiegel: der Vault enthaelt Code-Projekte mit
# `.venv` (0,7 GB, darunter ein 572-MB-Sprachmodell), `__pycache__` und
# `node_modules` — ein Viertel aller Dateien, alles wiederherstellbar.
# `.git` bleibt drin.
sichere_vault() {
  [ -d "$VAULT_DIR" ] || { merke_fehler "Vault nicht erreichbar: $VAULT_DIR"; return 1; }
  log "Sichere $VAULT_DIR ..."
  if ! "$RESTIC" backup "$VAULT_DIR" --tag "$TAG_VAULT" --tag automated \
        --host "$HOST" $WARTEN \
        --exclude ".trash" \
        --exclude ".obsidian/workspace*.json" \
        --exclude ".obsidian/cache" \
        --exclude ".DS_Store" \
        --exclude "*/.DS_Store" \
        --exclude ".venv" \
        --exclude "venv" \
        --exclude "node_modules" \
        --exclude "__pycache__" \
        --exclude "*.pyc" \
        >>"$LOG" 2>&1; then
    merke_fehler "restic-Sicherung des Vaults fehlgeschlagen"; return 1
  fi
  log "Vault gesichert (Schlagwort $TAG_VAULT)."
}
[ "$MACH_VAULT" -eq 1 ] && sichere_vault

# --- 4. Aufbewahrung -------------------------------------------------------
# Verwaiste Sperren zuerst wegraeumen. Am 16.09.2026 lagen vier davon im
# Repo, die aelteste seit 27 Stunden von einem laengst toten Prozess. Jedes
# `forget` wartete daraufhin seine vollen 30 Minuten und gab auf — die
# Aufbewahrung lief zwei Tage lang nicht, ohne dass es jemand sah.
#
# `unlock` ohne `--remove-all` entfernt ausschliesslich VERWAISTE Sperren
# (aelter als 30 Minuten und ohne lebenden Besitzer). Eine echte, laufende
# Operation haelt ihre Sperre frisch und bleibt unangetastet — wichtig, weil
# die monatliche Repo-Pruefung im selben Repo arbeitet.
if ! "$RESTIC" unlock >>"$LOG" 2>&1; then
  log "WARNUNG: unlock fehlgeschlagen — Aufbewahrung koennte blockieren."
fi

# Je Schlagwort getrennt. NIEMALS ohne --tag: im selben Repo liegt der Vault.
for T in "$TAG_DB" "$TAG_CODE" "$TAG_VAULT"; do
  if ! "$RESTIC" forget --tag "$T" --keep-daily 14 --keep-weekly 8 \
        --keep-monthly 12 $WARTEN >>"$LOG" 2>&1; then
    # Frueher nur eine Logzeile. Genau deshalb fiel zwei Tage lang nicht auf,
    # dass nichts mehr aufgeraeumt wurde: der Lauf meldete weiter "ok". Eine
    # Sicherung, die sich nicht mehr aufraeumt, waechst still, bis der Tarif
    # voll ist — das gehoert in den Bericht, nicht in eine Logzeile.
    merke_fehler "Aufbewahrung fuer $T fehlgeschlagen (Sicherung selbst ist durch)"
  fi
done

# prune einmal am Ende fuer das ganze Repo.
if ! "$RESTIC" prune $WARTEN >>"$LOG" 2>&1; then
  merke_fehler "prune fehlgeschlagen (Sicherungen sind unversehrt)"
fi

# --- 5. Stand --------------------------------------------------------------
N_DB="$("$RESTIC" snapshots --tag "$TAG_DB" --json 2>/dev/null | /usr/bin/python3 -c 'import json,sys;print(len(json.load(sys.stdin)))' 2>/dev/null || echo 0)"
N_CODE="$("$RESTIC" snapshots --tag "$TAG_CODE" --json 2>/dev/null | /usr/bin/python3 -c 'import json,sys;print(len(json.load(sys.stdin)))' 2>/dev/null || echo 0)"
# Erst jetzt urteilen — nachdem JEDER Datensatz seine Chance hatte. Gab es
# unterwegs Fehler, werden sie hier gesammelt gemeldet: eine Mail mit allen
# Punkten statt einer, die beim ersten stehenbleibt und den Rest verschweigt.
if [ "$FEHLER_ANZAHL" -gt 0 ]; then
  melde_fehler "$FEHLER_TEXT"
fi

printf '{"stand":"ok","zeit":"%s","snapshots_db":%s,"snapshots_code":%s}\n' \
  "$(ts)" "$N_DB" "$N_CODE" > "$STATUS"
log "===== Fertig. Snapshots: DB $N_DB, Code $N_CODE."
