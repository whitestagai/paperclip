#!/usr/bin/env bash
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
source "$HERE/../lib/slug.sh"

SANDBOX=$(mktemp -d)
trap "rm -rf $SANDBOX" EXIT
mkdir -p "$SANDBOX/Paperclip/Agenten"

WHITESTAG_AGENTS='[
  {"id":"aaa","name":"Online-Recherche"},
  {"id":"bbb","name":"Vault-Maintainer"},
  {"id":"ccc","name":"Bild & Video"}
]'
HEALTH_AGENTS='[
  {"id":"ddd","name":"CHO"},
  {"id":"eee","name":"Datenauswerter"}
]'

write_slug_index "$SANDBOX/Paperclip/Agenten/_index.md" \
  "whitestag" "$WHITESTAG_AGENTS" \
  "health" "$HEALTH_AGENTS"

grep -q "online-recherche.*aaa.*whitestag" "$SANDBOX/Paperclip/Agenten/_index.md" \
  || { echo "FAIL: online-recherche entry missing"; cat "$SANDBOX/Paperclip/Agenten/_index.md"; exit 1; }
grep -q "bild-und-video.*ccc" "$SANDBOX/Paperclip/Agenten/_index.md" \
  || { echo "FAIL: bild-und-video entry missing"; exit 1; }
grep -q "datenauswerter.*eee.*health" "$SANDBOX/Paperclip/Agenten/_index.md" \
  || { echo "FAIL: datenauswerter entry missing"; exit 1; }

echo "OK: test_slug_index.sh"
