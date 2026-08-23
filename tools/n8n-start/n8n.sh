#!/usr/bin/env bash
set -euo pipefail

# =========================================
#  WHITESTAG Start: n8n + Audio Player + Voice Agent + CCC-Film (macOS)
# Stand 07.06.2026
# =========================================

# --- PostgreSQL starten falls nicht läuft ---
pg_ctl -D /opt/homebrew/var/postgresql@18 status >/dev/null 2>&1 || \
  pg_ctl -D /opt/homebrew/var/postgresql@18 start

# --- Konfiguration ---
export N8N_HOST="127.0.0.1"
export N8N_PORT="5678"
export WEBHOOK_URL="https://n8n.whitestag.ai"
export N8N_EDITOR_BASE_URL="https://n8n.whitestag.ai"
export N8N_PROXY_HOPS=1
# --- Secrets zentral aus ~/.whitestag.env laden (chmod 600) ---
# Enthält TELEGRAM_BOT_TOKEN, EWS_USER/EWS_PASS (Walter) und
# EWS_USER_CLARA/EWS_PASS_CLARA (Clara). set -a sorgt dafür, dass
# alle gesourcten Variablen an Kindprozesse (n8n) vererbt werden.
if [[ -f "$HOME/.whitestag.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$HOME/.whitestag.env"
  set +a
else
  echo "WARN: ~/.whitestag.env nicht gefunden – EWS/Telegram-Secrets fehlen."
fi
export N8N_BLOCK_ENV_ACCESS_IN_NODE="false"
export GENERIC_TIMEZONE=Europe/Berlin
export N8N_DIAGNOSTICS_ENABLED=false

# Audio Player
PLAYER_HOST="127.0.0.1"
PLAYER_PORT="8123"

# Voice Agent (Python)
AGENT_DIR="$HOME/voice-agent"
AGENT_PY="$AGENT_DIR/agent.py"
AGENT_VENV_ACTIVATE="$AGENT_DIR/.venv/bin/activate"

# CCC-Film Backend
CCCFILM_DIR="/Users/walterschoenenbroecher.de/Library/CloudStorage/SynologyDrive-Mac/Claude Code MAC/CCC-Film/app/backend"
CCCFILM_PORT="3000"

# Paperclip
PAPERCLIP_DIR="$HOME/SynologyDrive/2026/AI/Claude Code/Paperclip"
PAPERCLIP_PORT="3100"

# Cannabis Grow Manager
CANNABIS_DIR="$HOME/Desktop/Claude Code/Cannabis/Cannabis-GUI"
CANNABIS_PORT="3001"

# KI-Kompass App (Expo Web — Microlearning-App EU AI Act)
KIKOMPASS_DIR="/Users/walterschoenenbroecher.de/Library/CloudStorage/SynologyDrive-Mac/Claude Code MAC/Apps/WHITESTAG App"
KIKOMPASS_PORT="8081"

# ComfyUI
COMFYUI_DIR="$HOME/ComfyUI"
COMFYUI_PORT="8000"
COMFYUI_VENV_ACTIVATE="$COMFYUI_DIR/.venv/bin/activate"

# Optional: erzwinge Node-Version
NVM_DIR="$HOME/.nvm"
NODE_VERSION="22"

# --- Verzeichnisse für Logs & PIDs ---
LOGDIR="$HOME/.whitestag-logs"
PIDDIR="$HOME/.whitestag-pids"
mkdir -p "$LOGDIR" "$PIDDIR"

N8N_LOG="$LOGDIR/n8n.log"
PLAYER_LOG="$LOGDIR/audio-player.log"
AGENT_LOG="$LOGDIR/voice-agent.log"
CANNABIS_LOG="$LOGDIR/cannabis.log"
COMFYUI_LOG="$LOGDIR/comfyui.log"
CCCFILM_LOG="$LOGDIR/ccc-film.log"
PAPERCLIP_LOG="$LOGDIR/paperclip.log"
KIKOMPASS_LOG="$LOGDIR/ki-kompass.log"

N8N_PIDFILE="$PIDDIR/n8n.pid"
PLAYER_PIDFILE="$PIDDIR/audio-player.pid"
AGENT_PIDFILE="$PIDDIR/voice-agent.pid"
CANNABIS_PIDFILE="$PIDDIR/cannabis.pid"
COMFYUI_PIDFILE="$PIDDIR/comfyui.pid"
CCCFILM_PIDFILE="$PIDDIR/ccc-film.pid"
PAPERCLIP_PIDFILE="$PIDDIR/paperclip.pid"
KIKOMPASS_PIDFILE="$PIDDIR/ki-kompass.pid"

# Player Script Location
PLAYER_DIR="$HOME/.whitestag-audio"
PLAYER_JS="$PLAYER_DIR/player.js"
mkdir -p "$PLAYER_DIR"

echo "========================================"
echo " WHITESTAG Start (macOS)"
echo " n8n + Audio Player + Voice Agent + ComfyUI + CCC-Film + Paperclip + Cannabis"
echo "========================================"
echo

# --- nvm initialisieren (wichtig für Autostart/LaunchAgent) ---
if [[ -s "$NVM_DIR/nvm.sh" ]]; then
  # shellcheck disable=SC1090
  source "$NVM_DIR/nvm.sh"
  nvm use "$NODE_VERSION" >/dev/null || true
else
  echo "WARN: nvm.sh nicht gefunden unter: $NVM_DIR/nvm.sh"
fi

# --- Checks ---
if ! command -v n8n >/dev/null 2>&1; then
  echo "ERROR: 'n8n' nicht gefunden (PATH)."
  echo "Tipp: Prüfe 'which n8n' im Terminal und ob nvm korrekt initialisiert ist."
  exit 1
fi

if ! command -v node >/dev/null 2>&1; then
  echo "ERROR: 'node' nicht gefunden (PATH)."
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: 'python3' nicht gefunden (PATH)."
  exit 1
fi

echo "node path  : $(which node)"
echo "n8n  path  : $(which n8n)"
echo "python path: $(which python3)"
echo

# ============================================================
# 0) LM Studio: Server + Modelle (inkl. Draft-Modelle) vorladen
# ============================================================
# Läuft im Hintergrund (Modell-Laden dauert Minuten), damit n8n/Paperclip
# nicht warten. Non-fatal: Fehler beim Laden brechen den Gesamtstart NICHT ab.
#
# Speculative Decoding (Draft-Modelle) wird in LM Studio NICHT per CLI gesetzt,
# sondern EINMALIG im GUI als Pro-Modell-Default gepaart (persistiert):
#   • Qwen2.5-Coder-14B  ← Draft  Qwen2.5-0.5B-Instruct-MLX-8bit   (Tokenizer identisch)
#   • Gemma-4-31B-it     ← Draft  gemma-4-31B-it-assistant         (Googles Draft-Kopf)
#   • Qwen3.6-35B        → KEIN Draft (kein tokenizer-kompatibles Modell vorhanden)
# Dieses Skript stellt nur sicher, dass Haupt- UND Draft-Modelle resident sind.
LMS="$HOME/.lmstudio/bin/lms"
LMSTUDIO_LOG="$LOGDIR/lmstudio-preload.log"
if [[ -x "$LMS" ]]; then
  echo "Preloading LM Studio Modelle im Hintergrund (Log: $LMSTUDIO_LOG) ..."
  nohup env LMS="$LMS" LMSTUDIO_LOG="$LMSTUDIO_LOG" bash -c '
    set +e
    log(){ echo "[$(date "+%Y-%m-%d %H:%M:%S")] $*" >>"$LMSTUDIO_LOG"; }
    # 1) Server sicherstellen
    if ! "$LMS" server status 2>/dev/null | grep -qi "running"; then
      log "Starte LM Studio Server ..."
      "$LMS" server start >>"$LMSTUDIO_LOG" 2>&1
      sleep 3
    fi
    # load <ps-such-pattern> <load-identifier/pfad> [extra lms-load-args ...]
    load(){
      pat="$1"; key="$2"; shift 2
      if "$LMS" ps 2>/dev/null | grep -q "$pat"; then
        log "schon geladen: $pat"; return 0
      fi
      log "lade: $key $*"
      if "$LMS" load "$key" "$@" -y >>"$LMSTUDIO_LOG" 2>&1; then
        log "OK: $key"
      else
        log "WARN: Laden fehlgeschlagen (evtl. Speicher-Guardrail): $key"
      fi
    }
    log "=== LM-Studio-Preload Start ==="
    # WICHTIG: 'lms load' braucht den kurzen modelKey, NICHT den Repo-Pfad
    # (ein Pfad faellt stumm ins interaktive Menue und laedt nichts).
    #
    # === Per-Geraet-Pinning (Root-Cause-Fix 2026-07-18) ===
    # Beide Macs sind 24/7 always-on. Die STUDIO faehrt zusaetzlich den ganzen
    # Dienste-Stack (Postgres/n8n/Paperclip/Brain/PII-Proxy, ~50-65 GB) -> bewusst
    # SCHLANK halten. Der MacBook faehrt nur Modelle -> die grossen Denk-Modelle
    # dorthin. Root Cause der Fleet-Ausfaelle: LM-Links "preferred device" war der
    # VOLLE MacBook -> jeder JIT-Load eines evicteten Modells (v.a. qwen3.6-35b)
    # scheiterte am Speicher-Guardrail -> Runs sterben -> Recovery-Kaskade. Fix:
    # grosse Modelle EXPLIZIT pro Geraet pinnen; preferred am Ende = Studio, damit
    # JIT-Overflow (seltene Modelle) dort landet, wo Platz + stabil ist.
    STUDIO_ID="$("$LMS" link status --json 2>/dev/null | python3 -c "import sys,json;print(json.load(sys.stdin).get('deviceIdentifier',''))" 2>/dev/null)"
    MACBOOK_ID="$("$LMS" link status --json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(next((p['deviceIdentifier'] for p in d.get('peers',[]) if 'acbook' in p.get('deviceName','')), ''))" 2>/dev/null)"
    set_pref(){ [ -n "$1" ] && "$LMS" link set-preferred-device "$1" >>"$LMSTUDIO_LOG" 2>&1 && log "preferred device -> $2"; }

    # --- MacBook: nur noch Fallback + Admin-Pilot ---
    #   qwen3.6-35b-a3b-mlx : ENTFERNT am 2026-08-22 — laeuft NUR NOCH AUF DER RTX
    #     als `abiray/qwen3.6-35b-a3b` (GGUF Q6_K, ctx 262144, Reasoning per
    #     Jinja-Vorlage aus). Alle 13 Agenten und 4 n8n-Workflows zeigen dorthin.
    #     NICHT wieder aufnehmen: die MLX-Variante schrieb den Denkprozess roh in
    #     `content` (Agenten bekamen englischen Denktext als Antwort), und ihre
    #     37,75 GB sind genau der Platz, der das MacBook aus der Dauerueberlastung
    #     holt.
    #   gemma-4-31b-it-mlx  : seit 2026-08-22 NUR NOCH FALLBACK (14 Agenten).
    #     Der Primaerpfad liegt auf der RTX: `gemma4-31b-it` (GGUF Q8, ctx 262144).
    #     Dorthin gewandert sind 22 Primaer- + 24 cheap-Profile, der Wake-Satellit
    #     und 6 n8n-Workflows. Hier bleibt es geladen, weil es das Netz auf einem
    #     ANDEREN Geraet ist — nicht entladen.
    #     ACHTUNG: `-c` unten ist bei MLX wirkungslos ("context auto-fit" zieht auf
    #     262144 hoch); die Zeile laedt, sie dimensioniert nicht.
    #   mistral-small-3.2   : Admin-Pilot (Sekretaerin, Office & Admin) seit 2026-07-20.
    #     Non-Reasoning + starkes Function-Calling -> gegen die max_iterations-Schleifen
    #     simpler Admin-Tasks. War vorher NUR JIT (n8n-Newsletter) und damit nicht
    #     neustart-fest; als Agent-Primaermodell muss es resident sein.
    set_pref "$MACBOOK_ID" "MacBook"
    # qwen3.6-35b-a3b-mlx bewusst NICHT mehr laden (siehe Kommentar oben).
    # KEIN --ttl angeben: die Option setzt nur, sie loescht nicht. Ohne sie
    # bekommt die Instanz ttlMs=null und wird nie automatisch entladen; mit
    # JIT-Nachladen haengt sonst wieder eine Stunde TTL dran und der Fallback
    # verschwindet unbemerkt.
    load "gemma-4-31b-it-mlx"  "gemma-4-31b-it-mlx"  -c 131077 --parallel 4
    load "mistral-small-3.2-24b-instruct-2506-mlx" "mistral-small-3.2-24b-instruct-2506-mlx" -c 131072 --parallel 4

    # --- Studio: schlankes Infra-/Fallback-Set ---
    #   text-embedding-bge-m3: Embeddings
    #   (gemma-4-12b PII-Classifier laedt separat via PII-Proxy-Infra)
    #
    #   2026-08-22: LOKALE CODER-SCHIENE KOMPLETT ENTFERNT.
    #   qwen/qwen3-coder-next (84,67 GB) und qwen/qwen3-coder-30b (17,19 GB)
    #   sind raus — Modelle geloescht, kein Agent und kein Workflow zeigt mehr
    #   darauf. Grund: 31 bzw. 38 Aufrufe in 60 Tagen, letzte Ende Juli, und der
    #   einzige Nutzer (Produktentwicklung) lief seit dem 16.05. nicht mehr.
    #   VP Engineering arbeitet auf claude-sonnet-5. Produktentwicklung laeuft
    #   jetzt auf gemma4-31b-it (RTX) mit gemma-4-31b-it-mlx (MacBook) als Netz.
    #   Wer wieder lokal coden will, laedt bewusst neu — nicht hier ergaenzen,
    #   ohne dass ein Agent es auch nutzt.
    set_pref "$STUDIO_ID" "Studio"
    load "text-embedding-bge-m3" "text-embedding-bge-m3"

    # --- RTX Pro 6000: Antwort-LLM des Wake-Word-Satelliten ("Hey Jarvis") ---
    #   mistral-small-3.2-24b @q4_k_m, ctx 8192 (kurze Sprach-Dialoge). Auf die
    #   RTX gepinnt: warm+schnell (~1 s) UND weicht der Studio-RAM-Contention aus,
    #   die die Mac-gemma verdraengte (22 s Kalt-Nachladen). Non-fatal: die RTX ist
    #   NACHTS AUS -> Load schlaegt dann fehl (WARN); der Satellit ist bewusst ein
    #   Tag-Dienst und faellt sonst auf sein llm.py-Fallback zurueck.
    RTX_ID="$("$LMS" link status --json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(next((p['deviceIdentifier'] for p in d.get('peers',[]) if 'RTX' in p.get('deviceName','')), ''))" 2>/dev/null)"
    if [ -n "$RTX_ID" ]; then
      set_pref "$RTX_ID" "RTX Pro 6000"
      load "mistral-small-3.2-24b-instruct-2506@q4_k_m" "mistral-small-3.2-24b-instruct-2506@q4_k_m" --context-length 8192 --parallel 4
      set_pref "$STUDIO_ID" "Studio (zurueck nach RTX-Load)"
    else
      log "RTX-Peer nicht gefunden (evtl. aus) - Satellit-Modell mistral@q4_k_m nicht vorgeladen"
    fi

    # preferred bleibt Studio: JIT bleibt bewusst AN -> Overflow landet auf der
    # Studio (Platz). Mistral ist seit 2026-07-20 oben auf dem MacBook gepinnt
    # (Agent-Primaer) und nicht mehr JIT-abhaengig.
    # Entfernt: qwen2.5-coder-14b + 0.5b-Draft (kein Agent/Workflow nutzt sie mehr).
    #
    # 2026-07-29 NAS-Archivierung: die Studio-KOPIEN von gemma-4-31b-it-mlx,
    # openbiollm-llama3-8b und dem gemma-Draft (31B-it-assistant) sind nach
    # "WHITESTAG-ARCHIV/LM Studio Modelle" ausgelagert und lokal geloescht.
    # Folge: diese drei existieren nur noch auf dem MacBook -> JIT kann sie NICHT
    # mehr auf die Studio ueberlaufen lassen (Dr-Knowledge/openbiollm laeuft damit
    # rein MacBook-abhaengig). Ist der MacBook offline, hilft nur Rueckkopieren
    # von der NAS. Auf der Studio liegen nur noch: qwen3.6-35b-a3b-mlx,
    # qwen/qwen3-coder-30b, google/gemma-4-12b, text-embedding-bge-m3.
    log "=== LM-Studio-Preload fertig (preferred=Studio, JIT an) ==="
    "$LMS" ps >>"$LMSTUDIO_LOG" 2>&1
  ' >>"$LMSTUDIO_LOG" 2>&1 &
  echo "LM Studio Preload PID: $!"
