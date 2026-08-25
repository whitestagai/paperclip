#!/usr/bin/env bash
# Haelt eine SMB-Freigabe des WHITESTAG-NAS eingehaengt.
#
# Usage: nas-mount.sh --freigabe <name> [--probe <unterordner>] [--frist <s>]
#                     [--mountpoint <pfad>] [--kein-log]
#                     [--mount-bin <pfad>] [--diskutil-bin <pfad>]
#                     [--osascript-bin <pfad>]
#
# Loest ~/.claude/scripts/mount-whitestag-archiv.sh ab. Diese Fassung
# existiert wegen zwei Fallen, an denen die Vorgaengerin gescheitert ist —
# beide sind am 25.08.2026 unter launchd nachgemessen:
#
# 1. LEBENDPRUEFUNG MIT `ls`. Unter launchd ist das Auflisten eines
#    Netzlaufwerks TCC-gesperrt ("Operation not permitted") — fuer bash wie
#    fuer zsh, auch wenn der Mount sichtbar und gesund ist. `ls` schlaegt dort
#    IMMER fehl. Die Vorgaengerin hat daraus "nicht eingehaengt" geschlossen
#    und alle 5 Minuten zwangsweise ausgehaengt und neu gemountet: 287-mal am
#    Tag, monatelang, mitten in laufende Sicherungen hinein. Der Vault-Spiegel
#    vom 24.08.2026 ist so mit "rsync error code 11" an fast jedem Ordner
#    gescheitert. `test -d` (stat) ist NICHT gesperrt und beweist denselben
#    Punkt — das ist der Unterschied zwischen dieser Fassung und der alten.
#
# 2. UNBEGRENZTES WARTEN. Auf einer toten SMB-Verbindung blockieren
#    `diskutil unmount` und `osascript mount volume` beliebig lange. launchd
#    startet bei StartInterval keine zweite Instanz, solange die erste noch
#    laeuft — ein einziger Haenger legt den Waechter also still. Am 24.08.2026
#    stand er so 28 Stunden, in denen NICHTS mehr auf die NAS gesichert wurde
#    und niemand nachgemountet hat. Jeder Aufruf nach draussen laeuft deshalb
#    unter einer Frist und wird bei Ablauf ZURUECKGELASSEN statt abgewartet:
#    ein Prozess, der auf totem SMB haengt, laesst sich oft nicht einmal mit
#    SIGKILL beenden. Lieber ein verwaister Prozess als ein toter Waechter.
#
# Kein Mailversand von hier: bei 288 Laeufen am Tag waere jede Stoerung eine
# Mailflut. Der Zustand landet in einer Statusdatei, alarmiert wird ueber
# `backup-waechter` (taeglich 09:00) und die Sicherungsskripte selbst.
set -uo pipefail

SERVER="${NAS_SERVER:-ws-cloud@WHITESTAG-NAS._smb._tcp.local}"
FREIGABE=""
PROBE=""
MOUNTPOINT=""
# 30 s reichen fuer jeden gesunden Mount ueber Gigabit und liegen deutlich
# unter dem 300-s-Takt des launchd-Jobs: zwei Laeufe koennen sich nie
# ueberholen, selbst wenn beide Aufrufe in die Frist laufen.
FRIST=30
LOG="$HOME/.paperclip/logs/nas-mount.log"
STATUS_DIR="$HOME/.paperclip/logs"

MOUNT_BIN="/sbin/mount"
DISKUTIL_BIN="/usr/sbin/diskutil"
OSASCRIPT_BIN="/usr/bin/osascript"

while [ $# -gt 0 ]; do
  case "$1" in
    --freigabe)      FREIGABE="$2"; shift 2 ;;
    --probe)         PROBE="$2"; shift 2 ;;
    --mountpoint)    MOUNTPOINT="$2"; shift 2 ;;
    --frist)         FRIST="$2"; shift 2 ;;
    --mount-bin)     MOUNT_BIN="$2"; shift 2 ;;
    --diskutil-bin)  DISKUTIL_BIN="$2"; shift 2 ;;
    --osascript-bin) OSASCRIPT_BIN="$2"; shift 2 ;;
    *) echo "unbekanntes Argument: $1" >&2; exit 2 ;;
  esac
done

if [ -z "$FREIGABE" ]; then
  echo "--freigabe fehlt" >&2
  exit 2
fi

MOUNTPOINT="${MOUNTPOINT:-/Volumes/$FREIGABE}"
URL="smb://$SERVER/$FREIGABE"
STATUS="$STATUS_DIR/nas-mount-$FREIGABE-last.json"

mkdir -p "$(dirname "$LOG")" "$STATUS_DIR"
ts() { date '+%Y-%m-%d %H:%M:%S'; }

# Ausgabe der aufgerufenen Werkzeuge auffangen statt nach /dev/null. Die
# Vorgaengerin warf sie weg und meldete nur "FEHLER - Mount fehlgeschlagen";
# warum, stand nirgends. Genau daran hing die Fehlersuche am 25.08.2026.
AUSGABE="$(mktemp -t nas-mount)"
trap 'rm -f "$AUSGABE"' EXIT

# `MOUNT_STILL` setzt die Testsuite (conftest.py). Ohne diese Bremse landen
# Testlaeufe im echten Log und sehen beim Nachsehen wie Vorfaelle aus —
# dieselbe Falle wie bei vault-nas-sync und backup-waechter.
log() {
  if [ -n "${MOUNT_STILL:-}" ]; then echo "$(ts)  [$FREIGABE] $*"; return; fi
  echo "$(ts)  [$FREIGABE] $*" | tee -a "$LOG"
}

