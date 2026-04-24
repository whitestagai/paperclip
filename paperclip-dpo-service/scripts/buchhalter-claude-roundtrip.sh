#!/usr/bin/env bash
#
# End-to-end test: Simuliert einen typischen Buchhalter-Claude-Call
# durch den DPO (/safe-call) und zeigt die drei Klartext-Stufen aus
# dem Debug-Trail. Läuft lokal, braucht DPO_SHARED_KEY + ANTHROPIC_API_KEY.
#
# Voraussetzungen:
#   - paperclip-dpo-service läuft mit DPO_DEBUG_TRAIL=1
#   - export DPO_SHARED_KEY=$(security find-generic-password -s ai.whitestag.paperclip-dpo-key -w)
#   - export ANTHROPIC_API_KEY=...
#
set -euo pipefail

URL="${1:-http://localhost:4711}"
KEY="${DPO_SHARED_KEY:?DPO_SHARED_KEY required}"
ANTHROPIC_KEY="${ANTHROPIC_API_KEY:?ANTHROPIC_API_KEY required}"
MODEL="${CLAUDE_MODEL:-claude-sonnet-4-6}"
TRAIL_DIR="${DPO_DEBUG_TRAIL_DIR:-$HOME/Library/Logs/paperclip-dpo/debug-trail}"

PROMPT='Bitte erstelle den Rechnungstext für folgende Position:
Kunde: Max Mustermann, Beethovenstraße 12, 10117 Berlin, max.mustermann@example-gmbh.de
IBAN des Kunden für Gutschrift: DE89 3704 0044 0532 0130 00
Leistung: Beratungstag WHITESTAG.AI, April 2026, 1.250,00 EUR netto
Frist: 14 Tage netto.'

echo "==> Trail-Datei(en) vor dem Run:"
ls -la "$TRAIL_DIR"/ 2>/dev/null | tail -n 5 || echo "(Verzeichnis noch leer)"
echo

BODY=$(cat <<EOF
{
  "prompt": $(printf '%s' "$PROMPT" | node -e 'let s="";process.stdin.on("data",c=>s+=c).on("end",()=>process.stdout.write(JSON.stringify(s)))'),
  "targetLlm": "$MODEL",
  "agent": "buchhaltung",
  "tenantId": "whitestag-internal",
  "external": {
    "url": "https://api.anthropic.com/v1/messages",
    "method": "POST",
    "headers": {
      "x-api-key": "$ANTHROPIC_KEY",
      "anthropic-version": "2023-06-01"
    },
    "bodyTemplate": {
      "model": "$MODEL",
      "max_tokens": 1024,
      "messages": [{"role": "user", "content": "{{prompt}}"}]
    },
    "responsePath": "content.0.text"
  }
}
EOF
)

echo "==> POST $URL/safe-call (Buchhalter → $MODEL)"
RESP=$(curl -s -f \
  -H "x-dpo-key: $KEY" \
  -H "content-type: application/json" \
  -d "$BODY" \
  "$URL/safe-call")

echo
echo "==> Finale (reanonymisierte) Antwort aus safe-call:"
echo "$RESP" | node -e 'let s="";process.stdin.on("data",c=>s+=c).on("end",()=>{const r=JSON.parse(s);if(r.blocked){console.error("BLOCKED:",r.reason);process.exit(2)}console.log(r.text)})'

echo
echo "==> Letzte 4 Einträge aus dem Debug-Trail:"
TRAIL_FILE="$TRAIL_DIR/dpo-debug-trail-$(date +%Y-%m-%d).jsonl"
if [[ -f "$TRAIL_FILE" ]]; then
  tail -n 4 "$TRAIL_FILE" | node -e '
    let s="";
    process.stdin.on("data",c=>s+=c).on("end",()=>{
      for (const line of s.trim().split("\n")) {
        try {
          const e = JSON.parse(line);
          const header = `[${e.ts}] ${e.route}/${e.stage} trace=${e.traceId}`;
          console.log(header);
          if (e.text !== undefined) console.log("  " + e.text.replace(/\n/g, "\n  "));
          if (e.blockedReason) console.log("  blocked:", e.blockedReason);
          if (e.errorCode) console.log("  error:", e.errorCode, e.errorMessage || "");
          console.log();
        } catch (err) {
          console.error("parse error:", err.message);
        }
      }
    });
  '
else
  echo "(keine Trail-Datei gefunden: $TRAIL_FILE)"
fi
