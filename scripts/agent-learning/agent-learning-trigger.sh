#!/usr/bin/env bash
# Agent Nightly Learning Trigger
# Usage: agent-learning-trigger.sh <knowledge|lessons|decay> [--dry-run]

set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
source "$HERE/lib/config.sh"
source "$HERE/lib/paperclip_api.sh"
source "$HERE/lib/vault_ops.sh"
source "$HERE/lib/slug.sh"
source "$HERE/lib/rotation.sh"
source "$HERE/lib/idempotency.sh"
source "$HERE/lib/decay.sh"

MODE="${1:-}"; shift || true
DRY_RUN=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    *) echo "Unknown arg: $arg" >&2; exit 2 ;;
  esac
done

if [[ -z "$MODE" ]]; then
  echo "Usage: $0 <knowledge|lessons|decay> [--dry-run]" >&2
  exit 2
fi

log() { echo "[$(date +%H:%M:%S)] $*"; }

load_config
vault_check_mounted

# Render template: $1 = template path, additional args are KEY=value pairs.
# Pure-Bash parameter expansion — handles multi-line values and quotes safely.
render_template() {
  local tmpl="$1"; shift
  local content
  content=$(cat "$tmpl")
  for kv in "$@"; do
    local k="${kv%%=*}" v="${kv#*=}"
    content="${content//\{\{${k}\}\}/${v}}"
  done
  printf '%s' "$content"
}

case "$MODE" in
  knowledge)
    log "Knowledge-Loop starting"
    today_short=$(weekday_short_today)
    today_iso=$(date +%Y-%m-%d)
    domains=$(weekday_domains "$today_short")
    if [[ -z "$domains" ]]; then
      log "No domains scheduled for $today_short — exiting clean."
      exit 0
    fi
    for domain in $domains; do
      title=$(domain_title "$domain")
      sources_list=$(domain_sources "$domain" | sed 's/^/- /')
      vault_path="${CONFIG_VAULT_ROOT}/${CONFIG_VAULT_KNOWLEDGE_DIR}/${domain}"

      vault_ensure_knowledge_domain "$domain" "$title"

      issue_title="Recherche: ${title} — Stand ${today_iso}"
      if issue_already_exists_today "$CONFIG_COMPANIES_WHITESTAG_ID" "$issue_title"; then
        log "Skip $domain — issue with same title exists in last 24h."
        continue
      fi

      body=$(render_template "$HERE/templates/issue_knowledge.md" \
        "DOMAIN_TITLE=${title}" \
        "DOMAIN_SLUG=${domain}" \
        "SOURCES_LIST=${sources_list}" \
        "VAULT_DOMAIN_PATH=${vault_path}" \
        "TODAY=${today_iso}" \
        "MAX_TURNS=${CONFIG_KNOWLEDGE_MAX_TURNS}" \
        "TIMEOUT_SEC=${CONFIG_KNOWLEDGE_TIMEOUT_SEC}")

      if [[ "$DRY_RUN" -eq 1 ]]; then
        log "DRY-RUN: would create issue '$issue_title' in WHITESTAG, assigned to online-recherche"
        echo "--- BODY ---"; echo "$body"; echo "--- END ---"
      else
        result=$(paperclip_create_issue "$CONFIG_COMPANIES_WHITESTAG_ID" \
          "$issue_title" "$body" "$CONFIG_ONLINE_RECHERCHE_ID")
        issue_id=$(echo "$result" | jq -r '.id')
        log "Created knowledge issue: $issue_id ($domain)"
        paperclip_wake_agent "$CONFIG_ONLINE_RECHERCHE_ID" "knowledge issue $issue_id" >/dev/null \
          || log "WARN: wakeup failed for online-recherche"
      fi
    done

    if [[ "$DRY_RUN" -eq 0 ]]; then
      domain_list=$(echo "$domains" | tr '\n' ',' | sed 's/,$//' | sed 's/,/, /g')
      vault_status_append "## $(date +"%Y-%m-%d %H:%M") — Recherche-Pass ($today_short)" <<EOF
