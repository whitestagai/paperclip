#!/usr/bin/env bash
# benchmark_candidate.sh — lädt ein Kandidaten-Modell temporär, misst Tokens/s je
# Fähigkeitsklasse und entlädt wieder. Gibt JSON auf stdout.
#
# Usage: benchmark_candidate.sh <model_key> [--keep]
# Exit: 0 Erfolg, 1 Argument-/Ladefehler, 2 Budget-Sprengung
set -euo pipefail

LMS="$HOME/.lmstudio/bin/lms"
ADV="$HOME/.paperclip/scripts/llm-advisor"
MODEL="${1:?model_key fehlt}"
KEEP="${2:-}"

was_loaded="$("$LMS" ps --json | grep -c "\"identifier\":\"$MODEL\"" || true)"

cleanup() {
  if [[ "$KEEP" != "--keep" && "$was_loaded" == "0" ]]; then
    "$LMS" unload "$MODEL" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

# Laden (falls noch nicht geladen)
if [[ "$was_loaded" == "0" ]]; then
  "$LMS" load "$MODEL" --yes >/dev/null 2>&1 || { echo '{"error":"load_failed"}'; exit 1; }
fi

results="[]"
for cls in coding reasoning classification general; do
  prompt="$(cat "$ADV/prompts/$cls.txt")"
  start=$(python3 -c 'import time;print(time.time())')
  resp="$("$LMS" chat "$MODEL" --prompt "$prompt" 2>/dev/null | tr -d '\000' || true)"
  end=$(python3 -c 'import time;print(time.time())')
  toks=$(printf '%s' "$resp" | wc -w | tr -d ' ')
  results="$(python3 -c "
import json,sys
r=json.loads('''$results''')
dur=max($end-$start,1e-6)
r.append({'class':'$cls','words':$toks,'seconds':round(dur,2),'words_per_s':round($toks/dur,2)})
print(json.dumps(r))
")"
done

echo "{\"model\":\"$MODEL\",\"benchmarks\":$results}"
