"""Tests der Auswaerts-Sicherung. Aufruf: python3 -m pytest test_nextcloud_backup.py -q

Geprueft wird gegen ECHTE restic-Repos in tmp_path — das Repo bei Hetzner wird
nie angefasst. `HOME` zeigt ebenfalls in tmp_path, damit Log, Status und
Arbeitsordner des Skripts dort landen und nicht im Produktivpfad.

Beide Faelle hier sind am 16.09.2026 wirklich passiert:

1. Ein gescheiterter Datensatz beendete den ganzen Lauf. Weil der
   Claude-Code-Ordner an sieben unlesbaren Verzeichnissen haengenblieb, wurde
   der Obsidian-Vault an diesem Tag ueberhaupt nicht ausgelagert — ohne dass
   das irgendwo als eigener Punkt auftauchte.
2. Die Aufbewahrung scheiterte an einer verwaisten Repo-Sperre, das Skript
   schrieb aber trotzdem `"stand":"ok"`. Deshalb fiel zwei Tage lang nicht
   auf, dass `forget` nie durchlief.
"""
import json
import os
import signal
import subprocess
import time
from pathlib import Path

import pytest

SKRIPT = Path(__file__).parent / "nextcloud-backup.sh"
RESTIC = "/opt/homebrew/bin/restic"

pytestmark = pytest.mark.skipif(not Path(RESTIC).exists(),
                                reason="restic nicht installiert")


def baue_repo(tmp_path):
    """Ein echtes, leeres restic-Repo plus Passwortdatei."""
    repo = tmp_path / "repo"
    passwort = tmp_path / "pass"
    passwort.write_text("test")
    umgebung = {**os.environ,
                "RESTIC_REPOSITORY": str(repo),
                "RESTIC_PASSWORD_FILE": str(passwort)}
    subprocess.run([RESTIC, "init"], env=umgebung, check=True,
                   capture_output=True)
    return repo, passwort, umgebung


def baue_vault(tmp_path):
    """Ein Vault-Ordner an der Stelle, an der das Skript ihn erwartet."""
    vault = tmp_path / "Obsidian" / "WHITESTAG-Vault"
    vault.mkdir(parents=True)
    (vault / "notiz.md").write_text("Inhalt")
    return vault


def lauf(repo, passwort, tmp_path, extra=(), retry_lock="5s"):
    return subprocess.run(
        ["/bin/bash", str(SKRIPT), "--kein-versand", "--repo", str(repo),
         *extra],
        capture_output=True, text=True, timeout=600,
        env={**os.environ,
             "HOME": str(tmp_path),
             "RESTIC_PASSWORD_FILE": str(passwort),
             "NC_RETRY_LOCK": retry_lock})


def status(tmp_path):
    p = tmp_path / ".paperclip" / "logs" / "nextcloud-backup-last.json"
    return json.loads(p.read_text()) if p.exists() else None


def schlagworte(umgebung):
    r = subprocess.run([RESTIC, "snapshots", "--json"], env=umgebung,
                       capture_output=True, text=True)
    return [t for s in json.loads(r.stdout or "[]") for t in (s.get("tags") or [])]


def sperrender_prozess(umgebung):
    """Ein restic, das die Repo-Sperre haelt und am Lesen von stdin haengt.

    Der Aufrufer entscheidet, ob er ihn am Leben laesst (echte gleichzeitige
    Operation) oder killt (verwaiste Sperre)."""
    p = subprocess.Popen([RESTIC, "backup", "--stdin", "--stdin-filename", "x"],
                         stdin=subprocess.PIPE,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         env=umgebung)
    for _ in range(100):
        if sperren(umgebung):
            return p
        time.sleep(0.1)
    p.kill()
    pytest.skip("Sperre liess sich nicht erzeugen")


def verwaiste_sperre(umgebung):
    """Eine Sperre, deren Besitzerprozess hart gestorben ist — der Zustand,
    den der Lauf vom 15.09. im Hetzner-Repo hinterlassen hat."""
    p = sperrender_prozess(umgebung)
    p.send_signal(signal.SIGKILL)
    p.wait(timeout=10)
    assert sperren(umgebung), "Sperre haette liegenbleiben muessen"