else
  echo "WARN: lms CLI nicht gefunden ($LMS) – überspringe LM-Studio-Preload."
fi

# ============================================================
# 1) Audio Player Script anlegen (falls nicht vorhanden)
# ============================================================
if [[ ! -f "$PLAYER_JS" ]]; then
  cat > "$PLAYER_JS" <<'EOF'
import http from "http";
import { spawn } from "child_process";
import fs from "fs";

const HOST = process.env.PLAYER_HOST || "127.0.0.1";
const PORT = Number(process.env.PLAYER_PORT || 8123);

function send(res, code, obj) {
  res.writeHead(code, { "Content-Type": "application/json" });
  res.end(JSON.stringify(obj));
}

http.createServer((req, res) => {
  if (req.method !== "POST" || req.url !== "/play") {
    res.writeHead(404);
    return res.end("Not found");
  }

  let body = "";
  req.on("data", c => body += c);
  req.on("end", () => {
    try {
      const payload = JSON.parse(body || "{}");
      const file = payload.file;
      const seconds = Number(payload.seconds ?? payload.playSeconds ?? 5);

      if (!file) return send(res, 400, { ok:false, error:"Missing 'file' in JSON body" });
      if (!fs.existsSync(file)) return send(res, 404, { ok:false, error:"File not found", file });

      // afplay: -t Sekunden
      spawn("afplay", ["-t", String(seconds), file], { stdio: "ignore" });
      return send(res, 200, { ok:true, playing:file, seconds });
    } catch (e) {
      return send(res, 400, { ok:false, error:"Invalid JSON body" });
    }
  });
}).listen(PORT, HOST, () => {
  console.log(`Audio player listening on http://${HOST}:${PORT}`);
});
EOF
  echo "Audio-Player Script erstellt: $PLAYER_JS"
