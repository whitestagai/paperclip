#!/bin/bash
# Tests fuer den MLX-Fallback-Waechter.
#
# Ersetzt `lms` durch ein Skript-Double (ueber LMS_BIN) und prueft die vier
# Entscheidungen: laden wenn weg, neu laden bei TTL, NICHTS tun wenn beschaeftigt,
# NICHTS tun wenn bereits ohne TTL. Der vierte Fall ist der wichtigste — ein
# Waechter, der bei gesundem Zustand eingreift, entlaedt das Netz im Minutentakt.
set -u
HIER="$(cd "$(dirname "$0")" && pwd)"
WAECHTER="$HIER/mlx-fallback-waechter.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fehler=0

pruefe(){ # name  erwartet  tatsaechlich
  if [ "$2" = "$3" ]; then echo "  ok    $1"
  else echo "  FEHL  $1 — erwartet '$2', war '$3'"; fehler=$((fehler+1)); fi
}

# lms-Double: gibt den in ZUSTAND.json hinterlegten ps-Output aus und
# protokolliert jeden Aufruf in AUFRUFE.
double(){
cat > "$TMP/lms" <<'SH'
#!/bin/bash
echo "$@" >> "$AUFRUFE"
case "$1" in
  ps) cat "$ZUSTAND" ;;
  load|unload) exit 0 ;;
esac
SH
chmod +x "$TMP/lms"
}
double

lauf(){ # $1 = ps-JSON
  echo "$1" > "$TMP/zustand.json"
  : > "$TMP/aufrufe.txt"
  env HOME="$TMP" LMS_BIN="$TMP/lms" ZUSTAND="$TMP/zustand.json" \
      AUFRUFE="$TMP/aufrufe.txt" bash "$WAECHTER" >/dev/null 2>&1
  # welche veraendernden Kommandos kamen?
  # ACHTUNG: grep -c gibt bei 0 Treffern "0" aus UND beendet sich mit 1.
  # Ein "|| echo 0" haengt deshalb eine zweite Null an.
  grep -cE '^(load|unload)' "$TMP/aufrufe.txt" 2>/dev/null || true
}

M='gemma-4-31b-it-mlx'

echo "Tests MLX-Fallback-Waechter"

# 1. Modell fehlt -> genau EIN load, kein unload
n=$(lauf '[]')
pruefe "fehlendes Modell wird geladen" "1" "$n"
pruefe "  dabei kein unload" "0" "$(grep -c '^unload' "$TMP/aufrufe.txt" || true)"

# 2. TTL gesetzt und idle -> unload + load
n=$(lauf "[{\"modelKey\":\"$M\",\"status\":\"idle\",\"ttlMs\":3600000}]")
pruefe "TTL gesetzt: unload und load" "2" "$n"

# 3. beschaeftigt -> NICHTS anfassen (sonst bricht ein Agentenlauf ab)
n=$(lauf "[{\"modelKey\":\"$M\",\"status\":\"generating\",\"ttlMs\":3600000}]")
pruefe "beschaeftigt: kein Eingriff" "0" "$n"
n=$(lauf "[{\"modelKey\":\"$M\",\"status\":\"processingPrompt\",\"ttlMs\":3600000}]")
pruefe "prefill laeuft: kein Eingriff" "0" "$n"

# 4. gesunder Zustand -> NICHTS anfassen
n=$(lauf "[{\"modelKey\":\"$M\",\"status\":\"idle\",\"ttlMs\":null}]")
pruefe "ohne TTL und idle: kein Eingriff" "0" "$n"

# 5. anderes Modell mit TTL darf den Waechter NICHT ausloesen
n=$(lauf "[{\"modelKey\":\"irgendwas-anderes\",\"status\":\"idle\",\"ttlMs\":3600000}]")
pruefe "fremdes Modell: wird als 'fehlt' behandelt, laedt eigenes nach" "1" "$n"

# 6. kaputte Antwort von lms -> kein Eingriff, Fehlerzaehler in der State-Datei
echo 'kein json' > "$TMP/zustand.json"
: > "$TMP/aufrufe.txt"
env HOME="$TMP" LMS_BIN="$TMP/lms" ZUSTAND="$TMP/zustand.json" \
    AUFRUFE="$TMP/aufrufe.txt" bash "$WAECHTER" >/dev/null 2>&1
pruefe "unlesbare Antwort: kein Eingriff" "0" "$(grep -cE '^(load|unload)' "$TMP/aufrufe.txt" || true)"
pruefe "  Fehlerzaehler persistiert" "1" "$(cat "$TMP/.paperclip-logs/mlx-fallback-waechter.state" 2>/dev/null)"

echo
if [ "$fehler" -eq 0 ]; then echo "Alle Tests bestanden."; else echo "$fehler Test(s) fehlgeschlagen."; fi
exit "$fehler"