# Nur ZUSTANDSWECHSEL protokollieren. Die Vorgaengerin schrieb bei jedem Lauf
# eine Zeile; das Log war mit 900 KB Rauschen so unbrauchbar, dass der echte
# Ausfall darin nicht auffiel.
letzter_zustand() {
  [ -f "$STATUS" ] || return 0
  sed -n 's/.*"stand":"\([a-z]*\)".*/\1/p' "$STATUS"
}

setze_zustand() {
  local stand="$1" grund="${2:-}"
  local vorher; vorher="$(letzter_zustand)"
  printf '{"stand":"%s","zeit":"%s","mountpoint":"%s","grund":"%s"}\n' \
    "$stand" "$(ts)" "$MOUNTPOINT" "${grund//\"/\'}" > "$STATUS"
  [ "$stand" = "$vorher" ] && return 0
  case "$stand" in
    ok)     log "wieder eingehaengt: $MOUNTPOINT" ;;
    fehler) log "NICHT eingehaengt: $grund" ;;
  esac
}

# mit_frist <sekunden> <befehl...> -> Rueckgabewert des Befehls, 124 bei Ablauf.
#
# Bewusst KEIN `wait` auf einen ueberfaelligen Prozess: haengt er im Kern auf
# totem SMB, ueberlebt er auch SIGKILL, und `wait` wuerde den Waechter mit in
# den Abgrund ziehen — genau der 28-Stunden-Ausfall vom 24.08.2026. Der
# Prozess wird dann zurueckgelassen; der naechste Lauf in 5 Minuten ist davon
# unberuehrt.
mit_frist() {
  local frist="$1"; shift
  "$@" >>"$AUSGABE" 2>&1 &
  local pid=$! i=0
  while kill -0 "$pid" 2>/dev/null; do
    if [ "$i" -ge "$frist" ]; then
      kill -9 "$pid" 2>/dev/null
      return 124
    fi
    sleep 1
    i=$((i + 1))
  done
  wait "$pid"
}

in_mount_tabelle() {
  "$MOUNT_BIN" 2>/dev/null | grep -q " $MOUNTPOINT "
}

# Eingehaengt UND benutzbar. Beides zu pruefen ist der Kern: die Mount-Tabelle
# behaelt eine Leiche auch dann, wenn die Verbindung laengst tot ist, und die
# Vorgaengerin meldete genau deshalb "OK - gemountet", waehrend nichts ging.
#
#   0 = gesund
#   1 = nicht eingehaengt oder tot  -> aushaengen und neu mounten
#   2 = Freigabe lebt, aber der Sondenpfad fehlt
#
# Der dritte Fall ist mit Absicht KEIN Mount-Anlass: ein umbenannter oder
# geloeschter Sondenordner ist ein Konfigurationsfehler. Wer ihn wie einen
# toten Mount behandelt, haengt alle 5 Minuten eine gesunde Freigabe aus —
# und stellt damit genau den Schaden wieder her, gegen den diese Fassung
# geschrieben ist.
zustand_pruefen() {
  in_mount_tabelle || return 1
  mit_frist "$FRIST" /bin/test -d "$MOUNTPOINT" || return 1
  [ -n "$PROBE" ] || return 0
  mit_frist "$FRIST" /bin/test -d "$MOUNTPOINT/$PROBE" && return 0
  return 2
}

zustand_pruefen
zustand=$?

if [ "$zustand" -eq 0 ]; then
  setze_zustand ok
  exit 0
fi

if [ "$zustand" -eq 2 ]; then
  setze_zustand fehler \
    "Sondenpfad fehlt: $MOUNTPOINT/$PROBE — Freigabe lebt, Konfiguration pruefen"
  exit 1
fi

# Eine Leiche in der Mount-Tabelle blockiert den Mountpoint und muss weg.
# Nur dann aushaengen — die Vorgaengerin tat es bei JEDEM Lauf.
if in_mount_tabelle; then
  log "Mountpoint belegt, aber nicht erreichbar — haenge aus"
  mit_frist "$FRIST" "$DISKUTIL_BIN" unmount force "$MOUNTPOINT"
  if [ $? -eq 124 ]; then
    setze_zustand fehler "Aushaengen ueberschritt die Frist von ${FRIST}s"
    exit 1
  fi
fi

# Der Finder-Automounter nimmt das Passwort aus dem Schluesselbund und legt
# den Mountpoint selbst an.
mit_frist "$FRIST" "$OSASCRIPT_BIN" -e "mount volume \"$URL\""
rc=$?
if [ "$rc" -eq 124 ]; then
  setze_zustand fehler "Mount-Aufruf ueberschritt die Frist von ${FRIST}s"
  exit 1
fi

# Nach dem Mount noch einmal VOLL pruefen, nicht nur die Mount-Tabelle: sonst
# gilt eine Leiche wieder als Erfolg.
if zustand_pruefen; then
  setze_zustand ok
  exit 0
fi

MELDUNG="$(tr '\n' ' ' < "$AUSGABE" | cut -c1-200)"
setze_zustand fehler "Mount fehlgeschlagen (rc=$rc, $URL) ${MELDUNG}"
exit 1
