# Wrapper around curl + jq for Paperclip REST API.
# Requires CONFIG_PAPERCLIP_API_BASE and PAPERCLIP_BOARD_API_KEY
# to be set (both done by load_config in lib/config.sh).

paperclip_get() {
  curl -sS -f -H "Authorization: Bearer ${PAPERCLIP_BOARD_API_KEY}" \
    "${CONFIG_PAPERCLIP_API_BASE}$1"
}

paperclip_post_json() {
  curl -sS -f -X POST "${CONFIG_PAPERCLIP_API_BASE}$1" \
    -H "Authorization: Bearer ${PAPERCLIP_BOARD_API_KEY}" \
    -H "Content-Type: application/json" \
    -d "$2"
}

paperclip_patch_json() {
  curl -sS -f -X PATCH "${CONFIG_PAPERCLIP_API_BASE}$1" \
    -H "Authorization: Bearer ${PAPERCLIP_BOARD_API_KEY}" \
    -H "Content-Type: application/json" \
    -d "$2"
}

paperclip_list_agents() {
  paperclip_get "/api/companies/$1/agents"
}

paperclip_create_issue() {
  # $1 = company id, $2 = title, $3 = description, $4 = assigneeAgentId
  # NOTE: schema uses `description` (NOT body) and `assigneeAgentId` (NOT assignedAgentId).
  # status: "todo" — agent's inbox filter is "todo,in_progress,in_review,blocked";
  # "backlog" is invisible to the heartbeat scan.
  local payload
  payload=$(jq -n \
    --arg t "$2" --arg d "$3" --arg a "$4" \
    '{title:$t, description:$d, assigneeAgentId:$a, status:"todo"}')
  paperclip_post_json "/api/companies/$1/issues" "$payload"
}

paperclip_list_issues() {
  paperclip_get "/api/companies/$1/issues${2:-}"
}

paperclip_list_company_heartbeat_runs() {
  # $1 = company id, $2 = optional limit (default 200)
  local limit="${2:-200}"
  paperclip_get "/api/companies/$1/heartbeat-runs?limit=${limit}"
}

paperclip_get_run_activity() {
  paperclip_get "/api/heartbeat-runs/$1/log"
}

paperclip_get_issue_comments() {
  paperclip_get "/api/issues/$1/comments"
}

paperclip_wake_agent() {
  # $1 = agent id, $2 = reason (free text)
  local payload
  payload=$(jq -n --arg r "$2" '{source:"assignment", triggerDetail:"manual", reason:$r}')
  paperclip_post_json "/api/agents/$1/wakeup" "$payload"
}
