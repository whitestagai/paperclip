import io
import json
import urllib.error

import pytest

import lokal_tts
import sat_config
import tts

# Die echte Funktion, bevor die autouse-Sperre in conftest sie ersetzt. Netz
# gibt es trotzdem nicht: jeder Test ersetzt urlopen.
synthesize = lokal_tts.synthesize

WAV = b"RIFF\x24\x00\x00\x00WAVEfmt "


class _Antwort(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _fake_urlopen(mitschrift, inhalt=WAV):
    def urlopen(req, timeout=None):
        mitschrift.append({"url": req.full_url, "body": json.loads(req.data),
                           "timeout": timeout})
        return _Antwort(inhalt)
    return urlopen


def test_schickt_text_stimme_und_modell_an_ollama(tmp_path, monkeypatch):
    aufrufe = []
    monkeypatch.setattr(lokal_tts.urllib.request, "urlopen", _fake_urlopen(aufrufe))
    dest = str(tmp_path / "reply.wav")

    assert synthesize("  Guten Morgen, Walter.  ", dest) == dest

    assert len(aufrufe) == 1
    body = aufrufe[0]["body"]
    assert aufrufe[0]["url"] == sat_config.LOKAL_TTS_URL
    assert body["input"] == "Guten Morgen, Walter."
    assert body["model"] == sat_config.LOKAL_TTS_MODEL
    assert body["voice"] == sat_config.LOKAL_TTS_STIMME
    assert body["response_format"] == "wav"
    assert aufrufe[0]["timeout"] == sat_config.LOKAL_TTS_TIMEOUT_SEC
    with open(dest, "rb") as fh:
        assert fh.read() == WAV


def test_leerer_text_fragt_ollama_gar_nicht(tmp_path, monkeypatch):
    aufrufe = []
    monkeypatch.setattr(lokal_tts.urllib.request, "urlopen", _fake_urlopen(aufrufe))
    with pytest.raises(tts.TtsError):
        synthesize("   ", str(tmp_path / "x.wav"))
    assert aufrufe == []


def test_ollama_nicht_erreichbar_wird_tts_fehler(tmp_path, monkeypatch):
    def weg(req, timeout=None):
        raise urllib.error.URLError("Connection refused")

    monkeypatch.setattr(lokal_tts.urllib.request, "urlopen", weg)
    with pytest.raises(tts.TtsError):
        synthesize("Hallo", str(tmp_path / "x.wav"))


def test_http_fehler_wird_tts_fehler(tmp_path, monkeypatch):
    def nicht_gefunden(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 404, "model not found", {}, None)

    monkeypatch.setattr(lokal_tts.urllib.request, "urlopen", nicht_gefunden)
    with pytest.raises(tts.TtsError):
        synthesize("Hallo", str(tmp_path / "x.wav"))


def test_antwort_ohne_wav_wird_nicht_als_audio_abgelegt(tmp_path, monkeypatch):
    # Ein Fehlertext mit Status 200 darf nicht als „reply.wav" bei afplay
    # landen — afplay scheitert dann still und Jarvis schweigt, statt auf
    # ElevenLabs auszuweichen.
    monkeypatch.setattr(lokal_tts.urllib.request, "urlopen",
                        _fake_urlopen([], inhalt=b'{"error":"voice not found"}'))
    dest = tmp_path / "x.wav"
    with pytest.raises(tts.TtsError):
        synthesize("Hallo", str(dest))
    assert not dest.exists()
