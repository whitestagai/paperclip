#!/usr/bin/env bash
# Symlinks scripts to ~/.paperclip/scripts/, copies config template (if missing),
# installs launchd plists. Does NOT create the Board-API-Key secret — that
# must be done separately via the CLI-auth-challenge flow (plan Task 0 Step 3).

set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)

SCRIPTS_DST="$HOME/.paperclip/scripts"
CONFIG_DST="$HOME/.paperclip/instances/default/agent-learning.config.yaml"
SECRET_DST="$HOME/.paperclip/instances/default/agent-learning.secret"
LAUNCHD_DST="$HOME/Library/LaunchAgents"

echo "Installing agent-learning scripts to $SCRIPTS_DST"
mkdir -p "$SCRIPTS_DST/lib" "$SCRIPTS_DST/templates"

ln -sf "$HERE/agent-learning-trigger.sh" "$SCRIPTS_DST/agent-learning-trigger.sh"

for src in "$HERE/lib"/*.sh; do
  ln -sf "$src" "$SCRIPTS_DST/lib/$(basename "$src")"
done
for src in "$HERE/templates"/*.md "$HERE/templates"/*.yaml; do
  [[ -e "$src" ]] && ln -sf "$src" "$SCRIPTS_DST/templates/$(basename "$src")"
done

if [[ ! -f "$CONFIG_DST" ]]; then
  cp "$HERE/templates/config.example.yaml" "$CONFIG_DST"
  echo "Copied config template to $CONFIG_DST"
else
  echo "Config already exists at $CONFIG_DST — not overwriting."
fi

if [[ ! -f "$SECRET_DST" ]]; then
  echo
  echo "WARNING: Board-API-Key secret missing at $SECRET_DST"
  echo "Create one before running the trigger script. See plan Task 0 Step 3."
  echo
fi

echo "Installing launchd plists to $LAUNCHD_DST"
mkdir -p "$LAUNCHD_DST"
for plist in "$HERE/launchd"/*.plist; do
  label=$(basename "$plist" .plist)
  dst="$LAUNCHD_DST/$(basename "$plist")"

  sed "s|\$HOME|$HOME|g" "$plist" > "$dst"

  launchctl unload "$dst" 2>/dev/null || true
  launchctl load -w "$dst"
  echo "Loaded $label"
done

echo
echo "Install complete. Verify:"
echo "  launchctl list | grep agent-learning"
echo "  ~/.paperclip/scripts/agent-learning-trigger.sh knowledge --dry-run"
