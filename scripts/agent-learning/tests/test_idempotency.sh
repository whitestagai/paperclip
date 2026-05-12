#!/usr/bin/env bash
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
source "$HERE/../lib/idempotency.sh"

# Mock paperclip_list_issues for the test
paperclip_list_issues() {
  local six_hours_ago
  six_hours_ago=$(date -u -v-6H +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d '6 hours ago' +%Y-%m-%dT%H:%M:%SZ)
  local now_iso
  now_iso=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  cat <<EOF
[
  {"id":"abc","title":"Recherche: n8n — Neuerungen seit 2026-05-05","createdAt":"$six_hours_ago"},
  {"id":"def","title":"Some other issue","createdAt":"$now_iso"}
]
EOF
}

if issue_already_exists_today "dummy-company-id" "Recherche: n8n — Neuerungen seit 2026-05-05"; then
  echo "OK: dedup detected"
else
  echo "FAIL: dedup not detected"; exit 1
fi

if issue_already_exists_today "dummy-company-id" "Recherche: photoshop — Neuerungen seit 2026-05-05"; then
  echo "FAIL: false positive on unique title"; exit 1
else
  echo "OK: unique title accepted"
fi

echo "OK: test_idempotency.sh"
