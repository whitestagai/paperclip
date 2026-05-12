# Filesystem operations on the Obsidian vault.
# Requires CONFIG_VAULT_ROOT, CONFIG_VAULT_KNOWLEDGE_DIR, CONFIG_VAULT_AGENTS_DIR.

vault_check_mounted() {
  [[ -d "$CONFIG_VAULT_ROOT" ]] || {
    echo "ERROR: vault not mounted at $CONFIG_VAULT_ROOT" >&2
    return 1
  }
}

vault_ensure_knowledge_domain() {
  # $1 = domain slug, $2 = domain title
  local domain="$1" title="$2"
  local dir="$CONFIG_VAULT_ROOT/$CONFIG_VAULT_KNOWLEDGE_DIR/$domain"
  mkdir -p "$dir/_archive"
  if [[ ! -f "$dir/MEMORY.md" ]]; then
    cat > "$dir/MEMORY.md" <<EOF
# Memory Index — ${title}

*Domain-Index, wird vom Online-Recherche-Agent nächtlich gepflegt.*

## Aktive Einträge

*(noch keine)*

## Archiv

Siehe \`_archive/\`.
EOF
  fi
}

vault_ensure_agent() {
  # $1 = company slug, $2 = agent slug, $3 = agent display name, $4 = path to memory template
  local co="$1" ag="$2" name="$3" tmpl="$4"
  local dir="$CONFIG_VAULT_ROOT/$CONFIG_VAULT_AGENTS_DIR/$co/$ag"
  mkdir -p "$dir/lessons/_archive" "$dir/references"
  if [[ ! -f "$dir/MEMORY.md" ]]; then
    sed "s/{{AGENT_NAME}}/${name}/g" "$tmpl" > "$dir/MEMORY.md"
  fi
  if [[ ! -f "$dir/references/quellen.md" ]]; then
    cat > "$dir/references/quellen.md" <<EOF
# Externe Quellen — ${name}

*(URLs, Doku-Pointers — wird über Zeit vom Agent ergänzt)*
EOF
  fi
}

vault_status_append() {
  # $1 = section header line; stdin = body lines
  local status="$CONFIG_VAULT_ROOT/$CONFIG_VAULT_AGENTS_DIR/_status.md"
  if [[ ! -f "$status" ]]; then
    cat > "$status" <<EOF
# Agent Learning — Lauf-Status

Auto-generiert. Jeder Trigger-Lauf appendet hier einen Eintrag.

EOF
  fi
  {
    echo
    echo "$1"
    cat
  } >> "$status"
}
