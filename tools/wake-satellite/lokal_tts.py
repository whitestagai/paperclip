# tools/wake-satellite/lokal_tts.py
"""Text -> WAV über Phonon, lokal in Ollama (stdlib only).

Nur der Satellit spricht so; der Telegram-Jarvis bleibt bei ElevenLabs
(`tts.py` ist geteilt und deshalb unberührt). Fehler werden als
`tts.TtsError` gemeldet, damit der Aufrufer auf ElevenLabs ausweichen kann."""
import json
import os
import urllib.error
import urllib.request

import sat_config
from tts import TtsError


def synthesize(text, dest):
    """Synthetisiert `text` mit der Phonon-Stimme nach `dest` (WAV).

    Gibt `dest` zurück. Wirft TtsError bei leerem Text, Netz-/HTTP-Fehler oder
    einer Antwort, die kein WAV ist — dann bleibt keine Datei liegen.
    """
    text = (text or "").strip()
    if not text:
        raise TtsError("empty text")

    body = json.dumps({"model": sat_config.LOKAL_TTS_MODEL, "input": text,
                       "voice": sat_config.LOKAL_TTS_STIMME,
                       "response_format": "wav"}).encode("utf-8")
    req = urllib.request.Request(sat_config.LOKAL_TTS_URL, data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=sat_config.LOKAL_TTS_TIMEOUT_SEC) as resp:
            audio = resp.read()
    except urllib.error.HTTPError as exc:
        raise TtsError("Phonon HTTP {}".format(exc.code)) from exc
    except (urllib.error.URLError, OSError) as exc:
        raise TtsError("Phonon request failed: {}".format(exc)) from exc

    if not audio.startswith(b"RIFF"):
        raise TtsError("Phonon returned no WAV: {!r}".format(audio[:80]))
    try:
        with open(dest, "wb") as out:
            out.write(audio)
    except OSError as exc:
        try:
            os.remove(dest)
        except OSError:
            pass
        raise TtsError("failed to write audio: {}".format(exc)) from exc
    return dest
