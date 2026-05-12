#!/usr/bin/env bash
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
source "$HERE/../lib/slug.sh"

assert_eq() { [[ "$1" == "$2" ]] || { echo "FAIL: expected '$2' got '$1'"; exit 1; }; }

assert_eq "$(slug_from_name 'Online-Recherche')"   "online-recherche"
assert_eq "$(slug_from_name 'Vault-Maintainer')"   "vault-maintainer"
assert_eq "$(slug_from_name 'Bild & Video')"       "bild-und-video"
assert_eq "$(slug_from_name 'CTO')"                "cto"
assert_eq "$(slug_from_name '  Online   Recherche  ')" "online-recherche"
assert_eq "$(slug_from_name 'Müll-Räumer')"        "muell-raeumer"

echo "OK: test_slug.sh"
