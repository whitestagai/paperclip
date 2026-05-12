#!/usr/bin/env bash
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
source "$HERE/../lib/decay.sh"

SANDBOX=$(mktemp -d)
trap "rm -rf $SANDBOX" EXIT
mkdir -p "$SANDBOX/Skill-Wissen/n8n/_archive"

echo "stale" > "$SANDBOX/Skill-Wissen/n8n/stale.md"
touch -t "$(date -v-200d +%Y%m%d0000 2>/dev/null || date -d '200 days ago' +%Y%m%d0000)" \
  "$SANDBOX/Skill-Wissen/n8n/stale.md"
echo "fresh" > "$SANDBOX/Skill-Wissen/n8n/fresh.md"
echo "## index" > "$SANDBOX/Skill-Wissen/n8n/MEMORY.md"
touch -t "$(date -v-300d +%Y%m%d0000 2>/dev/null || date -d '300 days ago' +%Y%m%d0000)" \
  "$SANDBOX/Skill-Wissen/n8n/MEMORY.md"

decay_archive_dir "$SANDBOX/Skill-Wissen/n8n" 180

[[ -f "$SANDBOX/Skill-Wissen/n8n/_archive/stale.md" ]] \
  || { echo "FAIL: stale.md not archived"; ls -la "$SANDBOX/Skill-Wissen/n8n/"; exit 1; }
[[ -f "$SANDBOX/Skill-Wissen/n8n/fresh.md" ]] \
  || { echo "FAIL: fresh.md disappeared"; exit 1; }
[[ ! -f "$SANDBOX/Skill-Wissen/n8n/stale.md" ]] \
  || { echo "FAIL: stale.md still in active dir"; exit 1; }
[[ -f "$SANDBOX/Skill-Wissen/n8n/MEMORY.md" ]] \
  || { echo "FAIL: MEMORY.md got archived (should be skipped)"; exit 1; }

echo "OK: test_decay.sh"