fi

# ============================================================
# 2) Audio Player starten (falls nicht läuft)
# ============================================================
if [[ -f "$PLAYER_PIDFILE" ]] && kill -0 "$(cat "$PLAYER_PIDFILE")" >/dev/null 2>&1; then
  echo "Audio Player läuft bereits (PID $(cat "$PLAYER_PIDFILE"))."
else
  echo "Starting Audio Player on $PLAYER_HOST:$PLAYER_PORT ..."
  nohup env PLAYER_HOST="$PLAYER_HOST" PLAYER_PORT="$PLAYER_PORT" node "$PLAYER_JS" >>"$PLAYER_LOG" 2>&1 &
  echo $! > "$PLAYER_PIDFILE"
  echo "Audio Player PID: $(cat "$PLAYER_PIDFILE")"
fi

# --- Warten, bis Player lauscht ---
echo "Waiting for Audio Player to listen on $PLAYER_HOST:$PLAYER_PORT ..."
for i in {1..15}; do
  if (command -v nc >/dev/null 2>&1 && nc -z "$PLAYER_HOST" "$PLAYER_PORT" >/dev/null 2>&1) \
     || (command -v lsof >/dev/null 2>&1 && lsof -iTCP:"$PLAYER_PORT" -sTCP:LISTEN >/dev/null 2>&1); then
    echo "Audio Player is up."
    break
  fi
  sleep 1
  if [[ "$i" -eq 15 ]]; then
    echo "WARN: Audio Player scheint noch nicht zu lauschen. Prüfe Log: $PLAYER_LOG"
  fi
