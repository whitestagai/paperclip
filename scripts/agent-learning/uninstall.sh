#!/usr/bin/env bash
# Removes symlinks and unloads launchd plists.
# Config, secret and vault content remain.

set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
SCRIPTS_DST="$HOME/.paperclip/scripts"
LAUNCHD_DST="$HOME/Library/LaunchAgents"

echo "Unloading launchd plists"
for plist in "$LAUNCHD_DST"/de.whitestag.agent-learning.*.plist; do
  [[ -e "$plist" ]] || continue
  launchctl unload "$plist" 2>/dev/null || true
  rm -f "$plist"
  echo "Removed $(basename "$plist")"
done

echo "Removing script symlinks"
rm -f "$SCRIPTS_DST/agent-learning-trigger.sh"
for src in "$HERE/lib"/*.sh; do
  rm -f "$SCRIPTS_DST/lib/$(basename "$src")"
done
for src in "$HERE/templates"/*.md "$HERE/templates"/*.yaml; do
  [[ -e "$src" ]] && rm -f "$SCRIPTS_DST/templates/$(basename "$src")"
done

echo
echo "Uninstall complete. Config, secret and vault contents kept."
echo "To also remove config and secret:"
echo "  rm $HOME/.paperclip/instances/default/agent-learning.config.yaml"
echo "  rm $HOME/.paperclip/instances/default/agent-learning.secret"
