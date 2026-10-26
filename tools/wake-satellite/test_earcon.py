import wave
import earcon


def test_ensure_wav_creates_file_of_expected_length(tmp_path):
    path = str(tmp_path / "beep.wav")
    earcon.ensure_wav(path, ms=100, sample_rate=16000)
    with wave.open(path, "rb") as wf:
        assert wf.getnframes() == 1600  # 100 ms @ 16 kHz


def test_ensure_wav_is_idempotent(tmp_path):
    path = str(tmp_path / "beep.wav")
    earcon.ensure_wav(path, ms=100)
    mtime1 = __import__("os").path.getmtime(path)
    earcon.ensure_wav(path, ms=100)      # existiert -> nicht neu schreiben
    assert __import__("os").path.getmtime(path) == mtime1


def test_beep_reicht_die_frequenz_an_die_wav_durch(monkeypatch, tmp_path):
    # Die Quittung („ich höre jetzt zu") braucht einen anderen Ton als der
    # Wake-Treffer („hab dich gehört") — sonst klingt beides gleich.
    monkeypatch.setattr(earcon.subprocess, "run", lambda *a, **k: None)
    erzeugt, referenz = str(tmp_path / "a.wav"), str(tmp_path / "b.wav")
    earcon.beep(erzeugt, freq=520)
    earcon.ensure_wav(referenz, freq=520)
    with open(erzeugt, "rb") as a, open(referenz, "rb") as b:
        assert a.read() == b.read()


def test_beep_never_raises(monkeypatch, tmp_path):
    def boom(*a, **k): raise RuntimeError("afplay weg")
    monkeypatch.setattr(earcon.subprocess, "run", boom)
    earcon.beep(str(tmp_path / "beep.wav"))   # kein Throw


def test_beep_async_is_non_blocking_and_never_raises(monkeypatch, tmp_path):
    calls = {}
    def fake_popen(args, **kwargs):
        calls["args"] = args
        return object()          # kein wait() -> nicht blockierend
    monkeypatch.setattr(earcon.subprocess, "Popen", fake_popen)
    earcon.beep_async(str(tmp_path / "beep.wav"))
    assert calls["args"][0] == "afplay"

    def boom(*a, **k): raise RuntimeError("afplay weg")
    monkeypatch.setattr(earcon.subprocess, "Popen", boom)
    earcon.beep_async(str(tmp_path / "beep.wav"))   # kein Throw
