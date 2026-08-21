#!/bin/bash
# Verschluesseltes Backup von ~/.whitestag.env
#
#   backup   (Standard) — verschluesselt ~/.whitestag.env nach $BACKUP_DIR
#   restore  <ziel>     — entschluesselt das Backup (Standardziel: /dev/stdout)
#   verify              — entschluesselt und vergleicht mit ~/.whitestag.env
#
# Die Passphrase liegt in der macOS-Login-Keychain unter dem Dienst
# "whitestag-env-backup" und taucht nie in der Kommandozeile oder auf Platte auf.
# Geht die Keychain verloren, ist das Backup NICHT wiederherstellbar.
set -euo pipefail

ENV_FILE="$HOME/.whitestag.env"
BACKUP_DIR="$HOME/Library/CloudStorage/SynologyDrive-Mac/Claude Code MAC/Mac Systemadministration/Secrets-Backup"
BACKUP_FILE="$BACKUP_DIR/whitestag.env.gpg"
KEYCHAIN_SERVICE="whitestag-env-backup"
KEYCHAIN_ACCOUNT="whitestag-env-backup"

get_pass() {
  security find-generic-password -a "$KEYCHAIN_ACCOUNT" -s "$KEYCHAIN_SERVICE" -w 2>/dev/null \
    || { echo "FEHLER: Keine Passphrase in der Keychain ($KEYCHAIN_SERVICE)." >&2; exit 1; }
}

cmd_backup() {
  [ -f "$ENV_FILE" ] || { echo "FEHLER: $ENV_FILE fehlt." >&2; exit 1; }
  mkdir -p "$BACKUP_DIR"; chmod 700 "$BACKUP_DIR"
  # Vorgaenger behalten, damit ein kaputtes Backup nicht das letzte gute ueberschreibt
  [ -f "$BACKUP_FILE" ] && cp -p "$BACKUP_FILE" "$BACKUP_FILE.prev"
  get_pass | gpg --batch --yes --quiet --passphrase-fd 0 --pinentry-mode loopback \
    --symmetric --cipher-algo AES256 -o "$BACKUP_FILE" "$ENV_FILE"
  chmod 600 "$BACKUP_FILE"
  cmd_verify
  echo "Backup ok: $BACKUP_FILE ($(wc -c <"$BACKUP_FILE" | tr -d ' ') Bytes)"
}

cmd_restore() {
  local target="${1:-/dev/stdout}"
  [ -f "$BACKUP_FILE" ] || { echo "FEHLER: $BACKUP_FILE fehlt." >&2; exit 1; }
  get_pass | gpg --batch --yes --quiet --passphrase-fd 0 --pinentry-mode loopback \
    -d -o "$target" "$BACKUP_FILE"
  [ "$target" != "/dev/stdout" ] && chmod 600 "$target" && echo "Wiederhergestellt nach $target"
}

cmd_verify() {
  local tmp rc
  tmp=$(mktemp)
  get_pass | gpg --batch --yes --quiet --passphrase-fd 0 --pinentry-mode loopback \
    -d -o "$tmp" "$BACKUP_FILE"
  if diff -q "$tmp" "$ENV_FILE" >/dev/null; then
    echo "verify: Backup ist byte-identisch mit $ENV_FILE"; rc=0
  else
    echo "verify: ABWEICHUNG zwischen Backup und $ENV_FILE" >&2; rc=1
  fi
  rm -f "$tmp"
  return "$rc"
}

case "${1:-backup}" in
  backup)  cmd_backup ;;
  restore) shift; cmd_restore "${1:-}" ;;
  verify)  cmd_verify ;;
  *) echo "Aufruf: $0 [backup|restore <ziel>|verify]" >&2; exit 2 ;;
esac
