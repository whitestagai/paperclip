"""Konfiguration für den Voice-Echo Jarvis-Bot (stdlib only)."""
import json
import os

PAPERCLIP_BASE = os.environ.get("PAPERCLIP_API_URL", "http://127.0.0.1:3100").rstrip("/")
API_BASE = f"{PAPERCLIP_BASE}/api"
AUTH_JSON = os.path.expanduser("~/.paperclip/auth.json")
ENV_PATH = os.path.expanduser("~/.paperclip/voice-echo-bot.env")
WHITESTAG_ENV = os.path.expanduser("~/.whitestag.env")


def load_env(path):
    """Parst eine einfache KEY="value"-Env-Datei zu einem dict."""
    env = {}
    with open(path, "r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[len("export "):]
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                env[key] = value
    return env


def load_paperclip_token(auth_path=AUTH_JSON):
    """Liest das Board-Token aus der auth.json (auto-renewt)."""
    with open(auth_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    creds = data["credentials"]
    # auth.json ist nach der Ausstellungs-URL geschluesselt: erst die
    # konfigurierte Adresse, dann die historischen Schreibweisen, zuletzt
    # der einzige Eintrag.
    for _key in (PAPERCLIP_BASE, "http://localhost:3100", "http://127.0.0.1:3100"):
        if _key in creds:
            return creds[_key]["token"]
    if len(creds) == 1:
        return next(iter(creds.values()))["token"]
    raise KeyError(f"Kein Token fuer {PAPERCLIP_BASE} in der auth.json")


# --- Rückkanal + Mehrmandanten ---
TENANTS_PATH = os.path.expanduser("~/.paperclip/voice-echo-tenants.json")
STATE_PATH = os.path.expanduser("~/.paperclip/voice-echo-state.json")
DECISION_LABEL = "entscheidung-noetig"
POLL_INTERVAL_SEC = 60
LONGPOLL_TIMEOUT_SEC = 25

# --- Academy-Auto-Brücke ---
ACADEMY_INTENT_PATH = os.path.expanduser("~/.paperclip/academy-auto/intent.json")
ACADEMY_AUTO_DIR = os.path.expanduser("~/.paperclip/scripts/academy-auto")

# --- Antwort-Modus (Text/Voice) + ElevenLabs-TTS ---
REPLY_MODE_PATH = os.path.expanduser("~/.paperclip/voice-echo-reply-mode.json")
ELEVEN_VOICE_ID = "fzqS9sNPYJhLlhsfDm0l"
ELEVEN_MODEL = "eleven_turbo_v2_5"
ELEVEN_LANGUAGE = "de"  # feste Sprache — verhindert Auto-Sprachwechsel bei Namen/Zahlen
ELEVEN_TTS_BASE = (
    "https://api.elevenlabs.io/v1/text-to-speech/" + ELEVEN_VOICE_ID
)
ELEVEN_OUTPUT_FORMAT_DEFAULT = "opus_48000_64"
# Rückwärtskompatibel: bestehender Voll-URL-Name bleibt erhalten.
ELEVEN_TTS_URL = ELEVEN_TTS_BASE + "?output_format=" + ELEVEN_OUTPUT_FORMAT_DEFAULT

# --- SEO/GEO-Freigaben ---
SEO_APPROVALS_DIR = os.path.expanduser("~/.paperclip/state/seo-approvals")
SEO_GEO_VENV = os.path.expanduser("~/.paperclip/scripts/seo-geo/venv/bin/python")
SEO_GEO_CLI = os.path.expanduser("~/.paperclip/scripts/seo-geo/cli.py")
SEO_GEO_ROOT = "~/.paperclip/seo-geo"
SEO_GEO_SITES = os.path.expanduser("~/.paperclip/scripts/seo-geo/sites.json")
WALTER_CHAT_ID = 8311805232
