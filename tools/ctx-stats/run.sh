#!/usr/bin/env bash
# run.sh — erzeugt die wöchentliche Kontext-Bedarf-Statistik und mailt sie an Walter.
# Rein deterministisch (kein LLM). Aufruf durch die Paperclip-Routine oder manuell.
# Optionen: --dry-run (Mail nur simulieren), --week-days N, --month-days N
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE="$DIR/state"
mkdir -p "$STATE"

DRY=""; WEEK=7; MONTH=30
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY="--dry-run"; shift;;
    --week-days) WEEK="$2"; shift 2;;
    --month-days) MONTH="$2"; shift 2;;
    *) echo "unbekanntes Argument: $1" >&2; exit 1;;
  esac
done

STAMP="$(date +%Y-%m-%d)"
KW="$(date +%V)"
HTML="$STATE/ctx-report-$STAMP.html"
JSON="$STATE/ctx-report-$STAMP.json"

# 1. Report bauen
python3 "$DIR/ctx_report.py" --out-html "$HTML" --out-json "$JSON" \
  --week-days "$WEEK" --month-days "$MONTH" --min-calls 5

# 2. Betreff aus dem JSON ableiten (Anzahl ROT-Modelle)
REDS="$(python3 -c "import json,sys; d=json.load(open('$JSON')); print(sum(1 for r in d['rows'] if r['color']=='#d93025'))")"
if [[ "$REDS" -gt 0 ]]; then
  SUBJECT="Kontext-Bedarf LM-Studio — KW$KW · ⚠ $REDS Modell(e) unter Bedarf"
else
  SUBJECT="Kontext-Bedarf LM-Studio — KW$KW · alle Fenster passend"
fi

# 3. Mailen (from cto@ an ws@ über den n8n-Mailhub)
"$DIR/send_ctx_mail.sh" --subject "$SUBJECT" --html-file "$HTML" $DRY
echo "fertig: $SUBJECT"
