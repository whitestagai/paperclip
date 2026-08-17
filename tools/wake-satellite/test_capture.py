import wave
import numpy as np
import capture


def loud(n=1280):  return (np.ones(n, dtype=np.int16) * 5000)
def quiet(n=1280): return np.zeros(n, dtype=np.int16)


def test_record_starts_at_speech_and_stops_after_silence():
    # 2 stille (ignoriert), 3 laute, dann hang=2 stille -> stop
    frames = [quiet(), quiet(), loud(), loud(), loud(), quiet(), quiet(), loud()]
    out = capture.record_until_silence(iter(frames), hang=2)
    # Startet beim ersten lauten Frame; endet nach 2 stillen; letztes loud nicht mehr
    assert len(out) == 5  # 3 loud + 2 trailing silence


def test_record_respects_max_frames():
    frames = (loud() for _ in range(1000))
    out = capture.record_until_silence(frames, max_frames=10)
    assert len(out) == 10


def test_record_empty_when_only_silence():
    out = capture.record_until_silence(iter([quiet(), quiet(), quiet()]), hang=2)
    assert out == []


def test_record_gives_up_when_speech_never_starts():
    # Fehl-Wake ohne Folgesatz: ohne Deckel wartet die Aufnahme unbegrenzt und
    # schnappt sich die nächstbeste Äußerung — auch Minuten später.
    frames = iter([quiet()] * 10 + [loud()] * 5)
    assert capture.record_until_silence(frames, max_start_frames=5) == []


def test_record_still_starts_within_start_window():
    frames = iter([quiet()] * 3 + [loud()] * 3 + [quiet()] * 3)
    out = capture.record_until_silence(frames, max_start_frames=5, hang=2)
    assert len(out) == 5     # 3 laute + 2 nachlaufende stille


def test_record_keeps_the_frames_that_triggered_the_start():
    # Kernbefund 17.08.: die Frames, an denen der Sprachbeginn erkannt wird,
    # gehören IN die Aufnahme. Wurden sie beim Erkennen verbraucht, fehlten im
    # Transkript die ersten Wörter ('eines Windrads' statt des ganzen Satzes).
    frames = [quiet(), loud(), loud(), loud(), loud(), quiet(), quiet()]
    out = capture.record_until_silence(iter(frames), hang=2, min_start_run=3)
    assert len(out) == 6                       # 4 laute + 2 nachlaufende stille
    assert all(capture._rms(f) >= capture.SILENCE_RMS for f in out[:4])


def test_record_ignores_short_noise_burst():
    # Ein einzelner lauter Frame (Knacks, Tastendruck) darf keine Aufnahme
    # starten — dieselbe Absicherung, die vorher in wait_for_speech steckte.
    frames = iter([quiet(), loud(), quiet(), quiet(), quiet()])
    assert capture.record_until_silence(frames, hang=2, min_start_run=3) == []


def test_record_discards_noise_before_real_speech():
    # Knacks, dann echte Sprache: der Knacks darf nicht vorne dranhängen.
    frames = [loud(), quiet(), loud(), loud(), loud(), quiet(), quiet()]
    out = capture.record_until_silence(iter(frames), hang=2, min_start_run=3)
    assert len(out) == 5                       # 3 laute + 2 nachlaufende stille


def test_record_start_window_also_counts_loud_frames():
    # Dauergeräusch unter der Start-Schwelle darf die Aufnahme nicht ewig in
    # der Warteschleife halten; der Deckel zählt jeden Frame, nicht nur stille.
    frames = iter([loud(), quiet()] * 20)
    assert capture.record_until_silence(frames, max_start_frames=5,
                                        min_start_run=3) == []


def test_frames_to_wav_roundtrip(tmp_path):
    path = str(tmp_path / "a.wav")
    capture.frames_to_wav([loud(), loud()], path)
    with wave.open(path, "rb") as wf:
        assert wf.getframerate() == 16000
        assert wf.getnchannels() == 1
        assert wf.getnframes() == 2560
