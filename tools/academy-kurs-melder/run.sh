#!/bin/zsh
# Von launchd über /bin/zsh aufgerufen (nicht übers Executable-Bit —
# SynologyDrive flippt Dateimodi beim Sync).
set -u
cd "$HOME/.paperclip/scripts/academy-kurs-melder" || exit 1
out=$(/usr/bin/python3 melder.py 2>&1); rc=$?
[[ -n "$out" ]] && print -r -- "$(date '+%Y-%m-%d %H:%M:%S') $out"
exit $rc