done

# ============================================================
# 3) Voice Agent starten (falls nicht läuft)
# ============================================================
if [[ ! -f "$AGENT_PY" ]]; then
  echo "WARN: Voice Agent nicht gefunden: $AGENT_PY"
  echo "      (Überspringe Start des Voice Agents.)"
else
  if [[ -f "$AGENT_PIDFILE" ]] && kill -0 "$(cat "$AGENT_PIDFILE")" >/dev/null 2>&1; then
    echo "Voice Agent läuft bereits (PID $(cat "$AGENT_PIDFILE"))."
  else
    if [[ ! -f "$AGENT_VENV_ACTIVATE" ]]; then
      echo "WARN: Voice-Agent venv activate nicht gefunden: $AGENT_VENV_ACTIVATE"
      echo "      (Überspringe Start des Voice Agents.)"
    else
      echo "Starting Voice Agent (Python) ..."
      nohup bash -lc "source \"$AGENT_VENV_ACTIVATE\" && python \"$AGENT_PY\"" >>"$AGENT_LOG" 2>&1 &
      echo $! > "$AGENT_PIDFILE"
      echo "Voice Agent PID: $(cat "$AGENT_PIDFILE")"
    fi
  fi
fi

# ============================================================
# 4) ComfyUI starten (falls nicht läuft)
# ============================================================
if [[ ! -d "$COMFYUI_DIR" ]]; then
  echo "WARN: ComfyUI-Verzeichnis nicht gefunden: $COMFYUI_DIR"
  echo "      (Überspringe Start von ComfyUI.)"
