# tools/wake-satellite/sat_config.py
"""Konstanten des Wake-Word-Satelliten (Walter / WHITESTAG, Mac Studio)."""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

WAKE_THRESHOLD = 0.5
# openwakeword lädt .tflite-Modelle nur über das eigenständige Paket
# `tflite_runtime` — auf macOS arm64 gibt es dafür kein Wheel. Deshalb ONNX-
# Backend (onnxruntime, kommt als openwakeword-Abhängigkeit mit). "hey_jarvis"
# ist ein offizielles openwakeword-Modell; deploy.sh lädt via download_models
# die passenden .onnx (Wakeword + Feature-Modelle) in den openwakeword-
# Ressourcenordner, von wo der Kurzname aufgelöst wird.
INFERENCE_FRAMEWORK = "onnx"
WAKE_MODELS = ["hey_jarvis"]
# Ein einzelner Frame über der Schwelle ist ein Ausreißer, kein Wake-Wort: ein
# echtes „Hey Jarvis" liegt über mehrere 80-ms-Frames hinweg oben. Zwei Treffer
# in Folge kosten 80 ms Latenz und sieben einen Großteil der Fehlalarme aus.
WAKE_REQUIRED_HITS = 2

SAMPLE_RATE = 16000
FRAME_SAMPLES = 1280
# Rollender Audio-Vorpuffer: die letzten ~1,2 s VOR dem Wake-Treffer werden
# der Aufnahme vorangestellt, damit ein flüssig gesprochenes „Hey Jarvis, <Befehl>"
# nicht am Anfang abgeschnitten wird (Wake-Erkennungs-Latenz + Bestätigungston).
PREROLL_SEC = 1.2
PREROLL_FRAMES = int(PREROLL_SEC * SAMPLE_RATE / FRAME_SAMPLES)  # ~15
# Nachfrage-Fenster ohne Wake-Word: wie lange nach Jarvis' Antwort auf einen
# Sprachbeginn gewartet wird. Waren es 2,5 s, kam Walter fast nie hinterher —
# seine Antwort spielt allein schon 4-7 s, und danach muss er den Satz erst
# anfangen. 5 s ist der Kompromiss: lang genug zum Nachfassen, kurz genug,
# dass am Schreibtisch nicht jedes Nebengespräch aufgeschnappt wird.
FOLLOWUP_START_FENSTER_SEC = 5.0
FOLLOWUP_START_FENSTER_FRAMES = int(FOLLOWUP_START_FENSTER_SEC * SAMPLE_RATE / FRAME_SAMPLES)  # ~62

# Nach der Quittung („Ja?") darf es deutlich länger dauern: hier hat Walter das
# Wake-Wort bewusst allein gesagt und formuliert seine Frage erst noch.
ANREDE_START_FENSTER_SEC = 8.0
ANREDE_START_FENSTER_FRAMES = int(ANREDE_START_FENSTER_SEC * SAMPLE_RATE / FRAME_SAMPLES)  # ~100

# So viele zusammenhängende laute Frames müssen es sein, damit eine Aufnahme
# OHNE Wake-Wort startet (~0,24 s) — sonst startet ein Türklappen die Aufnahme.
# Gilt nicht für die erste Runde: die ist bereits durch das Wake-Wort gedeckt.
MIN_START_RUN_FRAMES = 3
# Deckel für die Nachfrage-Kette: nach so vielen Antworten ist ohne erneutes
# Wake-Wort Schluss. Ohne Deckel hält ein Gespräch im Raum die Schleife
# beliebig lange am Leben und Jarvis beantwortet alles Gesagte.
MAX_TURNS_PER_WAKE = 3
PLAYBACK_COOLDOWN_SEC = 1.0
MAX_HISTORY_MESSAGES = 16

# macOS bündelt AirPlay-Ausgaben unter dem einen CoreAudio-Gerät "AirPlay",
# das an das zuletzt gewählte AirPlay-Ziel (hier: HomePod Studio) routet. Ein
# per-Gerätename "Homepod Studio" existiert nicht als Ausgabegerät.
HOMEPOD_DEVICE = "AirPlay"
TTS_FORMAT = "mp3_44100_128"

# Antwort-LLM: Mistral-Small-24B (Q4) resident auf der RTX Pro 6000 (ctx 8192)
# → schnell (~1 s) UND deutlich bessere Antwortqualität als die 12B-gemma-qat.
# Auf der RTX, damit es nicht unter Studio-RAM-Contention verdrängt wird. Nur
# der Satellit nutzt es; der Telegram-Jarvis bleibt auf seinem Env-/Default-
# Modell. Modell muss geladen sein: `lms load "<ID>" --context-length 8192`.
#
# 17.08.2026 auf gemma-4-31b umgestellt (Walters Wunsch): es formuliert
# gesprochenes Deutsch natuerlicher. Der Preis ist gemessen und bewusst:
#   mistral-small-24b (RTX, lokal)  1,8 / 0,9 / 0,9 s
#   gemma-4-31b-it-mlx (MacBook)    4,1 / 3,2 / 3,2 s
# Das Modell liegt auf dem MacBook (`lms ps` -> MacbookM5Mx128), der
# Sprachpfad haengt damit an LM Link statt nur am Studio. Abgefedert durch
# den Fallback in llm.chat(): weil CHAT_MODEL hier == llm.FALLBACK_MODEL
# ist, weicht der Modul-Default auf llm.DEFAULT_MODEL aus — ein lokales
# Netz unter dem entfernten Modell. Zurueck geht es mit einer Zeile.
CHAT_MODEL = "gemma-4-31b-it-mlx"

# Mandant fest verdrahtet.
TENANT = {
    "name": "Walter / WHITESTAG",
    "company_id": "9cebf3cf-efe8-4597-a400-f06488900a87",
    "ceo_agent_id": "506c873e-3a40-4483-9a45-0eb0fa1554bb",
    "vault": "whitestag",
}
