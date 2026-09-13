#!/usr/bin/env python3
"""Agenten-Aufsicht: holt stehende Agenten zurück und meldet, wenn die interne
Selbstheilung ausgefallen ist.

Warum es ihn gibt: Am 02.09.2026 um 20:57 wechselte der Watch-Tree den Branch
und nahm die interne Selbstheilung mit (sie lag nur in feat/vorfall-abschluss).
Elf Tage lang holte niemand mehr Agenten aus `error`, und niemand merkte es —
ein fehlender Wächter meldet nichts. Dieser Wächter läuft ausserhalb der
Anwendung und überlebt deshalb Branch-Wechsel, Deployments und Abstürze.

Er meldet nur bei Zustandswechsel; der Zustand steht in ZUSTAND_DATEI und wird
bei JEDEM Lauf fortgeschrieben, sonst bleibt ein wiederkehrender Fehler beim
zweiten Mal stumm.

Start über run-melder.js (node als Türöffner) — aus python verweigert TCC den
Zugriff auf die SynologyDrive-Freigabe.
"""

import json
import os
import subprocess
import sys
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, List, Optional

from pruefung import Agent, Lage, meldung_faellig, selbstheilung_schweigt, signatur, zu_holen

API = "http://localhost:3100"
WEBHOOK = "http://127.0.0.1:5678/webhook/mailhub/send"
FROM, TO = "cto@whitestag.ai", "ws@whitestag.ai"
ZUSTAND_DATEI = os.path.expanduser("~/.paperclip/logs/agent-wacht-last.json")
AUTH = os.path.expanduser("~/.paperclip/auth.json")
MAILHUB_ENV = os.path.expanduser("~/.paperclip/instances/default/secrets/mailhub.env")

# psql wird ohne absoluten Pfad aufgerufen; mit dem minimalen launchd-PATH
# ist es sonst nicht auffindbar.
os.environ["PATH"] = "/opt/homebrew/bin:" + os.environ.get("PATH", "")


@dataclass
class Bericht:
    signatur: str
    geholt: List[str] = field(default_factory=list)
    fehlgeschlagen: List[str] = field(default_factory=list)
    stumm: bool = False
    gemeldet: bool = False


def lauf(
    lage: Lage,
    jetzt: datetime,
    resumen: Callable[[Agent], bool],
    mailen: Callable[[str, str], None],
    letzte_sig: Optional[str],
    schwelle_min: int = 20,
) -> Bericht:
    """Ein Durchgang: holen, bewerten, ggf. melden.

    Das Holen passiert unabhängig davon, ob gemeldet wird — eine unveränderte
    Lage ist ein Grund zu schweigen, kein Grund untätig zu sein.
    """
    stumm = selbstheilung_schweigt(lage, jetzt)
    sig = signatur(lage, jetzt)
    bericht = Bericht(signatur=sig, stumm=stumm)

    for a in zu_holen(lage, jetzt, schwelle_min=schwelle_min):
        try:
            if resumen(a):
                bericht.geholt.append(a.name)
            else:
                bericht.fehlgeschlagen.append(a.name)
        except Exception:
            # Ein kaputtes resume darf die Runde nicht beenden.
            bericht.fehlgeschlagen.append(a.name)

    if meldung_faellig(sig, letzte_sig):
        mailen(_betreff(bericht, lage), _text(bericht, lage, jetzt))
        bericht.gemeldet = True

    return bericht


def _betreff(b: Bericht, lage: Lage) -> str:
    n = len(lage.agenten_in_error)
    if b.stumm:
        return f"Agenten-Aufsicht: Selbstheilung reagiert nicht — {n} Agent(en) in error"
    return f"Agenten-Aufsicht: {n} Agent(en) in error, {len(b.geholt)} zurueckgeholt"