else
  if [[ -f "$COMFYUI_PIDFILE" ]] && kill -0 "$(cat "$COMFYUI_PIDFILE")" >/dev/null 2>&1; then
    echo "ComfyUI läuft bereits (PID $(cat "$COMFYUI_PIDFILE"))."
  else
    echo "Starting ComfyUI on 127.0.0.1:$COMFYUI_PORT ..."
    if [[ -f "$COMFYUI_VENV_ACTIVATE" ]]; then
      nohup bash -lc "source \"$COMFYUI_VENV_ACTIVATE\" && python \"$COMFYUI_DIR/main.py\" --port $COMFYUI_PORT --listen 127.0.0.1" \
        >>"$COMFYUI_LOG" 2>&1 &
    else
      nohup python3 "$COMFYUI_DIR/main.py" --port $COMFYUI_PORT --listen 127.0.0.1 \
        >>"$COMFYUI_LOG" 2>&1 &
    fi
    echo $! > "$COMFYUI_PIDFILE"
    echo "ComfyUI PID: $(cat "$COMFYUI_PIDFILE")"

    # Warten bis ComfyUI lauscht (max 60s – Modell laden braucht Zeit)
    echo "Waiting for ComfyUI to listen on 127.0.0.1:$COMFYUI_PORT ..."
    for i in {1..60}; do
      if (command -v nc >/dev/null 2>&1 && nc -z 127.0.0.1 "$COMFYUI_PORT" >/dev/null 2>&1) \
         || (command -v lsof >/dev/null 2>&1 && lsof -iTCP:"$COMFYUI_PORT" -sTCP:LISTEN >/dev/null 2>&1); then
        echo "ComfyUI is up."
        break
      fi
      sleep 1
      if [[ "$i" -eq 60 ]]; then
        echo "WARN: ComfyUI scheint noch nicht zu lauschen. Prüfe Log: $COMFYUI_LOG"
      fi
    done
  fi
