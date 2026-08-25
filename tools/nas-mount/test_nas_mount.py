"""Tests des Mount-Waechters.

Geprueft wird genau das, was im Ernstfall zaehlt und sich im Betrieb nie
zeigt: der gesunde Mount darf NICHT angefasst werden, eine Leiche schon, und
ein haengender Aufruf darf den Waechter nicht mitnehmen. Alle drei Faelle sind
am 24./25.08.2026 echt eingetreten.

Die Aussenwelt (`mount`, `diskutil`, `osascript`) wird durch Attrappen ersetzt,
die ihren Aufruf protokollieren — nur so laesst sich beweisen, dass das Skript
im Normalfall gar nichts tut.

Python 3.9 — launchd faehrt /usr/bin/python3.
"""
import os
import subprocess
import time
from pathlib import Path

import pytest

SKRIPT = str(Path(__file__).with_name("nas-mount.sh"))


def _attrappe(pfad, rumpf):
    pfad.write_text("#!/bin/bash\n" + rumpf + "\n")
    pfad.chmod(0o755)
    return str(pfad)


@pytest.fixture
def welt(tmp_path):
    """Eine vollstaendige Attrappen-Umgebung mit Mountpoint und Protokollen."""

    class Welt:
        heim = tmp_path / "heim"
        mountpoint = tmp_path / "mp"
        tabelle = tmp_path / "mount-tabelle.txt"
        ruf_diskutil = tmp_path / "diskutil-aufrufe.txt"
        ruf_osascript = tmp_path / "osascript-aufrufe.txt"

        def haengt_ein(self):
            """Mount-Tabelle so fuellen, wie `mount` es fuer smbfs ausgibt."""
            self.tabelle.write_text(
                "//ws-cloud@NAS._smb._tcp.local/TEST on {} "
                "(smbfs, nodev, nosuid)\n".format(self.mountpoint))

        def sonde_anlegen(self):
            (self.mountpoint / "sonde").mkdir(parents=True, exist_ok=True)

        def status(self):
            pfad = (self.heim / ".paperclip" / "logs" /
                    "nas-mount-TEST-last.json")
            return pfad.read_text() if pfad.exists() else ""

        def lauf(self, frist="2"):
            umgebung = dict(os.environ)
            umgebung["HOME"] = str(self.heim)
            umgebung["MOUNT_STILL"] = "1"
            return subprocess.run(
                [SKRIPT, "--freigabe", "TEST",
                 "--mountpoint", str(self.mountpoint),
                 "--probe", "sonde",
                 "--frist", frist,
                 "--mount-bin", self.mount_bin,
                 "--diskutil-bin", self.diskutil_bin,
                 "--osascript-bin", self.osascript_bin],
                capture_output=True, text=True, env=umgebung, timeout=120)

    w = Welt()
    w.heim.mkdir()
    w.mountpoint.mkdir()
    w.tabelle.write_text("")

    w.mount_bin = _attrappe(tmp_path / "mount",
                            'cat "{}"'.format(w.tabelle))
    w.diskutil_bin = _attrappe(
        tmp_path / "diskutil",
        'echo "$@" >> "{}"\n: > "{}"'.format(w.ruf_diskutil, w.tabelle))
    # Erfolgreicher Mount: Eintrag in der Tabelle UND begehbarer Sondenordner.
    w.osascript_bin = _attrappe(
        tmp_path / "osascript",
        'echo "$@" >> "{ruf}"\n'
        'printf "//srv/TEST on {mp} (smbfs, nodev, nosuid)\\n" > "{tab}"\n'
        'mkdir -p "{mp}/sonde"'.format(
            ruf=w.ruf_osascript, mp=w.mountpoint, tab=w.tabelle))
    return w


def test_gesunder_mount_wird_nicht_angefasst(welt):
    """Die Regression, die monatelang lief.

    Die Vorgaengerin pruefte mit `ls`, was unter launchd auf Netzlaufwerken
    TCC-gesperrt ist und daher IMMER fehlschlug. Ergebnis: 287 Zwangs-Unmounts
    am Tag, mitten in laufende Sicherungen hinein.
    """
    welt.haengt_ein()
    welt.sonde_anlegen()

    e = welt.lauf()

    assert e.returncode == 0, e.stderr
    assert not welt.ruf_diskutil.exists(), "hat einen gesunden Mount ausgehaengt"
    assert not welt.ruf_osascript.exists(), "hat unnoetig neu gemountet"
    assert '"stand":"ok"' in welt.status()


