# tools/wake-satellite/quittung.py
"""Kurze Quittung „Ja?" — das Signal „ich höre jetzt zu".

Fällt an, sobald nach dem Wake-Wort nur die Anrede kam (siehe `anrede.py`).
Weil das bei JEDEM zögernden „Hey Jarvis …" passiert, wird die Sprachdatei
genau einmal von ElevenLabs gerendert und danach von der Platte gespielt:
kein API-Aufruf, keine Wartezeit, kein Kontingent. Ist das nicht möglich
(kein Schlüssel, ElevenLabs down), kommt ein Piepton — bewusst mit anderer
Frequenz als der Wake-Ton, damit „hab dich gehört" und „ich höre jetzt zu"
unterscheidbar bleiben. Nie fatal: Schweigen wäre das schlechteste Ergebnis."""
import os
import traceback

import earcon
import lokal_tts
import playback
import sat_config
import tts

DEFAULT_PATH = os.path.expanduser("~/.paperclip/wake-satellite/quittung.mp3")
# Seit 26.10.2026 zuerst in der Phonon-Stimme der Antworten; ElevenLabs
# (DEFAULT_PATH) nur noch, wenn Phonon nicht zu haben ist. Die Stimme steht im
# Dateinamen, damit ein Stimmwechsel neu rendert statt die alte zu spielen.
LOKAL_PATH = os.path.expanduser("~/.paperclip/wake-satellite/quittung-phonon-{}.wav".format(
    sat_config.LOKAL_TTS_STIMME.lower()))
TEXT = "Ja?"
FORMAT = "mp3_44100_128"

# Rückfallton: tiefer als der 880-Hz-Wake-Ton aus earcon.py.
TON_PATH = os.path.expanduser("~/.paperclip/wake-satellite/quittung-ton.wav")
TON_FREQ = 520


def _render_einmal(path, render):
    """Pfad zur zwischengespeicherten Datei; ruft `render(tmp)` beim ersten Mal.
    None, wenn das Rendern scheitert.

    Geschrieben wird über eine temporäre Datei und `os.replace`: eine halb
    geschriebene Datei würde beim nächsten Start als fertig gelten und die
    Quittung für immer stumm schalten.
    """
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = path + ".tmp"
    try:
        render(tmp)
        os.replace(tmp, path)
        return path
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        try:
            os.remove(tmp)
        except OSError:
            pass
        return None


def ensure_audio(api_key, path=DEFAULT_PATH, text=TEXT, output_format=FORMAT):
    """Quittung in der ElevenLabs-Stimme. None ohne Schlüssel oder bei Fehler."""
    if not (os.path.exists(path) and os.path.getsize(path) > 0) and not api_key:
        return None
    return _render_einmal(
        path, lambda tmp: tts.synthesize(text, api_key, tmp, output_format=output_format))


def ensure_lokal(path=LOKAL_PATH, text=TEXT):
    """Quittung in der Phonon-Stimme. None, wenn Phonon nicht zu haben ist."""
    return _render_einmal(path, lambda tmp: lokal_tts.synthesize(text, tmp))


def spiele(api_key, path=DEFAULT_PATH, device=None, lokal_path=LOKAL_PATH):
    """Spielt die Quittung. Gibt "stimme" oder "ton" zurück. Nie fatal."""
    pfad = ensure_lokal(path=lokal_path) or ensure_audio(api_key, path=path)
    if pfad:
        playback.play(pfad, device=device)
        return "stimme"
    earcon.beep(TON_PATH, freq=TON_FREQ)
    return "ton"