fi

# ============================================================
# 5) n8n starten (falls nicht läuft)
# ============================================================
# Orphan-Schutz: prüfe ob ein n8n unter unbekannter PID auf dem Port läuft.
# Symptom: workflows failen mit "Module 'fs' is disallowed" → n8n wurde manuell
# ohne NODE_FUNCTION_ALLOW_BUILTIN gestartet. Wir stoppen ihn und starten neu.
if lsof -iTCP:"$N8N_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  RUNNING_PID=$(lsof -tiTCP:"$N8N_PORT" -sTCP:LISTEN 2>/dev/null | head -1)
  TRACKED_PID="$(cat "$N8N_PIDFILE" 2>/dev/null || echo "")"
  if [[ -n "$RUNNING_PID" && "$RUNNING_PID" != "$TRACKED_PID" ]]; then
    echo "WARN: n8n läuft auf Port $N8N_PORT unter PID $RUNNING_PID, aber PID-File ($TRACKED_PID) ist stale/leer."
    echo "      Vermutlich manuell gestartet ohne NODE_FUNCTION_ALLOW_BUILTIN → stoppe orphan n8n."
    kill "$RUNNING_PID" 2>/dev/null || true
    for i in {1..10}; do
      kill -0 "$RUNNING_PID" >/dev/null 2>&1 || break
      sleep 1
    done
    kill -9 "$RUNNING_PID" 2>/dev/null || true
    rm -f "$N8N_PIDFILE"
  fi
fi

if [[ -f "$N8N_PIDFILE" ]] && kill -0 "$(cat "$N8N_PIDFILE")" >/dev/null 2>&1; then
  echo "n8n läuft bereits (PID $(cat "$N8N_PIDFILE"))."
else
  echo "Starting n8n on $N8N_HOST:$N8N_PORT ..."
  nohup env NODE_FUNCTION_ALLOW_BUILTIN=fs,child_process,path,http,https \
      NODE_FUNCTION_ALLOW_EXTERNAL=pg,imapflow \
      N8N_CORS_ALLOWED_ORIGINS="*" \
      N8N_MIGRATE_FS_STORAGE_PATH=true \
      N8N_SECURE_COOKIE=false \
      EXECUTIONS_TIMEOUT=-1 \
      N8N_RUNNERS_TASK_TIMEOUT=86400 \
      N8N_UNVERIFIED_PACKAGES_ENABLED=true \
      n8n start --host "$N8N_HOST" --port "$N8N_PORT" >>"$N8N_LOG" 2>&1 &
  echo $! > "$N8N_PIDFILE"
  echo "n8n PID: $(cat "$N8N_PIDFILE")"
fi

# --- Warten, bis n8n lauscht ---
echo "Waiting for n8n to listen on $N8N_HOST:$N8N_PORT ..."
for i in {1..30}; do
  if (command -v nc >/dev/null 2>&1 && nc -z "$N8N_HOST" "$N8N_PORT" >/dev/null 2>&1) \
     || (command -v lsof >/dev/null 2>&1 && lsof -iTCP:"$N8N_PORT" -sTCP:LISTEN >/dev/null 2>&1); then
    echo "n8n is up."
    break
  fi
  sleep 1
  if [[ "$i" -eq 30 ]]; then
    echo "WARN: n8n scheint noch nicht zu lauschen. Prüfe Log: $N8N_LOG"
  fi
done

# ============================================================
# 6) CCC-Film Backend starten (falls nicht läuft)
# ============================================================
if [[ ! -d "$CCCFILM_DIR" ]]; then
  echo "WARN: CCC-Film Backend nicht gefunden: $CCCFILM_DIR"
  echo "      (Überspringe Start des CCC-Film Backends.)"
else
  if [[ -f "$CCCFILM_PIDFILE" ]] && kill -0 "$(cat "$CCCFILM_PIDFILE")" >/dev/null 2>&1; then
    echo "CCC-Film Backend läuft bereits (PID $(cat "$CCCFILM_PIDFILE"))."
  else
    echo "Starting CCC-Film Backend auf Port $CCCFILM_PORT ..."
    nohup bash -c "cd \"$CCCFILM_DIR\" && node server.js" >>"$CCCFILM_LOG" 2>&1 &
    echo $! > "$CCCFILM_PIDFILE"
    echo "CCC-Film PID: $(cat "$CCCFILM_PIDFILE")"

    echo "Waiting for CCC-Film to listen on 127.0.0.1:$CCCFILM_PORT ..."
    for i in {1..15}; do
      if lsof -iTCP:"$CCCFILM_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
        echo "CCC-Film is up."
        break
      fi
      sleep 1
      if [[ "$i" -eq 15 ]]; then
        echo "WARN: CCC-Film scheint noch nicht zu lauschen. Prüfe Log: $CCCFILM_LOG"
      fi
    done
  fi
