# Returns 0 (true) if an issue with this title was created in the last 24h
# in the given company. Used to avoid duplicate issues on re-trigger.
# Depends on paperclip_list_issues being defined.

issue_already_exists_today() {
  local company_id="$1" title="$2"
  local cutoff
  cutoff=$(date -u -v-24H +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d '24 hours ago' +%Y-%m-%dT%H:%M:%SZ)
  local match_count
  match_count=$(paperclip_list_issues "$company_id" | jq --arg t "$title" --arg cutoff "$cutoff" \
    '[.[] | select(.title == $t and .createdAt >= $cutoff)] | length')
  [[ "$match_count" -gt 0 ]]
}