def test_zweiter_lauf_schweigt(welt):
    """Nur Zustandswechsel gehoeren ins Log.

    Das alte Log war mit 900 KB Rauschen („OK - gemountet", 287-mal am Tag) so
    zugestellt, dass der echte 28-Stunden-Ausfall darin nicht auffiel.
    """
    welt.haengt_ein()
    welt.sonde_anlegen()

    erster = welt.lauf()
    zweiter = welt.lauf()

    assert "wieder eingehaengt" in erster.stdout
    assert zweiter.stdout.strip() == "", "schreibt ohne Zustandswechsel ins Log"


def test_nicht_eingehaengt_wird_gemountet(welt):
    e = welt.lauf()

    assert e.returncode == 0, e.stderr
    assert welt.ruf_osascript.exists(), "hat nicht gemountet"
    assert not welt.ruf_diskutil.exists(), \
        "haengt aus, obwohl der Mountpoint frei war"
    assert '"stand":"ok"' in welt.status()


def test_leiche_wird_ausgehaengt(welt):
    """Mount-Tabelle sagt ja, die Freigabe antwortet nicht.

    Genau dieser Zustand blockiert den Mountpoint: ohne Aushaengen scheitert
    jeder Neuversuch.
    """
    welt.haengt_ein()
    welt.mountpoint.rmdir()   # Eintrag da, aber nichts mehr dahinter

    e = welt.lauf()

    assert e.returncode == 0, e.stderr
    assert welt.ruf_diskutil.exists(), "Leiche nicht ausgehaengt"
    assert "unmount force" in welt.ruf_diskutil.read_text()
    assert welt.ruf_osascript.exists()


def test_fehlende_sonde_haengt_nicht_aus(welt):
    """Der Rueckfall in die alte Dauerschleife.

    Wird der Sondenordner umbenannt, lebt die Freigabe weiter — sie darf dann
    NICHT alle 5 Minuten zwangsweise ausgehaengt werden. Das war der Schaden,
    der monatelang lief.
    """
    welt.haengt_ein()   # Wurzel begehbar, aber kein Sondenordner

    e = welt.lauf()

    assert e.returncode == 1
    assert not welt.ruf_diskutil.exists(), "haengt eine gesunde Freigabe aus"
    assert not welt.ruf_osascript.exists(), "mountet eine gesunde Freigabe neu"
    assert "Sondenpfad fehlt" in welt.status()


def test_haengender_mount_bricht_nach_frist_ab(welt):
    """Der 28-Stunden-Ausfall vom 24.08.2026.

    Blockiert der Mount-Aufruf, muss das Skript die Frist einhalten und sich
    beenden — sonst startet launchd wegen StartInterval nie wieder einen Lauf.
    """
    welt.osascript_bin = _attrappe(
        Path(welt.osascript_bin), 'sleep 120')

    start = time.monotonic()
    e = welt.lauf(frist="2")
    dauer = time.monotonic() - start

    assert e.returncode != 0
    assert dauer < 30, "Frist nicht eingehalten: {:.0f}s".format(dauer)
    assert '"stand":"fehler"' in welt.status()
    assert "Frist" in welt.status()


def test_haengendes_aushaengen_bricht_ab(welt):
    """Auch `diskutil unmount` blockiert auf totem SMB beliebig lange."""
    welt.haengt_ein()
    welt.mountpoint.rmdir()
    welt.diskutil_bin = _attrappe(Path(welt.diskutil_bin), 'sleep 120')

    start = time.monotonic()
    e = welt.lauf(frist="2")
    dauer = time.monotonic() - start

    assert e.returncode != 0
    assert dauer < 30, "Frist nicht eingehalten: {:.0f}s".format(dauer)
    assert '"stand":"fehler"' in welt.status()


def test_erfolgloser_mount_meldet_fehler(welt):
    """Attrappe tut nichts — die Nachpruefung muss das merken.

    Die Vorgaengerin pruefte nach dem Mount nur die Mount-Tabelle und meldete
    deshalb Erfolg, obwohl die Freigabe unbenutzbar war.
    """
    welt.osascript_bin = _attrappe(Path(welt.osascript_bin), 'exit 1')

    e = welt.lauf()

    assert e.returncode == 1
    assert '"stand":"fehler"' in welt.status()


def test_freigabe_ist_pflicht():
    e = subprocess.run([SKRIPT], capture_output=True, text=True, timeout=30)
    assert e.returncode == 2
    assert "--freigabe" in e.stderr