- Domains: ${domain_list}
EOF
    fi
    log "Knowledge-Loop done."

    # B2: AGENTS.md Skill-Wissen-Sektionen auffrischen
    if [[ "$DRY_RUN" -eq 0 ]]; then
      log "Skill-Wissen-Sync: regeneriere AGENTS.md-Sektionen"
      SW_TOKEN=$(python3 -c "import json,os;d=json.load(open(os.path.expanduser('~/.paperclip/auth.json')));print(d['credentials']['http://localhost:3100']['token'])" 2>/dev/null || true)
      if [[ -n "$SW_TOKEN" ]]; then
        PCP_TOKEN="$SW_TOKEN" PCP_CID="9cebf3cf-efe8-4597-a400-f06488900a87" \
          python3 "$HOME/.paperclip/scripts/agents-instructions/build-agents-md.py" --apply \
          || log "Skill-Wissen-Sync FEHLGESCHLAGEN (nicht fatal)"
      else
        log "Skill-Wissen-Sync übersprungen — kein Token in auth.json"
      fi
    fi
    ;;

  lessons)
    log "Lessons-Loop starting"
    today_iso=$(date +%Y-%m-%d)
    yesterday_iso=$(date -v-1d +%Y-%m-%d 2>/dev/null || date -d 'yesterday' +%Y-%m-%d)
    cutoff_iso=$(date -u -v-${CONFIG_LESSONS_LOOKBACK_HOURS}H +%Y-%m-%dT%H:%M:%SZ 2>/dev/null \
      || date -u -d "${CONFIG_LESSONS_LOOKBACK_HOURS} hours ago" +%Y-%m-%dT%H:%M:%SZ)

    # Nur WHITESTAG: das Lessons-Issue liegt in WHITESTAG, und dessen Agent-Keys
    # bekommen auf Runs/Issues anderer Companies 403. Health-Runs im Body
    # blockierten das Issue jede Nacht erneut (WHI-9852, 17.10.).
    # Filter client-side by status (trigger_run_statuses) and createdAt cutoff.
    statuses_array=$(yq -o=json -I=0 '.lessons_loop.trigger_run_statuses' "$CONFIG_FILE")

    wh_runs=$(paperclip_list_company_heartbeat_runs "$CONFIG_COMPANIES_WHITESTAG_ID" 500)

    runs_json=$(echo "$wh_runs" | jq --argjson statuses "$statuses_array" \
      --arg cutoff "$cutoff_iso" --argjson max "$CONFIG_LESSONS_MAX_RUNS" \
      'map(select((.status as $s | $statuses | index($s)) != null
                    and (.createdAt // .startedAt // "1970-01-01") >= $cutoff))
       | sort_by(.createdAt // .startedAt) | reverse | .[0:$max]')

    run_count=$(echo "$runs_json" | jq 'length')
    if [[ "$run_count" -eq 0 && "$CONFIG_LESSONS_SKIP_IF_EMPTY" == "true" ]]; then
      log "No friction runs in last ${CONFIG_LESSONS_LOOKBACK_HOURS}h — skipping."
      if [[ "$DRY_RUN" -eq 0 ]]; then
        vault_status_append "## $(date +"%Y-%m-%d %H:%M") — Reibungs-Sweep" <<EOF
- skipped — no friction runs in last ${CONFIG_LESSONS_LOOKBACK_HOURS}h
EOF
      fi
      exit 0
    fi

    # heartbeat-runs response gives IDs but not display-names — Vault-Maintainer
    # resolves agent/issue names via API when processing the issue body.
    run_list=$(echo "$runs_json" | jq -r '.[] |
      "- Run `\(.id)` — agentId `\(.agentId)` — companyId `\(.companyId)` — status `\(.status)`" +
      (if .errorCode then " — errorCode `\(.errorCode)`" else "" end) +
      (if .contextSnapshot.issueId then " — issueId `\(.contextSnapshot.issueId)`" else "" end)')

    issue_title="Lessons aus Reibungs-Runs vom ${yesterday_iso}"
    if issue_already_exists_today "$CONFIG_COMPANIES_WHITESTAG_ID" "$issue_title"; then
      log "Skip — lessons issue with same title exists in last 24h."
      exit 0
    fi

    body=$(render_template "$HERE/templates/issue_lessons.md" \
      "YESTERDAY=${yesterday_iso}" \
      "TODAY=${today_iso}" \
      "RUN_LIST=${run_list}" \
      "VAULT_LESSONS_PATH_PATTERN=${CONFIG_VAULT_ROOT}/${CONFIG_VAULT_AGENTS_DIR}/<company-slug>/<agent-slug>/lessons/${today_iso}-<run-id-kurz>-<topic-slug>.md" \
      "VAULT_AGENT_PATH_PATTERN=${CONFIG_VAULT_ROOT}/${CONFIG_VAULT_AGENTS_DIR}/<company-slug>/<agent-slug>" \
      "MAX_RUNS=${CONFIG_LESSONS_MAX_RUNS}")

    if [[ "$DRY_RUN" -eq 1 ]]; then
      log "DRY-RUN: would create lessons issue '$issue_title' assigned to vault-maintainer"
      echo "--- BODY ---"; echo "$body"; echo "--- END ---"
    else
      result=$(paperclip_create_issue "$CONFIG_COMPANIES_WHITESTAG_ID" \
        "$issue_title" "$body" "$CONFIG_VAULT_MAINTAINER_ID")
      issue_id=$(echo "$result" | jq -r '.id')
      log "Created lessons issue: $issue_id (${run_count} friction runs)"
      paperclip_wake_agent "$CONFIG_VAULT_MAINTAINER_ID" "lessons issue $issue_id" >/dev/null \
        || log "WARN: wakeup failed for vault-maintainer"
      vault_status_append "## $(date +"%Y-%m-%d %H:%M") — Reibungs-Sweep" <<EOF
- ${run_count} friction runs handed to Vault-Maintainer (issue ${issue_id})
EOF
    fi
    log "Lessons-Loop done."
    ;;

  decay)
    log "Decay-Pass starting"
    k_days=$(yq '.decay_pass.knowledge_archive_after_days' "$CONFIG_FILE")
    l_days=$(yq '.decay_pass.lessons_archive_after_days' "$CONFIG_FILE")

    if [[ "$DRY_RUN" -eq 1 ]]; then
      log "DRY-RUN: would archive knowledge >${k_days}d and lessons >${l_days}d in $CONFIG_VAULT_ROOT/$CONFIG_VAULT_AGENTS_DIR"
    else
      decay_run "$CONFIG_VAULT_ROOT" "$CONFIG_VAULT_KNOWLEDGE_DIR" "$CONFIG_VAULT_AGENTS_DIR" "$k_days" "$l_days"
      vault_status_append "## $(date +"%Y-%m-%d %H:%M") — Decay-Pass" <<EOF
- knowledge_archive_after_days: ${k_days}
- lessons_archive_after_days: ${l_days}
EOF
    fi
    log "Decay-Pass done."
    ;;

  *)
    echo "Unknown mode: $MODE" >&2; exit 2 ;;
esac