fi

# ============================================================
# 7) Paperclip starten (falls nicht läuft)
# ============================================================
if [[ ! -d "$PAPERCLIP_DIR" ]]; then
  echo "WARN: Paperclip-Verzeichnis nicht gefunden: $PAPERCLIP_DIR"
  echo "      (Überspringe Start von Paperclip.)"
elif lsof -iTCP:"$PAPERCLIP_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Paperclip läuft bereits auf Port $PAPERCLIP_PORT (vermutlich launchd-Agent 'ing.paperclip.dev')."
  echo "  → Stop: launchctl bootout gui/\$(id -u) ~/Library/LaunchAgents/ing.paperclip.dev.plist"
else
  if [[ -f "$PAPERCLIP_PIDFILE" ]] && kill -0 "$(cat "$PAPERCLIP_PIDFILE")" >/dev/null 2>&1; then
    echo "Paperclip läuft bereits (PID $(cat "$PAPERCLIP_PIDFILE"))."
  else
    echo "Starting Paperclip auf Port $PAPERCLIP_PORT (LAN: 0.0.0.0) ..."
    nohup bash -lc "source \"$NVM_DIR/nvm.sh\" && nvm use $NODE_VERSION >/dev/null 2>&1 && cd \"$PAPERCLIP_DIR\" && PAPERCLIP_ALLOWED_HOSTNAMES=192.168.2.191,company.whitestag.ai PAPERCLIP_UI_DEV_MIDDLEWARE=false pnpm dev:once --bind lan --bind-host 0.0.0.0" \
      >>"$PAPERCLIP_LOG" 2>&1 &
    echo $! > "$PAPERCLIP_PIDFILE"
    echo "Paperclip PID: $(cat "$PAPERCLIP_PIDFILE")"

    echo "Waiting for Paperclip to listen on 127.0.0.1:$PAPERCLIP_PORT ..."
    for i in {1..60}; do
      if (command -v nc >/dev/null 2>&1 && nc -z 127.0.0.1 "$PAPERCLIP_PORT" >/dev/null 2>&1) \
         || (command -v lsof >/dev/null 2>&1 && lsof -iTCP:"$PAPERCLIP_PORT" -sTCP:LISTEN >/dev/null 2>&1); then
        echo "Paperclip is up."
        break
      fi
      sleep 1
      if [[ "$i" -eq 60 ]]; then
        echo "WARN: Paperclip scheint noch nicht zu lauschen. Prüfe Log: $PAPERCLIP_LOG"
      fi
    done
  fi
fi

# ============================================================
# 8) Cannabis Grow Manager starten (falls nicht läuft)
# ============================================================
if [[ ! -d "$CANNABIS_DIR" ]]; then
  echo "WARN: Cannabis-GUI-Verzeichnis nicht gefunden: $CANNABIS_DIR"
  echo "      (Überspringe Start des Cannabis Grow Managers.)"
else
  if [[ -f "$CANNABIS_PIDFILE" ]] && kill -0 "$(cat "$CANNABIS_PIDFILE")" >/dev/null 2>&1; then
    echo "Cannabis Grow Manager läuft bereits (PID $(cat "$CANNABIS_PIDFILE"))."
  else
    echo "Starting Cannabis Grow Manager auf Port $CANNABIS_PORT ..."
    nohup bash -c "cd \"$CANNABIS_DIR\" && PORT=$CANNABIS_PORT node server.js" >>"$CANNABIS_LOG" 2>&1 &
    echo $! > "$CANNABIS_PIDFILE"
    echo "Cannabis PID: $(cat "$CANNABIS_PIDFILE")"

    echo "Waiting for Cannabis Grow Manager to listen on 127.0.0.1:$CANNABIS_PORT ..."
    for i in {1..15}; do
      if lsof -iTCP:"$CANNABIS_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
        echo "Cannabis Grow Manager is up."
        break
      fi
      sleep 1
      if [[ "$i" -eq 15 ]]; then
        echo "WARN: Cannabis Grow Manager scheint noch nicht zu lauschen. Prüfe Log: $CANNABIS_LOG"
      fi
    done
  fi
fi

