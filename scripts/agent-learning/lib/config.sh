# Loaded via `source`. Exports CONFIG_* environment variables.
# Default config path: ~/.paperclip/instances/default/agent-learning.config.yaml
# Override via env var CONFIG_FILE.
# Also sources the Board-API-Key secret-file (chmod 600).

load_config() {
  local config_file="${CONFIG_FILE:-$HOME/.paperclip/instances/default/agent-learning.config.yaml}"
  local secret_file="${SECRET_FILE:-$HOME/.paperclip/instances/default/agent-learning.secret}"

  if [[ ! -f "$config_file" ]]; then
    echo "ERROR: config file not found: $config_file" >&2
    return 1
  fi
  if [[ ! -f "$secret_file" ]]; then
    echo "ERROR: secret file not found: $secret_file (run plan Task 0 Step 3 to create)" >&2
    return 1
  fi
  # shellcheck disable=SC1090
  source "$secret_file"
  if [[ -z "${PAPERCLIP_BOARD_API_KEY:-}" ]]; then
    echo "ERROR: PAPERCLIP_BOARD_API_KEY not set after sourcing $secret_file" >&2
    return 1
  fi
  export PAPERCLIP_BOARD_API_KEY

  export CONFIG_FILE="$config_file"
  export CONFIG_VAULT_ROOT=$(yq '.vault.root' "$config_file")
  export CONFIG_VAULT_KNOWLEDGE_DIR=$(yq '.vault.knowledge_dir' "$config_file")
  export CONFIG_VAULT_AGENTS_DIR=$(yq '.vault.agents_dir' "$config_file")
  export CONFIG_PAPERCLIP_API_BASE=$(yq '.paperclip.api_base' "$config_file")
  export CONFIG_COMPANIES_WHITESTAG_ID=$(yq '.companies.whitestag.id' "$config_file")
  export CONFIG_COMPANIES_HEALTH_ID=$(yq '.companies.health.id' "$config_file")
  export CONFIG_ONLINE_RECHERCHE_ID=$(yq '.agents.online_recherche.id' "$config_file")
  export CONFIG_VAULT_MAINTAINER_ID=$(yq '.agents.vault_maintainer.id' "$config_file")
  export CONFIG_KNOWLEDGE_MAX_TURNS=$(yq '.knowledge_loop.max_turns_per_run' "$config_file")
  export CONFIG_KNOWLEDGE_TIMEOUT_SEC=$(yq '.knowledge_loop.timeout_sec' "$config_file")
  export CONFIG_LESSONS_LOOKBACK_HOURS=$(yq '.lessons_loop.lookback_hours' "$config_file")
  export CONFIG_LESSONS_MAX_RUNS=$(yq '.lessons_loop.max_runs_per_sweep' "$config_file")
  export CONFIG_LESSONS_MARKER=$(yq '.lessons_loop.always_pickup_marker' "$config_file")
  export CONFIG_LESSONS_SKIP_IF_EMPTY=$(yq '.lessons_loop.skip_if_empty' "$config_file")
}

weekday_domains() {
  local day="$1"
  yq ".knowledge_loop.rotation.${day}[]" "${CONFIG_FILE}" 2>/dev/null || true
}

domain_title() {
  yq ".domains.${1}.title" "${CONFIG_FILE}"
}

domain_sources() {
  yq ".domains.${1}.sources[]" "${CONFIG_FILE}" 2>/dev/null || true
}
