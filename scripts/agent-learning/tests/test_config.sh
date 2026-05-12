#!/usr/bin/env bash
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
source "$HERE/../lib/config.sh"

SANDBOX=$(mktemp -d)
trap "rm -rf $SANDBOX" EXIT
cat > "$SANDBOX/agent-learning.secret" <<'EOF'
PAPERCLIP_BOARD_API_KEY=pcp_board_testtesttesttesttesttesttesttesttesttesttest
EOF

SECRET_FILE="$SANDBOX/agent-learning.secret" \
CONFIG_FILE="$HERE/../templates/config.example.yaml" \
  load_config
[[ "$CONFIG_VAULT_ROOT" == "/Volumes/WHITESTAG-ARCHIV/Obsidian/WHITESTAG-Vault" ]] \
  || { echo "FAIL: vault root mismatch ($CONFIG_VAULT_ROOT)"; exit 1; }
[[ "$CONFIG_COMPANIES_WHITESTAG_ID" == "9cebf3cf-efe8-4597-a400-f06488900a87" ]] \
  || { echo "FAIL: whitestag id mismatch"; exit 1; }
[[ -n "${PAPERCLIP_BOARD_API_KEY:-}" ]] \
  || { echo "FAIL: bearer token not exported"; exit 1; }

if SECRET_FILE="$SANDBOX/agent-learning.secret" \
   CONFIG_FILE=/tmp/does-not-exist.yaml load_config 2>/dev/null; then
  echo "FAIL: load_config should fail on missing config file"; exit 1
fi

if SECRET_FILE=/tmp/does-not-exist.secret \
   CONFIG_FILE="$HERE/../templates/config.example.yaml" load_config 2>/dev/null; then
  echo "FAIL: load_config should fail on missing secret file"; exit 1
fi

domains=$(weekday_domains "mon")
[[ "$domains" == *"n8n"* ]] || { echo "FAIL: monday should include n8n ($domains)"; exit 1; }

echo "OK: test_config.sh"
