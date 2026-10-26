import os

import pytest

import quittung
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


def test_spiele_nutzt_die_stimme_wenn_vorhanden(tmp_path, monkeypatch):
    gespielt, gepiept = [], []
    monkeypatch.setattr(tts, "synthesize", _fake_synth([]))
    monkeypatch.setattr(quittung.playback, "play",
                        lambda pfad, device=None: gespielt.append((pfad, device)))
    monkeypatch.setattr(quittung.earcon, "beep",
                        lambda path=None, freq=None: gepiept.append(path))
    pfad = str(tmp_path / "quittung.mp3")

    assert quittung.spiele("key", path=pfad, device="AirPlay") == "stimme"
    assert gespielt == [(pfad, "AirPlay")]
    assert gepiept == []


def test_spiele_faellt_auf_ton_zurueck_ohne_schluessel(tmp_path, monkeypatch):
    # Kein ElevenLabs-Schlüssel (oder Ausfall): lieber ein Ton als Schweigen —
    # Walter muss wissen, dass jetzt zugehört wird.
    gespielt, gepiept = [], []
    monkeypatch.setattr(quittung.playback, "play",
                        lambda pfad, device=None: gespielt.append(pfad))
    monkeypatch.setattr(quittung.earcon, "beep",
                        lambda path=None, freq=None: gepiept.append((path, freq)))

    assert quittung.spiele(None, path=str(tmp_path / "q.mp3")) == "ton"
    assert gespielt == []
    assert len(gepiept) == 1


def test_rueckfallton_klingt_anders_als_der_wake_ton():
    # „Hab dich gehört" (Wake) und „ich höre jetzt zu" (Quittung) müssen
    # unterscheidbar sein, sonst hört Walter zweimal dasselbe.
    assert quittung.TON_FREQ != 880
    assert quittung.TON_PATH != quittung.earcon.DEFAULT_PATH
