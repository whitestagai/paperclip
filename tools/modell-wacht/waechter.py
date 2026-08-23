#!/usr/bin/env python3
"""Modell-Aufsicht — sammelt alle fest verdrahteten LM-Studio-Modellnamen im
Haus und hält sie gegen den tatsächlichen Bestand.

Gibt JSON auf stdout. Repariert nichts.

Aufruf:  ./waechter.py            (JSON)
         ./waechter.py --text     (kurzer Klartext für die Konsole)

Läuft unter dem System-Python 3.9 — keine Fremdpakete, keine 3.10-Syntax.
"""

import json
import os
import plistlib
import re
import sqlite3
import subprocess
import sys
import urllib.request
from typing import Any, Dict, List, Tuple

from pruefung import Bestand, Referenz, bewerte

LM_STUDIO = os.environ.get("MODELL_WACHT_LMSTUDIO", "http://127.0.0.1:1234")
PAPERCLIP_DSN = dict(host="127.0.0.1", port="54329", user="paperclip", dbname="paperclip")
PAPERCLIP_PW = os.environ.get("MODELL_WACHT_PGPASSWORD", "paperclip")

VAULT = os.path.expanduser("~/Obsidian/WHITESTAG-Vault")
REPO = os.environ.get(
    "MODELL_WACHT_REPO",
    os.path.expanduser("~/Library/CloudStorage/SynologyDrive-Mac/Claude Code MAC/Paperclip"),
)
N8N_DB = os.path.expanduser("~/.n8n/database.sqlite")
PII_PLIST = os.path.expanduser("~/Library/LaunchAgents/io.piiproxy.server.plist")
DETEKTOR = os.path.join(VAULT, "projekte/obsidian/link-detektor-v11")


# ===================================================================== rein


def bestand_aus_api(payload: Dict[str, Any]) -> Bestand:
    vorhanden, geladen = set(), set()
    for m in payload.get("data") or []:
        mid = m.get("id")
        if not mid:
            continue
        vorhanden.add(mid)
        if m.get("state") == "loaded":
            geladen.add(mid)
    return Bestand(vorhanden=frozenset(vorhanden), geladen=frozenset(geladen))


def referenzen_aus_agenten(zeilen: List[Dict[str, Any]]) -> List[Referenz]:
    """Fünf Stellen je Agent — das Primärmodell allein reicht nicht.

    Der Vorfall vom 23.08. steckte im `cheap`-Profil unter `runtime_config`,
    das man leicht übersieht, weil dieselbe Struktur zusätzlich (und
    wirkungslos) unter `adapter_config` liegen kann.
    """
    refs = []
    for z in zeilen:
        quelle = "Paperclip-Agent {}/{}".format(z.get("firma", "?"), z.get("name", "?"))
        ac = z.get("adapter_config") or {}
        for feld in ("model", "defaultModel", "fallbackModel"):
            wert = ac.get(feld)
            if isinstance(wert, str) and wert:
                refs.append(Referenz(quelle, "adapterConfig." + feld, wert))
        profile = ((z.get("runtime_config") or {}).get("modelProfiles")) or {}
        for pname, p in sorted(profile.items()):
            pac = (p or {}).get("adapterConfig") or {}
            for feld in ("model", "fallbackModel"):
                wert = pac.get(feld)
                if isinstance(wert, str) and wert:
                    refs.append(
                        Referenz(
                            quelle,
                            "runtimeConfig.modelProfiles.{}.{}".format(pname, feld),
                            wert,
                        )
                    )
    return refs


