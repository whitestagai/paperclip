"""Gemeinsame Test-Voreinstellungen.

Sperrt das Produktivlog fuer die GANZE Suite. Ohne das schreiben Testlaeufe
nach `~/.paperclip/logs/nas-mount.log` und sehen beim spaeteren Nachsehen wie
echte Vorfaelle aus — dieselbe Falle wie bei vault-nas-sync und
backup-waechter, wo genau das schon einmal passiert ist.
"""
import pytest


@pytest.fixture(autouse=True)
def kein_produktivlog(monkeypatch):
    monkeypatch.setenv("MOUNT_STILL", "1")
