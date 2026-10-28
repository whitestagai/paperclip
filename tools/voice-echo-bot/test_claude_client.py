import subprocess

import pytest

import claude_client


class FakeProc:
    """Steht für den `claude -p`-Prozess."""
    def __init__(self, out="", err="", rc=0, haengt=False):
        self.out, self.err, self.rc, self.haengt = out, err, rc, haengt
        self.returncode = None
        self.killed = False

    def communicate(self, timeout=None):
        if self.haengt and not self.killed:
            raise subprocess.TimeoutExpired("claude", timeout)
        self.returncode = self.rc
        return self.out, self.err

    def kill(self):
        self.killed = True


def _popen(proc, seen):
    def popen(args, **kw):
        seen["args"], seen["kw"] = args, kw
        return proc
    return popen


def test_antwort_kommt_zurueck(tmp_path):
    seen = {}
    antwort = claude_client.frage("Wie wird das Wetter?", arbeitsordner=str(tmp_path),
                                  popen=_popen(FakeProc(out="Morgen sonnig.\n"), seen))
    assert antwort == "Morgen sonnig."
    args = seen["args"]
    assert "-p" in args and "Wie wird das Wetter?" in args
    # Schlank: eigener System-Prompt, nur Web-Werkzeuge, keine MCP-Server
    assert "--system-prompt" in args and "--strict-mcp-config" in args
    assert args[args.index("--tools") + 1:args.index("--tools") + 3] == ["WebSearch", "WebFetch"]
    assert seen["kw"]["cwd"] == str(tmp_path)


def test_waehrenddessen_laeuft_nachdem_claude_gestartet_ist(tmp_path):
    # Die Ansage „Moment …" darf Claude nicht aufhalten: erst starten, dann reden.
    reihenfolge = []
    proc = FakeProc(out="ok")
    def popen(args, **kw):
        reihenfolge.append("start")
        return proc
    claude_client.frage("x", arbeitsordner=str(tmp_path), popen=popen,
                        waehrenddessen=lambda: reihenfolge.append("ansage"))
    assert reihenfolge == ["start", "ansage"]


def test_fehler_in_der_ansage_bricht_die_frage_nicht_ab(tmp_path):
    def kaputt():
        raise RuntimeError("Lautsprecher weg")
    assert claude_client.frage("x", arbeitsordner=str(tmp_path), waehrenddessen=kaputt,
                               popen=_popen(FakeProc(out="ok"), {})) == "ok"


def test_verlauf_geht_als_kontext_mit(tmp_path):
    seen = {}
    verlauf = [{"role": "user", "content": "Wetter morgen?"},
               {"role": "assistant", "content": "Sonnig."}]
    claude_client.frage("Und übermorgen?", history=verlauf, arbeitsordner=str(tmp_path),
                        popen=_popen(FakeProc(out="Regen."), seen))
    prompt = seen["args"][seen["args"].index("-p") + 1]
    assert "Wetter morgen?" in prompt and "Sonnig." in prompt
    assert prompt.rstrip().endswith("Und übermorgen?")


def test_exitcode_ungleich_null_ist_fehler(tmp_path):
    with pytest.raises(claude_client.ClaudeError):
        claude_client.frage("x", arbeitsordner=str(tmp_path),
                            popen=_popen(FakeProc(err="auth", rc=1), {}))


def test_leere_antwort_ist_fehler(tmp_path):
    with pytest.raises(claude_client.ClaudeError):
        claude_client.frage("x", arbeitsordner=str(tmp_path),
                            popen=_popen(FakeProc(out="  \n"), {}))


def test_zeitueberschreitung_beendet_den_prozess(tmp_path):
    proc = FakeProc(haengt=True)
    with pytest.raises(claude_client.ClaudeError):
        claude_client.frage("x", arbeitsordner=str(tmp_path), timeout=1,
                            popen=_popen(proc, {}))
    assert proc.killed


def test_fehlendes_programm_ist_fehler(tmp_path):
    def popen(args, **kw):
        raise FileNotFoundError("claude")
    with pytest.raises(claude_client.ClaudeError):
        claude_client.frage("x", arbeitsordner=str(tmp_path), popen=popen)


def test_markdown_wird_fuer_die_sprachausgabe_entfernt(tmp_path):
    antwort = claude_client.frage("x", arbeitsordner=str(tmp_path),
                                  popen=_popen(FakeProc(out="Es wird **sonnig**."), {}))
    assert antwort == "Es wird sonnig."
