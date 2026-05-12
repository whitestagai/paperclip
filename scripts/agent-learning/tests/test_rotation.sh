#!/usr/bin/env bash
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
source "$HERE/../lib/rotation.sh"

assert_eq() { [[ "$1" == "$2" ]] || { echo "FAIL: expected '$2' got '$1'"; exit 1; }; }

assert_eq "$(weekday_short 1)" "mon"
assert_eq "$(weekday_short 5)" "fri"
assert_eq "$(weekday_short 7)" "sun"

TODAY=$(weekday_short_today)
case "$TODAY" in
  mon|tue|wed|thu|fri|sat|sun) ;;
  *) echo "FAIL: unexpected weekday $TODAY"; exit 1 ;;
esac

echo "OK: test_rotation.sh"
