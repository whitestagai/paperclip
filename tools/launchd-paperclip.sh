#!/bin/zsh
# launchd wrapper for Paperclip dev server.
#
# Runs `pnpm dev` AND a parallel HTTP health-watchdog.
# If the health endpoint fails ≥MAX_FAIL times in a row, the whole process
# tree is killed and the wrapper exits → launchd restarts the wrapper.
# This catches OOM-crashes where the outer pnpm/tsx parents stay alive but
# the actual Node server is dead (see dev-watch.ts — no crash-restart).

set -u

export HOME="/Users/walterschoenenbroecher.de"
export PATH="$HOME/.nvm/versions/node/v22.22.0/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

# Hostnames (Cloudflare-Tunnel, lokale LAN-Aliase) die Paperclip akzeptieren darf.
# Komma-separiert; gelesen in server/src/config.ts → PAPERCLIP_ALLOWED_HOSTNAMES.
export PAPERCLIP_ALLOWED_HOSTNAMES="company.whitestag.ai,192.168.2.191,192.168.2.191:3100,127.0.0.1:3100,localhost:3100"

# n8n-Mailhub-Webhook-Secret. Wird von Agents über shell_exec curl genutzt,
# um E-Mails via SMTP Relay zu versenden (z.B. CHO der Health Insights Company).
# Quelle: n8n credential "Mailhub Webhook Secret" (Header X-Mailhub-Secret).
export MAILHUB_WEBHOOK_SECRET="$(sed -n 's/^MAILHUB_SECRET=//p' "$HOME/.paperclip/instances/default/secrets/mailhub.env" 2>/dev/null | tr -d '\n' || true)"
[ -n "${MAILHUB_WEBHOOK_SECRET:-}" ] || echo "WARNUNG: MAILHUB_SECRET nicht aus ~/.paperclip/instances/default/secrets/mailhub.env lesbar" >&2

# Per-task model router (Phase 1+2). Opt-in kill-switch read by the heartbeat
# dispatch path (server/src/services/model-router-signals.ts → isModelRouterEnabled).
# "on" = route trivial tasks of Qwen-default lmstudio agents to the cheap (Gemma)
# profile; anything else / unset = router off, every task stays on its default model.
export PAPERCLIP_MODEL_ROUTER="on"

REPO="$HOME/SynologyDrive/Mac/Claude Code MAC/Paperclip"
HEALTH_URL="http://127.0.0.1:3100/api/health"
BOOT_TIMEOUT=240      # seconds to wait for first successful health check
POLL_INTERVAL=15      # seconds between post-boot health checks
MAX_FAIL=3            # consecutive failures before we kill the stack
LOG_PREFIX="[launchd-wrapper $(date '+%H:%M:%S')]"

log() { echo "$LOG_PREFIX $*"; }

cd "$REPO" || { log "FATAL: repo not found"; exit 1; }

# Keep the Mac awake while Paperclip is running. macOS idle/disk sleep
# otherwise stalls LMStudio streams mid-run (observed: Vault-Maintainer
# nighttime routines failing with adapter_failed after the LLM stream
# silently froze). `-w $$` ties caffeinate's lifetime to this wrapper —
# when launchd restarts us, caffeinate exits cleanly with the old PID.
caffeinate -i -m -w $$ &
CAFFEINATE_PID=$!
log "caffeinate started PID=$CAFFEINATE_PID (idle+disk sleep blocked while wrapper alive)"

# Start pnpm dev as a backgrounded child
pnpm dev &
PNPM_PID=$!
log "pnpm dev started PID=$PNPM_PID"

# Graceful cleanup (on any exit path)
cleanup() {
  log "cleanup: killing pnpm tree PID=$PNPM_PID"
  # Kill direct children
  pkill -TERM -P "$PNPM_PID" 2>/dev/null
  kill -TERM "$PNPM_PID" 2>/dev/null
  sleep 2
  # Force-kill anything still alive that looks like the paperclip dev stack
  pkill -9 -f 'tsx .*src/index\.ts|dev-watch\.ts|dev-runner\.ts|@paperclipai/server dev:watch|node .*pnpm dev' 2>/dev/null
  kill -9 "$PNPM_PID" 2>/dev/null
}
trap cleanup EXIT TERM INT

# --- Boot phase: wait until API answers ---
booted=0
for i in $(seq 1 $((BOOT_TIMEOUT / 2))); do
  if curl -sSf -o /dev/null -m 3 "$HEALTH_URL" 2>/dev/null; then
    log "boot ok after $((i * 2))s"
    booted=1
    break
  fi
  if ! kill -0 "$PNPM_PID" 2>/dev/null; then
    log "pnpm dev died during boot → exit 1"
    exit 1
  fi
  sleep 2
done

if [ "$booted" -ne 1 ]; then
  log "boot timeout after ${BOOT_TIMEOUT}s → exit 1 (launchd will restart)"
  exit 1
fi

# --- Run phase: periodic health check ---
fail=0
while kill -0 "$PNPM_PID" 2>/dev/null; do
  sleep "$POLL_INTERVAL"
  if curl -sSf -o /dev/null -m 5 "$HEALTH_URL" 2>/dev/null; then
    if [ "$fail" -gt 0 ]; then
      log "health recovered"
    fi
    fail=0
  else
    fail=$((fail + 1))
    log "healthcheck fail $fail/$MAX_FAIL"
    if [ "$fail" -ge "$MAX_FAIL" ]; then
      log "stack unhealthy → exit 1 (launchd will restart)"
      exit 1
    fi
  fi
done

log "pnpm dev exited on its own → exit 0"
exit 0