def _text(b: Bericht, lage: Lage, jetzt: datetime) -> str:
    zeilen = [f"Stand {jetzt:%Y-%m-%d %H:%M}", ""]
    if b.stumm:
        letzter = f"{lage.letzter_ledger:%Y-%m-%d %H:%M}" if lage.letzter_ledger else "nie"
        zeilen += [
            "ACHTUNG: Die interne Selbstheilung schreibt nicht mehr.",
            f"Letzter Ledger-Eintrag: {letzter}.",
            "Pruefen, ob der Code im laufenden Stand ist (Branch-Wechsel?).",
            "",
        ]
    for a in lage.agenten_in_error:
        dauer = int((jetzt - a.error_seit).total_seconds() // 60)
        zeilen.append(f"  {a.name}: seit {dauer} Minuten in error")
    if b.geholt:
        zeilen += ["", "Zurueckgeholt: " + ", ".join(b.geholt)]
    if b.fehlgeschlagen:
        zeilen += ["Fehlgeschlagen: " + ", ".join(b.fehlgeschlagen)]
    return "\n".join(zeilen)


# --- IO ----------------------------------------------------------------------


def _psql(sql: str) -> List[List[str]]:
    env = dict(os.environ, PGPASSWORD="paperclip")
    out = subprocess.run(
        ["psql", "-h", "127.0.0.1", "-p", "54329", "-U", "paperclip", "-d", "paperclip",
         "-tA", "-F", "\t", "-c", sql],
        capture_output=True, text=True, env=env,
    ).stdout
    return [z.split("\t") for z in out.splitlines() if z.strip()]


def _zeit(s: str) -> Optional[datetime]:
    s = s.strip()
    if not s:
        return None
    return datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")


def lies_lage() -> Lage:
    agenten = [
        Agent(name=r[1], agent_id=r[0], company_id=r[2], error_seit=_zeit(r[3]) or datetime.now())
        for r in _psql(
            "SELECT id, name, company_id, coalesce(last_heartbeat_at, now()) "
            "FROM agents WHERE status = 'error'"
        )
    ]
    letzter = _psql("SELECT coalesce(max(updated_at)::text, '') FROM agent_self_heal_ledger")
    # updated_at, nicht nur die blosse ID: eine offene Zeile zaehlt nur als
    # aktive Betreuung, solange sie frisch ist (siehe pruefung._wird_betreut).
    offen = _psql(
        "SELECT agent_id, updated_at FROM agent_self_heal_ledger WHERE resolved_at IS NULL"
    )
    betreut = {}
    for r in offen:
        z = _zeit(r[1])
        if z is not None:
            betreut[r[0]] = z
    return Lage(
        agenten_in_error=agenten,
        letzter_ledger=_zeit(letzter[0][0]) if letzter else None,
        betreut=betreut,
    )


def _token() -> str:
    with open(AUTH, encoding="utf-8") as fh:
        return json.load(fh)["credentials"][API]["token"]


def resume_via_api(a: Agent) -> bool:
    req = urllib.request.Request(
        f"{API}/api/agents/{a.agent_id}/resume",
        data=b"",
        headers={"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status < 300


def _mailhub_secret() -> str:
    with open(MAILHUB_ENV, encoding="utf-8") as fh:
        for zeile in fh:
            if zeile.startswith("MAILHUB_SECRET="):
                return zeile.split("=", 1)[1].strip().strip('"')
    raise RuntimeError("MAILHUB_SECRET nicht gefunden in " + MAILHUB_ENV)


def mail_an_walter(betreff: str, text: str) -> None:
    nutzlast = json.dumps(
        {"from": FROM, "to": TO, "subject": betreff, "text": text, "html": "", "attachments": []}
    ).encode()
    req = urllib.request.Request(
        WEBHOOK,
        data=nutzlast,
        headers={"Content-Type": "application/json", "X-Mailhub-Secret": _mailhub_secret()},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        if r.status >= 300:
            raise RuntimeError(f"Mailhub antwortete {r.status}")


def lies_zustand() -> Optional[str]:
    try:
        with open(ZUSTAND_DATEI, encoding="utf-8") as fh:
            return json.load(fh).get("signatur")
    except (OSError, ValueError):
        return None


def schreib_zustand(sig: str) -> None:
    os.makedirs(os.path.dirname(ZUSTAND_DATEI), exist_ok=True)
    with open(ZUSTAND_DATEI, "w", encoding="utf-8") as fh:
        json.dump({"signatur": sig, "stand": datetime.now().isoformat(timespec="seconds")}, fh)


def main() -> int:
    jetzt = datetime.now()
    lage = lies_lage()
    b = lauf(lage, jetzt, resume_via_api, mail_an_walter, lies_zustand())
    # Bei JEDEM Lauf fortschreiben, sonst bleibt ein wiederkehrender Fehler stumm.
    schreib_zustand(b.signatur)
    print(
        f"{jetzt:%H:%M} error={len(lage.agenten_in_error)} geholt={len(b.geholt)} "
        f"fehlgeschlagen={len(b.fehlgeschlagen)} stumm={b.stumm} gemeldet={b.gemeldet}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