# ============================================================
# 9) KI-Kompass App (Expo Web) starten (falls nicht läuft)
# ============================================================
if [[ ! -d "$KIKOMPASS_DIR" ]]; then
  echo "WARN: KI-Kompass-Verzeichnis nicht gefunden: $KIKOMPASS_DIR"
  echo "      (Überspringe Start der KI-Kompass App.)"
elif lsof -iTCP:"$KIKOMPASS_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "KI-Kompass App läuft bereits auf Port $KIKOMPASS_PORT."
else
  if [[ -f "$KIKOMPASS_PIDFILE" ]] && kill -0 "$(cat "$KIKOMPASS_PIDFILE")" >/dev/null 2>&1; then
    echo "KI-Kompass App läuft bereits (PID $(cat "$KIKOMPASS_PIDFILE"))."
  else
    echo "Starting KI-Kompass App (Expo Web) auf Port $KIKOMPASS_PORT ..."
    nohup bash -lc "source \"$NVM_DIR/nvm.sh\" && nvm use $NODE_VERSION >/dev/null 2>&1 && cd \"$KIKOMPASS_DIR\" && npm run web" \
      >>"$KIKOMPASS_LOG" 2>&1 &
    echo $! > "$KIKOMPASS_PIDFILE"
    echo "KI-Kompass PID: $(cat "$KIKOMPASS_PIDFILE")"

    echo "Waiting for KI-Kompass to listen on 127.0.0.1:$KIKOMPASS_PORT ..."
    for i in {1..60}; do
      if (command -v nc >/dev/null 2>&1 && nc -z 127.0.0.1 "$KIKOMPASS_PORT" >/dev/null 2>&1) \
         || (command -v lsof >/dev/null 2>&1 && lsof -iTCP:"$KIKOMPASS_PORT" -sTCP:LISTEN >/dev/null 2>&1); then
        echo "KI-Kompass is up."
        break
      fi
      sleep 1
      if [[ "$i" -eq 60 ]]; then
        echo "WARN: KI-Kompass scheint noch nicht zu lauschen. Prüfe Log: $KIKOMPASS_LOG"
      fi
    done
  fi
fi

sleep 2

# --- Browser öffnen ---
echo "Opening n8n locally..."
open "http://$N8N_HOST:$N8N_PORT" >/dev/null 2>&1 || true
echo "Opening Paperclip locally..."
open "http://127.0.0.1:$PAPERCLIP_PORT" >/dev/null 2>&1 || true
echo "Opening CCC-Film locally..."
open "http://127.0.0.1:$CCCFILM_PORT" >/dev/null 2>&1 || true
echo "Opening KI-Kompass App in Chrome (eigener Reiter)..."
# Chrome zuerst sicher starten (sonst schluckt der Session-Restore die URL),
# kurz warten, dann die URL als Reiter öffnen.
open -a "Google Chrome" >/dev/null 2>&1 || true
sleep 1
open -a "Google Chrome" "http://localhost:$KIKOMPASS_PORT" >/dev/null 2>&1 || true

echo
echo "========================================"
echo " Started"
echo "========================================"
echo "n8n local     : http://$N8N_HOST:$N8N_PORT"
echo "audio player  : http://$PLAYER_HOST:$PLAYER_PORT/play"
echo "comfyui       : http://127.0.0.1:$COMFYUI_PORT"
echo "ccc-film      : http://127.0.0.1:$CCCFILM_PORT"
echo "paperclip     : http://127.0.0.1:$PAPERCLIP_PORT"
echo "cannabis      : http://127.0.0.1:$CANNABIS_PORT"
echo "ki-kompass    : http://localhost:$KIKOMPASS_PORT  (Chrome-Reiter)"
echo "voice agent   : $AGENT_PY"
echo
echo "Logs:"
echo "  lmstudio: $LMSTUDIO_LOG"
echo "  n8n     : $N8N_LOG"
echo "  player  : $PLAYER_LOG"
echo "  agent   : $AGENT_LOG"
echo "  comfyui : $COMFYUI_LOG"
echo "  ccc-film: $CCCFILM_LOG"
echo "  cannabis: $CANNABIS_LOG"
echo "  paperclip: $PAPERCLIP_LOG"
echo "  ki-kompass: $KIKOMPASS_LOG"
echo
echo "Stop:"
echo "  kill \$(cat \"$PLAYER_PIDFILE\") ; kill \$(cat \"$N8N_PIDFILE\") ; kill \$(cat \"$AGENT_PIDFILE\") ; kill \$(cat \"$COMFYUI_PIDFILE\") ; kill \$(cat \"$CCCFILM_PIDFILE\") ; kill \$(cat \"$CANNABIS_PIDFILE\") ; kill \$(cat \"$PAPERCLIP_PIDFILE\") ; kill \$(cat \"$KIKOMPASS_PIDFILE\")"
echo "========================================"