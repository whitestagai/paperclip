"""Einstiegspunkt des Entlade-Waerters (siehe evict.py fuer das Warum).

Aufruf:
    python3 evict_main.py            # entlaedt
    python3 evict_main.py --dry-run  # sagt nur, was es taete

Laeuft als launchd-Job 'ai.whitestag.model-evict' alle 10 Minuten.
"""
import json
import os
import subprocess
import sys
import time

from config import load_resident_set
from evict import bericht, erlaubte_keys, plan_evictions

RUHEFRIST_MIN = 20
LOG = os.path.expanduser("~/.paperclip/logs/model-evict.log")
STATUS = os.path.expanduser("~/.paperclip/logs/model-evict-last.json")
HIER = os.path.dirname(os.path.abspath(__file__))


def run(get_ps_json, unload, set_path, jetzt_ms, trocken=False,
        ruhefrist_min=RUHEFRIST_MIN):
    desired = load_resident_set(set_path)
    erlaubt = erlaubte_keys(desired, "studio")
    loaded = json.loads(get_ps_json())
    if isinstance(loaded, dict):
        loaded = loaded.get("models", [])

    ruhefrist_ms = ruhefrist_min * 60_000
    aktionen = plan_evictions(loaded, erlaubt, jetzt_ms, ruhefrist_ms)

    ergebnis = {
        "zeitpunkt": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "geladen": len(loaded),
        "entladen": [],
        "fehlgeschlagen": [],
        "frei_gb": 0.0,
        "trocken": trocken,
        "uebersicht": bericht(loaded, erlaubt, jetzt_ms, ruhefrist_ms),
    }

    for a in aktionen:
        if trocken:
            ergebnis["entladen"].append(a["identifier"])
            ergebnis["frei_gb"] += a["gigabyte"]
            continue
        rc, ausgabe = unload(a["identifier"])
        if rc == 0:
            ergebnis["entladen"].append(a["identifier"])
            ergebnis["frei_gb"] += a["gigabyte"]
        else:
            ergebnis["fehlgeschlagen"].append(f"{a['identifier']}: {ausgabe.strip()[:200]}")

    ergebnis["frei_gb"] = round(ergebnis["frei_gb"], 2)
    return ergebnis


def log_zeilen(ergebnis, ausfuehrlich=False):
    """Der Job laeuft alle 10 Minuten und hat fast immer nichts zu tun.
    Dann bleibt es bei EINER Zeile — die Begruendung je Modell steht nur
    dort, wo wirklich etwas passiert ist (oder auf Wunsch)."""
    kopf = (f"===== {ergebnis['zeitpunkt']} model-evict"
            f"{' (Probelauf)' if ergebnis['trocken'] else ''}")
    passiert = ergebnis["entladen"] or ergebnis["fehlgeschlagen"]

    if not passiert and not ausfuehrlich:
        return [f"{kopf}: {ergebnis['geladen']} geladen, nichts zu tun"]

    zeilen = [kopf]
    zeilen += ergebnis["uebersicht"]
    if ergebnis["entladen"]:
        zeilen.append(f"  -> entladen: {', '.join(ergebnis['entladen'])}"
                      f"  ({ergebnis['frei_gb']} GB frei)")
    for f in ergebnis["fehlgeschlagen"]:
        zeilen.append(f"  -> FEHLER {f}")
    return zeilen


def _schreibe_log(ergebnis, ausfuehrlich=False):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a") as fh:
        fh.write("\n".join(log_zeilen(ergebnis, ausfuehrlich)) + "\n")


def main() -> int:
    trocken = "--dry-run" in sys.argv
    lms = os.path.expanduser("~/.lmstudio/bin/lms")

    def ps_json():
        p = subprocess.run([lms, "ps", "--json"], capture_output=True, text=True,
                           timeout=60)
        return p.stdout or "[]"

    def unload(identifier):
        p = subprocess.run([lms, "unload", identifier], capture_output=True,
                           text=True, timeout=120)
        return p.returncode, (p.stdout or "") + (p.stderr or "")

    try:
        ergebnis = run(ps_json, unload, os.path.join(HIER, "resident-set.json"),
                       int(time.time() * 1000), trocken=trocken)
    except Exception as fehler:                      # LM Studio aus, JSON kaputt
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a") as fh:
            fh.write(f"===== {time.strftime('%Y-%m-%dT%H:%M:%S')} model-evict "
                     f"ABBRUCH: {type(fehler).__name__}: {fehler}\n")
        return 1

    _schreibe_log(ergebnis, ausfuehrlich="--verbose" in sys.argv or trocken)
    with open(STATUS, "w") as fh:
        json.dump({k: v for k, v in ergebnis.items() if k != "uebersicht"},
                  fh, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in ergebnis.items() if k != "uebersicht"},
                     ensure_ascii=False))
    return 1 if ergebnis["fehlgeschlagen"] else 0


if __name__ == "__main__":
    sys.exit(main())
