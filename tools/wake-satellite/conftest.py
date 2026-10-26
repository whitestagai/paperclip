import os
import subprocess
import sys

import pytest

# Geteilte voice-echo-bot-Module (jarvis_brain, tts, transcribe, config, …)
# in Tests importierbar machen.
_VCO = os.path.join(os.path.dirname(__file__), "..", "voice-echo-bot")
sys.path.insert(0, os.path.abspath(_VCO))


@pytest.fixture(autouse=True)
def keine_echte_hardware(monkeypatch):
    """Sperrt Audio-Ausgabe und ElevenLabs für ALLE Tests.

    Der Satellit hat beides in Reichweite: `playback.play` schaltet die
    Systemausgabe um und spielt über den HomePod, `tts.synthesize` ruft die
    API. Ohne diese Sperre spielte ein Testlauf tatsächlich „Ja?" durchs
    Zimmer und brauchte 38 s (Befund 17.08.) — sobald die Quittungsdatei
    einmal vorgerendert im Cache lag, ging `ensure_audio` ja direkt zur
    Wiedergabe. Tests, die genau diese Schicht prüfen, setzen ihre eigenen
    Doubles; die greifen, weil sie später gesetzt werden als diese Fixture.
    """
    import tts

    def verboten(*args, **kwargs):
        raise AssertionError(
            "Test wollte echte Hardware/Netz benutzen — im Test ersetzen")

    monkeypatch.setattr(subprocess, "run", verboten)
    monkeypatch.setattr(subprocess, "Popen", verboten)
    monkeypatch.setattr(tts, "synthesize", verboten)
