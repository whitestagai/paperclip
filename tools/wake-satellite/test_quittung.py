import os

import pytest

import lokal_tts
import quittung
import sat_config
import tts


def _fake_synth(counter, inhalt=b"MP3"):
    def synth(text, api_key, dest, output_format=None):
        counter.append({"text": text, "key": api_key, "format": output_format})
        with open(dest, "wb") as fh:
            fh.write(inhalt)
        return dest
    return synth


def test_audio_wird_einmal_gerendert_und_wiederverwendet(tmp_path, monkeypatch):
    # Die Quittung fällt bei JEDEM „Hey Jarvis" an — sie darf nur beim ersten
    # Mal einen ElevenLabs-Aufruf kosten, sonst wartet Walter jedes Mal.
    aufrufe = []
    monkeypatch.setattr(tts, "synthesize", _fake_synth(aufrufe))
    pfad = str(tmp_path / "quittung.mp3")

    erst = quittung.ensure_audio("key", path=pfad)
    zweit = quittung.ensure_audio("key", path=pfad)

    assert erst == pfad and zweit == pfad
    assert len(aufrufe) == 1
    assert aufrufe[0]["text"] == quittung.TEXT
    with open(pfad, "rb") as fh:
        assert fh.read() == b"MP3"


def test_ohne_schluessel_kein_audio(tmp_path, monkeypatch):
    monkeypatch.setattr(tts, "synthesize", _fake_synth([]))
    pfad = str(tmp_path / "quittung.mp3")
    assert quittung.ensure_audio("", path=pfad) is None
    assert not os.path.exists(pfad)


def test_tts_fehler_hinterlaesst_keine_kaputte_datei(tmp_path, monkeypatch):
    # Eine halb geschriebene Datei würde beim nächsten Start als „fertig"
    # gelten und für immer stumm bleiben.
    def kaputt(text, api_key, dest, output_format=None):
        with open(dest, "wb") as fh:
            fh.write(b"halb")
        raise tts.TtsError("ElevenLabs HTTP 401")

    monkeypatch.setattr(tts, "synthesize", kaputt)
    pfad = str(tmp_path / "quittung.mp3")
    assert quittung.ensure_audio("key", path=pfad) is None
    assert not os.path.exists(pfad)


def test_leere_datei_wird_neu_gerendert(tmp_path, monkeypatch):
    aufrufe = []
    monkeypatch.setattr(tts, "synthesize", _fake_synth(aufrufe))
    pfad = str(tmp_path / "quittung.mp3")
    open(pfad, "wb").close()          # 0 Byte von einem früheren Abbruch

    assert quittung.ensure_audio("key", path=pfad) == pfad
    assert len(aufrufe) == 1


def _phonon_aus(monkeypatch):
    def aus(text, dest):
        raise tts.TtsError("Ollama nicht erreichbar")
    monkeypatch.setattr(lokal_tts, "synthesize", aus)


def test_spiele_nutzt_die_stimme_wenn_vorhanden(tmp_path, monkeypatch):
    gespielt, gepiept = [], []
    _phonon_aus(monkeypatch)
    monkeypatch.setattr(tts, "synthesize", _fake_synth([]))
    monkeypatch.setattr(quittung.playback, "play",
                        lambda pfad, device=None: gespielt.append((pfad, device)))
    monkeypatch.setattr(quittung.earcon, "beep",
                        lambda path=None, freq=None: gepiept.append(path))
    pfad = str(tmp_path / "quittung.mp3")

    assert quittung.spiele("key", path=pfad, device="AirPlay",
                           lokal_path=str(tmp_path / "q.wav")) == "stimme"
    assert gespielt == [(pfad, "AirPlay")]
    assert gepiept == []


def test_spiele_faellt_auf_ton_zurueck_ohne_schluessel(tmp_path, monkeypatch):
    # Kein ElevenLabs-Schlüssel (oder Ausfall): lieber ein Ton als Schweigen —
    # Walter muss wissen, dass jetzt zugehört wird.
    gespielt, gepiept = [], []
    _phonon_aus(monkeypatch)
    monkeypatch.setattr(quittung.playback, "play",
                        lambda pfad, device=None: gespielt.append(pfad))
    monkeypatch.setattr(quittung.earcon, "beep",
                        lambda path=None, freq=None: gepiept.append((path, freq)))

    assert quittung.spiele(None, path=str(tmp_path / "q.mp3"),
                           lokal_path=str(tmp_path / "q.wav")) == "ton"
    assert gespielt == []
    assert len(gepiept) == 1


def test_rueckfallton_klingt_anders_als_der_wake_ton():
    # „Hab dich gehört" (Wake) und „ich höre jetzt zu" (Quittung) müssen
    # unterscheidbar sein, sonst hört Walter zweimal dasselbe.
    assert quittung.TON_FREQ != 880
    assert quittung.TON_PATH != quittung.earcon.DEFAULT_PATH


# ---- Quittung in der Phonon-Stimme ----------------------------------------

def _fake_lokal(counter, inhalt=b"RIFFWAV"):
    def synth(text, dest):
        counter.append(text)
        with open(dest, "wb") as fh:
            fh.write(inhalt)
        return dest
    return synth


def test_quittung_spricht_mit_derselben_stimme_wie_die_antworten(tmp_path, monkeypatch):
    # „Ja?" in ElevenLabs und die Antwort in Phonon klängen nach zwei Leuten.
    lokal, eleven, gespielt = [], [], []
    monkeypatch.setattr(lokal_tts, "synthesize", _fake_lokal(lokal))
    monkeypatch.setattr(tts, "synthesize", _fake_synth(eleven))
    monkeypatch.setattr(quittung.playback, "play",
                        lambda pfad, device=None: gespielt.append(pfad))
    wav = str(tmp_path / "q.wav")

    assert quittung.spiele("key", path=str(tmp_path / "q.mp3"), lokal_path=wav) == "stimme"
    assert lokal == [quittung.TEXT]
    assert eleven == []
    assert gespielt == [wav]


def test_phonon_quittung_wird_einmal_gerendert(tmp_path, monkeypatch):
    lokal = []
    monkeypatch.setattr(lokal_tts, "synthesize", _fake_lokal(lokal))
    wav = str(tmp_path / "q.wav")
    assert quittung.ensure_lokal(path=wav) == wav
    assert quittung.ensure_lokal(path=wav) == wav
    assert len(lokal) == 1


def test_phonon_fehler_hinterlaesst_keine_kaputte_quittung(tmp_path, monkeypatch):
    def kaputt(text, dest):
        with open(dest, "wb") as fh:
            fh.write(b"halb")
        raise tts.TtsError("Ollama HTTP 500")

    monkeypatch.setattr(lokal_tts, "synthesize", kaputt)
    wav = tmp_path / "q.wav"
    assert quittung.ensure_lokal(path=str(wav)) is None
    assert not wav.exists()


def test_quittungsdatei_traegt_die_stimme_im_namen():
    # Wechselt die Stimme, muss das „Ja?" neu gerendert werden — sonst bleibt
    # die alte Stimme für immer im Cache.
    assert sat_config.LOKAL_TTS_STIMME.lower() in os.path.basename(quittung.LOKAL_PATH)
