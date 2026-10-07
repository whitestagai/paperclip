"""Tests fuer erreichbarkeit.sh.

Das Skript ist die Evidenzgrundlage dafuer, ob der Node durchlaeuft — eine
Fehlmeldung in Richtung "connected" waere der schlimmste Fehler, den es
machen kann. Genau das wird hier geprueft.
"""
import os
import subprocess
import textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
SKRIPT = os.path.join(HERE, "erreichbarkeit.sh")

NODE_VERBUNDEN = """\
This device: MacStudioM4Max128
Status: Online

Found 2 devices:

  - RTX Pro 6000
    Status: connected
    Identifier: 3f6d2489f519c745243a6c4daa0334d5
    Loaded Models Instances:
      - qwen3.6-35b-a3b
  - WHITESTAG-AI
    Status: connected
    Identifier: 55fb4392eb9f978c1bc68abfef0c4b59
    Loaded Models Instances:
      - gemma-4-31b-win
      - qwen3.6-35b-win
"""

NODE_GETRENNT_ZULETZT = """\
This device: MacStudioM4Max128
Status: Online

Found 2 devices:

  - RTX Pro 6000
    Status: connected
    Identifier: 3f6d2489f519c745243a6c4daa0334d5
    Loaded Models Instances:
      - qwen3.6-35b-a3b
  - WHITESTAG-AI
    Status: disconnected
    Identifier: 55fb4392eb9f978c1bc68abfef0c4b59
"""

# Der kritische Fall: der Node ist getrennt und ein WEITERES Geraet folgt
# danach. Ein getrennter Node hat keine "Loaded Models Instances", sein
# Block ist also kuerzer — eine Blockbildung mit fester Zeilenzahl liest
# in das naechste Geraet hinein und findet dort "Status: connected".
NODE_GETRENNT_MITTENDRIN = """\
This device: MacStudioM4Max128
Status: Online

Found 3 devices:

  - WHITESTAG-AI
    Status: disconnected
    Identifier: 55fb4392eb9f978c1bc68abfef0c4b59
  - RTX Pro 6000
    Status: connected
    Identifier: 3f6d2489f519c745243a6c4daa0334d5
    Loaded Models Instances:
      - qwen3.6-35b-a3b
  - MacbookM5Mx128
    Status: connected
    Identifier: e2d3747e00000000000000000000aaaa
    Loaded Models Instances:
      - qwen3.6-35b-a3b-mlx
"""


def lauf(tmp_path, lms_ausgabe, curl_code="200"):
    """Fuehrt das Skript mit gefaelschtem lms und curl aus, gibt die Logzeile."""
    fake_lms = tmp_path / "lms"
    # lms link status schreibt auf STDERR, nicht stdout — das faelschen wir mit.
    fake_lms.write_text(textwrap.dedent(f"""\
        #!/bin/sh
        cat >&2 <<'ENDE'
        {lms_ausgabe.rstrip()}
        ENDE
        """).replace("\n        ", "\n"))
    fake_lms.chmod(0o755)

    fake_curl = tmp_path / "curl"
    fake_curl.write_text(f"#!/bin/sh\nprintf '{curl_code}'\n")
    fake_curl.chmod(0o755)

    log = tmp_path / "node.log"
    env = dict(os.environ,
               LMS_BIN=str(fake_lms),
               CURL_BIN=str(fake_curl),
               LOG_FILE=str(log))
    subprocess.run(["/bin/zsh", SKRIPT], env=env, check=True,
                   capture_output=True, timeout=60)
    return log.read_text().strip()


def test_verbundener_node_wird_als_connected_protokolliert(tmp_path):
    zeile = lauf(tmp_path, NODE_VERBUNDEN)
    assert "| connected |" in zeile
    assert "gemma-4-31b-win=200" in zeile


def test_getrennter_node_zuletzt_wird_als_disconnected_protokolliert(tmp_path):
    zeile = lauf(tmp_path, NODE_GETRENNT_ZULETZT)
    assert "| disconnected |" in zeile


def test_getrennter_node_mit_folgendem_geraet_wird_nicht_als_connected_gemeldet(tmp_path):
    """Der wichtigste Test: niemals 'connected' melden, wenn der Node weg ist.

    Eine Fehlmeldung in diese Richtung laesst einen Ausfall unsichtbar und
    wuerde eine Freigabe auf falscher Grundlage stuetzen.
    """
    zeile = lauf(tmp_path, NODE_GETRENNT_MITTENDRIN)
    assert "| disconnected |" in zeile, f"falsch gemeldet: {zeile}"


def test_modell_ohne_200_wird_sichtbar(tmp_path):
    zeile = lauf(tmp_path, NODE_VERBUNDEN, curl_code="503")
    assert "gemma-4-31b-win=503" in zeile