def sperren(umgebung):
    r = subprocess.run([RESTIC, "list", "locks"], env=umgebung,
                       capture_output=True, text=True)
    return [z for z in r.stdout.splitlines() if z.strip()]


def test_gescheiterter_datensatz_stoppt_die_folgenden_nicht(tmp_path):
    """Der Kern des Ausfalls vom 16.09.: der Claude-Code-Ordner scheiterte,
    und deshalb wurde der Vault gar nicht erst versucht.

    Jeder Datensatz ist eigenstaendig — dass einer nicht lesbar ist, sagt
    nichts darueber, ob der naechste sicherbar waere. Ihn trotzdem
    auszulassen heisst, aus einem Teilausfall einen groesseren zu machen."""
    repo, passwort, umgebung = baue_repo(tmp_path)
    baue_vault(tmp_path)
    # CODE_DIR wird bewusst NICHT angelegt: unter dem Test-HOME existiert
    # `Library/CloudStorage/...` nicht, der Code-Schritt muss scheitern.
    r = lauf(repo, passwort, tmp_path, ["--nur-code", "--nur-vault"])

    assert "obsidian-vault" in schlagworte(umgebung), \
        f"Vault wurde nicht gesichert. stdout:\n{r.stdout}\n{r.stderr}"
    s = status(tmp_path)
    assert s and s["stand"] == "fehler", s
    assert "Code" in s["grund"] or "code" in s["grund"], s


def test_verwaiste_sperre_blockiert_die_aufbewahrung_nicht(tmp_path):
    """Am 16.09. lagen vier verwaiste Sperren im Repo, die aelteste seit 27
    Stunden von einem toten Prozess. Jedes `forget` wartete daraufhin seine
    vollen 30 Minuten und gab auf; die Aufbewahrung lief zwei Tage nicht.

    Der Lauf raeumt solche Sperren jetzt selbst weg, bevor er aufraeumt."""
    repo, passwort, umgebung = baue_repo(tmp_path)
    baue_vault(tmp_path)
    verwaiste_sperre(umgebung)

    r = lauf(repo, passwort, tmp_path, ["--nur-vault"])

    assert sperren(umgebung) == [], \
        f"verwaiste Sperre blieb liegen. stdout:\n{r.stdout}\n{r.stderr}"
    s = status(tmp_path)
    assert s and s["stand"] == "ok", \
        f"Lauf haette trotz verwaister Sperre durchgehen muessen: {s}"


def test_gescheiterte_aufbewahrung_wird_nicht_als_ok_gemeldet(tmp_path):
    """Gegenstueck: haelt ein LEBENDER Prozess die Sperre, ist sie nicht
    verwaist und darf auch nicht weggeraeumt werden — `forget` scheitert dann
    zu Recht. Bis zum 16.09. war das nur eine Logzeile, der Lauf meldete
    weiter `"stand":"ok"`. Genau deshalb fiel zwei Tage lang nicht auf, dass
    nichts mehr aufgeraeumt wurde.

    Eine Sicherung, die sich nicht mehr aufraeumt, waechst still weiter, bis
    der Tarif voll ist — das gehoert in den Bericht."""
    repo, passwort, umgebung = baue_repo(tmp_path)
    baue_vault(tmp_path)
    halter = sperrender_prozess(umgebung)
    try:
        r = lauf(repo, passwort, tmp_path, ["--nur-vault"])

        assert "obsidian-vault" in schlagworte(umgebung), \
            f"Sicherung selbst muss durchlaufen. stdout:\n{r.stdout}\n{r.stderr}"
        s = status(tmp_path)
        assert s and s["stand"] == "fehler", \
            f"Gescheiterte Aufbewahrung darf nicht als ok durchgehen: {s}"
        assert "ufbewahrung" in s["grund"], s
    finally:
        halter.kill()
        halter.wait(timeout=10)
