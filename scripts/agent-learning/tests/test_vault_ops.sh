#!/usr/bin/env bash
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
source "$HERE/../lib/vault_ops.sh"

SANDBOX=$(mktemp -d)
trap "rm -rf $SANDBOX" EXIT
export CONFIG_VAULT_ROOT="$SANDBOX"
export CONFIG_VAULT_KNOWLEDGE_DIR="Paperclip/Skill-Wissen"
export CONFIG_VAULT_AGENTS_DIR="Paperclip/Agenten"

vault_ensure_knowledge_domain "n8n" "n8n Workflow Automation"
[[ -f "$SANDBOX/Paperclip/Skill-Wissen/n8n/MEMORY.md" ]] \
  || { echo "FAIL: n8n MEMORY.md missing"; exit 1; }
[[ -d "$SANDBOX/Paperclip/Skill-Wissen/n8n/_archive" ]] \
  || { echo "FAIL: n8n _archive/ missing"; exit 1; }

echo "## Manual edit" >> "$SANDBOX/Paperclip/Skill-Wissen/n8n/MEMORY.md"
vault_ensure_knowledge_domain "n8n" "n8n Workflow Automation"
grep -q "Manual edit" "$SANDBOX/Paperclip/Skill-Wissen/n8n/MEMORY.md" \
  || { echo "FAIL: manual edit lost on second ensure"; exit 1; }

TEMPLATE="$HERE/../templates/memory_initial.md"
vault_ensure_agent "whitestag" "online-recherche" "Online-Recherche" "$TEMPLATE"
[[ -f "$SANDBOX/Paperclip/Agenten/whitestag/online-recherche/MEMORY.md" ]] \
  || { echo "FAIL: agent MEMORY.md missing"; exit 1; }
[[ -d "$SANDBOX/Paperclip/Agenten/whitestag/online-recherche/lessons" ]] \
  || { echo "FAIL: lessons dir missing"; exit 1; }
[[ -d "$SANDBOX/Paperclip/Agenten/whitestag/online-recherche/references" ]] \
  || { echo "FAIL: references dir missing"; exit 1; }
grep -q "Online-Recherche" "$SANDBOX/Paperclip/Agenten/whitestag/online-recherche/MEMORY.md" \
  || { echo "FAIL: agent name not substituted"; exit 1; }

echo "OK: test_vault_ops.sh"
