#!/usr/bin/env python3
"""Häufiger Takt für die Modell-Aufsicht — prüft, protokolliert, meldet.

Warum es diesen Melder zusätzlich zur täglichen Paperclip-Routine gibt: Der
Vorfall am 26.08.2026 begann um 10:00 und war um 12:11 wieder vorbei. Ein
einzelner Lauf um 07:30 hätte ihn vollständig verpasst. Prüfen kostet hier
nichts — es ist reines Python ohne LLM —, also wird oft geprüft und nur bei
Zustandswechsel gemeldet.

Aufruf (launchd, alle 30 Minuten):
    ./melder.py

Läuft unter dem System-Python 3.9 — keine Fremdpakete, keine 3.10-Syntax.
"""

import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.expanduser("~/.paperclip/scripts"))

from pruefung import meldung_faellig, signatur  # noqa: E402
from waechter import pruefe  # noqa: E402

LOG = os.path.expanduser("~/.paperclip/logs/modell-wacht.log")
ZUSTAND = os.path.expanduser("~/.paperclip/logs/modell-wacht-last.json")
FIRMA = os.environ.get("MODELL_WACHT_FIRMA", "9cebf3cf-efe8-4597-a400-f06488900a87")


def _protokoll(zeile: str) -> None:
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write("{} {}\n".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), zeile))


def _zuletzt() -> list:
    try:
        with open(ZUSTAND, "r", encoding="utf-8") as fh:
            return json.load(fh).get("signatur") or []
    except Exception:  # noqa: BLE001 - erster Lauf, kaputte Datei: beides egal
        return []


def _schreibe_zustand(sig: list, ergebnis: dict) -> None:
    """Wird bei JEDEM Lauf geschrieben, auch ohne Meldung.

    Sonst gilt ein behobener Fehler beim Wiederauftreten als «schon gemeldet»
    und bleibt stumm — genau der flappende Fall vom 26.08.
    """
    with open(ZUSTAND, "w", encoding="utf-8") as fh:
        json.dump(
            {
                "zeitpunkt": datetime.now().isoformat(timespec="seconds"),
                "signatur": sig,
                "ok": ergebnis.get("ok"),
                "befunde": ergebnis.get("befunde"),
            },
            fh,
            ensure_ascii=False,
            indent=1,
        )


def _melde(befunde, ergebnis) -> str:
    """Legt ein Paperclip-Issue an. Fehler hier dürfen den Lauf nicht kippen —
    ein nicht zugestelltes Issue ist schlimm, ein abgebrochener Wächter
    schlimmer."""
    import paperclip_client as pc

    hart = [b for b in befunde if b.schwere == "hoch"]
    titel = "Modell-Aufsicht: {} harte{} Befund{}".format(
        len(hart), "r" if len(hart) == 1 else "", "" if len(hart) == 1 else "e"
    )
    zeilen = [ergebnis["kopfzeile"], ""]
    for b in befunde:
        zeilen.append("- [{}] {}".format(b.schwere.upper(), b.text))
    zeilen += [
        "",
        "Gemeldet vom halbstündlichen Melder (`tools/modell-wacht/melder.py`).",
        "Erneute Meldung erst, wenn sich der Befundstand ändert.",
    ]
    return pc.create_issue(
        pc.api_base(),
        pc.load_token(),
        FIRMA,
        title=titel,
        description="\n".join(zeilen),
        assignee_agent_id=None,
        priority="high",
    )


def main() -> int:
    befunde, ergebnis = pruefe()
    sig = signatur(befunde)
    faellig = meldung_faellig(sig, _zuletzt())

    if faellig:
        try:
            issue = _melde(befunde, ergebnis)
            _protokoll("MELDUNG {} Befund(e), Issue {}".format(len(sig), issue))
        except Exception as exc:  # noqa: BLE001
            _protokoll("MELDUNG FEHLGESCHLAGEN ({}): {}".format(len(sig), exc))
    elif sig:
        _protokoll("unveraendert: {} harte Befunde, keine neue Meldung".format(len(sig)))
    else:
        _protokoll("ok: {}".format(ergebnis["kopfzeile"]))

    _schreibe_zustand(sig, ergebnis)
    return 1 if sig else 0


if __name__ == "__main__":
    sys.exit(main())
