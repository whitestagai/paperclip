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
import playback
import tts

DEFAULT_PATH = os.path.expanduser("~/.paperclip/wake-satellite/quittung.mp3")
TEXT = "Ja?"
FORMAT = "mp3_44100_128"

# Rückfallton: tiefer als der 880-Hz-Wake-Ton aus earcon.py.
TON_PATH = os.path.expanduser("~/.paperclip/wake-satellite/quittung-ton.wav")
TON_FREQ = 520


def ensure_audio(api_key, path=DEFAULT_PATH, text=TEXT, output_format=FORMAT):
    """Pfad zur zwischengespeicherten Quittung; rendert sie beim ersten Mal.
    None, wenn kein Audio zu bekommen ist.

    Geschrieben wird über eine temporäre Datei und `os.replace`: eine halb
    geschriebene Datei würde beim nächsten Start als fertig gelten und die
    Quittung für immer stumm schalten.
    """
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    if not api_key:
        return None
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = path + ".tmp"
    try:
        tts.synthesize(text, api_key, tmp, output_format=output_format)
        os.replace(tmp, path)
        return path
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        try:
            os.remove(tmp)
        except OSError:
            pass
        return None


def spiele(api_key, path=DEFAULT_PATH, device=None):
    """Spielt die Quittung. Gibt "stimme" oder "ton" zurück. Nie fatal."""
    pfad = ensure_audio(api_key, path=path)
    if pfad:
        playback.play(pfad, device=device)
        return "stimme"
    earcon.beep(TON_PATH, freq=TON_FREQ)
    return "ton"
