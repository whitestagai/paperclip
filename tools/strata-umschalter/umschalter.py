#!/usr/bin/env python3
"""Strata-Umschalter: VP Engineering laeuft auf Strata, wenn es erreichbar ist, sonst auf Claude.

Strata (qwen3.8-flash-next auf dem Film-Rechner, 192.168.2.181:1235) laeuft nur, solange
Walter am Windows-Rechner angemeldet ist. Der claude_local-Adapter kennt keine
Ausweichadresse — faellt Strata weg, scheitert jeder Lauf. Dieses Skript prueft alle
5 Minuten (launchd) `/health` und stellt VP Engineering per Paperclip-API um:

- Strata weg (drei Proben in Folge scheitern)  -> sofort auf Claude
- Strata da (zwei Durchlaeufe in Folge gesund) -> zurueck auf Strata, aber nur, wenn
  der Agent gerade keinen Lauf hat

Bei jedem Wechsel werden die Claude-Sitzungen des Agenten zurueckgesetzt: eine Sitzung,
die auf dem einen Modell begonnen wurde, darf nicht auf dem anderen fortgesetzt werden
(fremde Thinking-Signaturen lehnt die Anthropic-API ab, und der Lauf scheitert dann bei
jeder Wiederaufnahme erneut).

Hat jemand die Konfiguration von Hand auf etwas Drittes gestellt, haelt das Skript still.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime

AGENT_ID = "5563514c-4254-48d5-9339-802172304119"  # WHITESTAG / VP Engineering
API = "http://localhost:3100/api"
AUTH_FILE = os.path.expanduser("~/.paperclip/auth.json")
STRATA_BASE = "http://192.168.2.181:1235"
HERE = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(HERE, "state.json")
LOG_FILE = os.path.expanduser("~/.paperclip/logs/strata-umschalter.log")

# Env-Schluessel, die nur im Strata-Betrieb gesetzt sind. ANTHROPIC_AUTH_TOKEN verdraengt
# Walters claude.ai-Login, damit dessen OAuth-Token nicht an den Windows-Rechner geht.
STRATA_ENV_KEYS = (
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC",
)
FAILS_TO_CLAUDE = 1   # Durchlaeufe; jeder Durchlauf probt bereits dreimal
OKS_TO_STRATA = 2


def plain(value):
    return {"type": "plain", "value": value}


def env_value(cfg, key):
    v = (cfg.get("env") or {}).get(key)
    if isinstance(v, dict):
        return v.get("value")
    return v


# --- reine Logik (getestet) ---

def detect_mode(cfg, claude_profile):
    """'strata', 'claude' oder 'fremd' (von Hand auf etwas Drittes gestellt)."""
    base = env_value(cfg, "ANTHROPIC_BASE_URL")
    if base == STRATA_BASE:
        return "strata"
    if (claude_profile
            and cfg.get("model") == claude_profile["model"]
            and base == env_value(claude_profile, "ANTHROPIC_BASE_URL")
            and not any(k in (cfg.get("env") or {}) for k in STRATA_ENV_KEYS)):
        return "claude"
    return "fremd"


def strata_patch(cfg, model):
    env = {k: v for k, v in (cfg.get("env") or {}).items() if k not in STRATA_ENV_KEYS}
    env["ANTHROPIC_BASE_URL"] = plain(STRATA_BASE)
    env["ANTHROPIC_AUTH_TOKEN"] = plain("strata-local")
    for k in ("ANTHROPIC_DEFAULT_HAIKU_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL",
              "ANTHROPIC_DEFAULT_OPUS_MODEL"):
        env[k] = plain(model)
    env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = plain("1")
    return {"model": model, "env": env}


def claude_patch(cfg, claude_profile):
    env = {k: v for k, v in (cfg.get("env") or {}).items() if k not in STRATA_ENV_KEYS}
    env.update(claude_profile.get("env") or {})
    return {"model": claude_profile["model"], "env": env}


def decide(state, healthy, strata_model, mode, agent_running, current_model):
    """Liefert (aktion, neuer_state). aktion: None | 'to_claude' | 'to_strata'."""
    st = dict(state)
    if healthy:
        st["oks"] = st.get("oks", 0) + 1
        st["fails"] = 0
    else:
        st["fails"] = st.get("fails", 0) + 1
        st["oks"] = 0
    if mode == "fremd":
        return None, st
    if mode == "strata" and not healthy and st["fails"] >= FAILS_TO_CLAUDE:
        return "to_claude", st
    if mode == "strata" and healthy and strata_model and current_model != strata_model \
            and not agent_running:
        return "to_strata", st   # anderes Modell in Strata geladen -> ID nachziehen
    if mode == "claude" and healthy and st["oks"] >= OKS_TO_STRATA and not agent_running:
        return "to_strata", st
    return None, st


# --- Ein-/Ausgabe ---

def log(msg):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().isoformat(timespec='seconds')} {msg}\n")


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(st):
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, indent=2, ensure_ascii=False)
    os.replace(tmp, STATE_FILE)


def probe_strata(tries=3, pause=10):
    """Modell-ID bei gesundem Strata, sonst None."""
    for i in range(tries):
        try:
            with urllib.request.urlopen(STRATA_BASE + "/health", timeout=5) as r:
                d = json.load(r)
            if d.get("status") == "ok" and d.get("loaded") and d.get("model"):
                return d["model"]
        except (OSError, ValueError, urllib.error.URLError):
            pass
        if i < tries - 1:
            time.sleep(pause)
    return None


def board_token():
    with open(AUTH_FILE, encoding="utf-8") as f:
        return json.load(f)["credentials"]["http://localhost:3100"]["token"]


def api(method, path, body=None):
    req = urllib.request.Request(
        API + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {board_token()}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def switch(agent, patch, label):
    api("PATCH", f"/agents/{AGENT_ID}", {"adapterConfig": patch})
    api("POST", f"/agents/{AGENT_ID}/runtime-state/reset-session", {})
    log(f"UMGESCHALTET -> {label}: model={patch['model']} base="
        f"{patch['env']['ANTHROPIC_BASE_URL']['value']} (Sitzungen zurueckgesetzt)")


def main():
    st = load_state()
    agent = api("GET", f"/agents/{AGENT_ID}")
    cfg = agent.get("adapterConfig") or {}

    # Claude-Profil einmalig aus dem Ist-Stand festhalten, solange der Agent noch auf Claude steht.
    if "claude_profile" not in st:
        if env_value(cfg, "ANTHROPIC_BASE_URL") == STRATA_BASE:
            log("FEHLER: kein Claude-Profil gespeichert und Agent steht schon auf Strata — Abbruch")
            return 2
        st["claude_profile"] = {
            "model": cfg.get("model"),
            "env": {"ANTHROPIC_BASE_URL": (cfg.get("env") or {}).get("ANTHROPIC_BASE_URL")},
        }
        log(f"Claude-Profil festgehalten: {json.dumps(st['claude_profile'], ensure_ascii=False)}")

    model = probe_strata()
    mode = detect_mode(cfg, st["claude_profile"])
    running = agent.get("status") == "running"
    action, st = decide(st, model is not None, model, mode, running, cfg.get("model"))

    if mode == "fremd" and st.get("last_mode") != "fremd":
        log(f"Konfiguration von Hand geaendert (model={cfg.get('model')}, base="
            f"{env_value(cfg, 'ANTHROPIC_BASE_URL')}) — Umschalter haelt still")
    if action == "to_claude":
        switch(agent, claude_patch(cfg, st["claude_profile"]), "Claude (Strata nicht erreichbar)")
        mode = "claude"
    elif action == "to_strata":
        switch(agent, strata_patch(cfg, model), "Strata")
        mode = "strata"
    elif mode == "claude" and model and running and st["oks"] >= OKS_TO_STRATA:
        if not st.get("warte_geloggt"):
            log("Strata gesund, aber VP Engineering hat einen laufenden Lauf — Wechsel wartet")
            st["warte_geloggt"] = True
    if action:
        st.pop("warte_geloggt", None)
    st["last_mode"] = mode
    st["last_check"] = datetime.now().isoformat(timespec="seconds")
    st["last_strata_model"] = model
    save_state(st)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # launchd: Fehler ins Log, nicht ins Leere
        log(f"FEHLER: {type(e).__name__}: {e}")
        sys.exit(1)
