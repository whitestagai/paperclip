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
# Nur noch das Format des ElevenLabs-Rückfalls (siehe unten).
TTS_FORMAT = "mp3_44100_128"

# Stimme: Phonon (deutsches 40M-TTS) lokal in Ollama auf dem Studio, seit
# 26.10.2026 statt ElevenLabs. Walter hat aus 13 deutschen Stimmen „Anton"
# gewählt. Gemessen: 6-10 s Sprache in 0,1-0,2 s erzeugt, kalt ~2,3 s; Whisper
# las alle Proben wortgleich zurück. ElevenLabs bleibt das Netz, falls Ollama
# nicht läuft oder das Modell fehlt (`ollama pull phonon:40m-de`).
# Ausgabe ist WAV — afplay spielt sie direkt, AirPlay streamt den Systemton.
LOKAL_TTS_URL = "http://127.0.0.1:11434/v1/audio/speech"
LOKAL_TTS_MODEL = "phonon:40m-de"
LOKAL_TTS_STIMME = "Anton"
LOKAL_TTS_TIMEOUT_SEC = 20

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
#
# 22.08.2026 auf die GGUF-Q8-Kopie derselben Gemma umgestellt, die jetzt auf
# der RTX liegt. Gleiches Modell, gleiche Sprachqualitaet, nur schneller —
# unter laufender Flottenlast gemessen (dieselben drei Fragen, ohne
# max_tokens, deshalb hoeher als die Werte oben):
#   gemma4-31b-it (RTX)              19,3 / 9,7 / 6,3 s
#   gemma-4-31b-it-mlx (MacBook)    108,1 / 32,0 /  -   s
# Das MacBook traegt weiterhin 7 aktive n8n-Workflows, zwei Reports und den
# Fallback von 14 Agenten bei ~2 GB freiem RAM; daher der Einbruch.
#
# NEBENEFFEKT auf den Fallback in llm.chat(): CHAT_MODEL ist jetzt NICHT mehr
# gleich llm.FALLBACK_MODEL, also greift kein Ausweichen auf DEFAULT_MODEL
# mehr — das Netz ist ab sofort `gemma-4-31b-it-mlx` auf dem MacBook. Also
# gleiche Modellqualitaet im Fallback statt Abstieg auf die 12b, und weiterhin
# ein ANDERES Geraet als der Primaerpfad. Zurueck geht es mit einer Zeile.
#
# 15.09.2026: Die ID war "gemma4-31b-it" — der Bindestrich nach "gemma" fehlte.
# LM Studio kennt sie nicht und antwortet auf JEDEN Aufruf mit «Invalid model
# identifier», der Sprachpfad lief also ins Leere.
#
# 04.10.2026: GENAU DASSELBE WIEDER — diesmal hiess die ID "gemma-4-31b-it",
# und auch die kennt LM Studio nicht mehr. Das Modell heisst "google/gemma-4-31b".
# Gegengeprobt: `GET /api/v0/models/google/gemma-4-31b` -> 200, die alte ID -> 400.
# Der Satellit lief mit der toten ID und dem laufenden launchd-Job
# `de.whitestag.wake-satellite` — ein stiller Ausfall des Sprachpfads.
# Es war der sechste Fundort derselben Umbenennung (27 Agenten-Konfigurationen,
# 11 cheap-Profile, 6 n8n-Workflows, zwei Soll-Dateien der Modell-Aufsicht).
#
# KORREKTUR zum Absatz oben: dort steht, das Netz sei `gemma-4-31b-it-mlx` auf
# dem MacBook. Das stimmt nicht — `llm.py` setzt FALLBACK_MODEL und DEFAULT_MODEL
# beide auf `google/gemma-4-12b`. Der Fallback ist also die 12B, nicht ein
# zweites 31B. Wer das aendern will, aendert llm.py, nicht diesen Kommentar.
CHAT_MODEL = "google/gemma-4-31b"

# 26.10.2026: Die Studio-gemma DENKT vor jeder Antwort (Reasoning), das war
# der Großteil der 22-201 s Antwortzeit. Gemessen an derselben Frage:
#   ohne Schalter            31,1 s  (259 von 302 Tokens Reasoning)
#   reasoning_effort="none"   2,9-4,4 s  (0 Reasoning-Tokens)
# `chat_template_kwargs.enable_thinking=False` wirkt bei LM Studio NICHT
# (21,8 s, 199 Reasoning-Tokens). Für gesprochene Kurzantworten bringt das
# Nachdenken nichts; None schaltet zurück auf das Modellverhalten.
CHAT_REASONING_EFFORT = "none"

# Mandant fest verdrahtet.
TENANT = {
    "name": "Walter / WHITESTAG",
    "company_id": "9cebf3cf-efe8-4597-a400-f06488900a87",
    "ceo_agent_id": "506c873e-3a40-4483-9a45-0eb0fa1554bb",
    "vault": "whitestag",
}