def referenzen_aus_n8n(workflows: List[Dict[str, Any]]) -> List[Referenz]:
    """Nur ausführende Knoten, nur literale Werte.

    Zwei Fallen, beide am 23.08. real erlebt:
    - Sticky Notes enthalten oft alte Modellnamen als Kommentar. Sie werden
      nie ausgeführt; wer sie mitzählt, meldet Geister.
    - Die Chat-Knoten beziehen ihr Modell über `={{ ... }}` aus einem
      Konfigurationsknoten. Der Ausdruck ist statisch nicht auflösbar; der
      literale Wert steht im `set`-Knoten und wird dort abgegriffen.
    """
    refs = []
    for wf in workflows:
        wfname = wf.get("name", "?")
        for node in wf.get("nodes") or []:
            typ = node.get("type") or ""
            if "stickyNote" in typ:
                continue
            nname = node.get("name", "?")
            params = node.get("parameters") or {}
            zuweisungen = ((params.get("assignments") or {}).get("assignments")) or []
            for a in zuweisungen:
                name = a.get("name") or ""
                wert = a.get("value")
                if not isinstance(wert, str) or wert.startswith("="):
                    continue
                if re.search(r"model|modell", name, re.I):
                    refs.append(
                        Referenz(
                            "n8n «{}»".format(wfname),
                            "{}.{}".format(nname, name),
                            wert,
                        )
                    )
    return refs


def referenzen_aus_template(text: str, quelle: str) -> List[Referenz]:
    m = re.search(r'^\s*modell:\s*"([^"]+)"', text, re.M)
    return [Referenz(quelle, "llm.modell", m.group(1))] if m else []


def referenzen_aus_satellit(text: str) -> List[Referenz]:
    m = re.search(r'^\s*CHAT_MODEL\s*=\s*"([^"]+)"', text, re.M)
    return [Referenz("Wake-Satellit", "sat_config.CHAT_MODEL", m.group(1))] if m else []


# ====================================================================== I/O


def _hole(fn, beschreibung, unlesbar):
    """Jede Quelle einzeln absichern — ein Ausfall darf die Prüfung nicht
    stumm verkürzen, sondern wird selbst zum Befund."""
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - bewusst breit, fail-closed
        unlesbar.append("{}: {}".format(beschreibung, exc))
        return []


def _psql(dsn, sql, passwort):
    env = dict(os.environ, PGPASSWORD=passwort)
    cmd = [
        "psql", "-h", dsn["host"], "-p", dsn["port"], "-U", dsn["user"],
        "-d", dsn["dbname"], "-t", "-A", "-F", "\x1f", "-c", sql,
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=30)
    if out.returncode != 0:
        raise RuntimeError((out.stderr or "").strip().split("\n")[-1][:160])
    return [z for z in out.stdout.strip().split("\n") if z]


def hole_bestand() -> Bestand:
    with urllib.request.urlopen(LM_STUDIO + "/api/v0/models", timeout=20) as r:
        return bestand_aus_api(json.loads(r.read().decode()))


def hole_agenten() -> List[Referenz]:
    zeilen = _psql(
        PAPERCLIP_DSN,
        "SELECT c.name, a.name, coalesce(a.adapter_config::text,'{}'), "
        "coalesce(a.runtime_config::text,'{}') "
        "FROM agents a JOIN companies c ON c.id=a.company_id ORDER BY c.name, a.name;",
        PAPERCLIP_PW,
    )
    rows = []
    for z in zeilen:
        teile = z.split("\x1f")
        if len(teile) != 4:
            continue
        rows.append(
            {
                "firma": teile[0],
                "name": teile[1],
                "adapter_config": json.loads(teile[2]),
                "runtime_config": json.loads(teile[3]),
            }
        )
    return referenzen_aus_agenten(rows)


def hole_link_detektor() -> List[Referenz]:
    """Das Modell steht in der DATENBANK (`ld.config`), nicht in der `.env` —
    die speist die Spalte nur beim Migrieren. Beide Instanzen einzeln prüfen."""
    refs = []
    for datei, dbname in ((".env", "link_detektor"), (".env.clara", "link_detektor_clara")):
        pfad = os.path.join(DETEKTOR, datei)
        pw = ""
        with open(pfad, "r", encoding="utf-8") as fh:
            for zeile in fh:
                if zeile.startswith("PGPASSWORD="):
                    pw = zeile.split("=", 1)[1].strip()
        dsn = dict(host="127.0.0.1", port="5432", user=os.environ.get("USER", ""), dbname=dbname)
        zeilen = _psql(dsn, "SELECT llm_model, embedding_model FROM ld.config WHERE id=1;", pw)
        for z in zeilen:
            teile = z.split("\x1f")
            quelle = "Link-Detektor {}".format(dbname)
            if teile and teile[0]:
                refs.append(Referenz(quelle, "ld.config.llm_model", teile[0]))
            if len(teile) > 1 and teile[1]:
                refs.append(Referenz(quelle, "ld.config.embedding_model", teile[1]))
    return refs


def hole_n8n() -> List[Referenz]:
    con = sqlite3.connect("file:{}?mode=ro".format(N8N_DB), uri=True, timeout=20)
    try:
        workflows = []
        for name, nodes in con.execute("SELECT name, nodes FROM workflow_entity WHERE active=1"):
            try:
                workflows.append({"name": name, "nodes": json.loads(nodes)})
            except Exception:
                continue
        return referenzen_aus_n8n(workflows)
    finally:
        con.close()


def hole_tagger() -> List[Referenz]:
    basis = os.path.join(REPO, "obsidian-tagger", "templates")
    refs = []
    for datei, quelle in (
        ("frontmatter-template.yaml", "Obsidian-Tagger WHITESTAG"),
        ("frontmatter-template-clara.yaml", "Obsidian-Tagger Clara Sound"),
    ):
        with open(os.path.join(basis, datei), "r", encoding="utf-8") as fh:
            refs += referenzen_aus_template(fh.read(), quelle)
    return refs


def hole_satellit() -> List[Referenz]:
    pfad = os.path.join(REPO, "tools", "wake-satellite", "sat_config.py")
    with open(pfad, "r", encoding="utf-8") as fh:
        return referenzen_aus_satellit(fh.read())


def hole_pii_proxy() -> List[Referenz]:
    with open(PII_PLIST, "rb") as fh:
        env = plistlib.load(fh).get("EnvironmentVariables") or {}
    refs = []
    for schluessel, feld in (
        ("PII_PROXY_CLASSIFIER_MODEL", "CLASSIFIER_MODEL"),
        ("PII_PROXY_CLASSIFIER_FALLBACK_MODEL", "CLASSIFIER_FALLBACK_MODEL"),
    ):
        if env.get(schluessel):
            refs.append(Referenz("PII-Proxy", feld, env[schluessel]))
    return refs


QUELLEN: Tuple = (
    (hole_agenten, "Paperclip-Agenten"),
    (hole_link_detektor, "Link-Detektor-Datenbanken"),
    (hole_n8n, "n8n-Datenbank"),
    (hole_tagger, "Obsidian-Tagger-Templates"),
    (hole_satellit, "Wake-Satellit"),
    (hole_pii_proxy, "PII-Proxy-Plist"),
)


def main() -> int:
    unlesbar: List[str] = []
    try:
        bestand = hole_bestand()
    except Exception as exc:  # noqa: BLE001
        unlesbar.append("LM Studio {}: {}".format(LM_STUDIO, exc))
        bestand = Bestand(frozenset(), frozenset())

    referenzen: List[Referenz] = []
    for fn, name in QUELLEN:
        referenzen += _hole(fn, name, unlesbar)

    befunde = bewerte(referenzen, bestand, unlesbar)
    ergebnis = {
        "ok": not befunde,
        "geprueft": len(referenzen),
        "quellen": len(QUELLEN),
        "bestand": {"vorhanden": len(bestand.vorhanden), "geladen": len(bestand.geladen)},
        "befunde": [b._asdict() for b in befunde],
    }

    if "--text" in sys.argv:
        print("{} Referenzen aus {} Quellen gegen {} Modelle geprüft.".format(
            len(referenzen), len(QUELLEN), len(bestand.vorhanden)))
        if not befunde:
            print("Kein Befund.")
        for b in befunde:
            print("[{}] {}".format(b.schwere.upper(), b.text))
    else:
        print(json.dumps(ergebnis, ensure_ascii=False, indent=2))

    return 1 if any(b.schwere == "hoch" for b in befunde) else 0


if __name__ == "__main__":
    sys.exit(main())
