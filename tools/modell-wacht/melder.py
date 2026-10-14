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

import html
import json
import os
import sys
import urllib.request
from datetime import datetime

sys.path.insert(0, os.path.expanduser("~/.paperclip/scripts"))

from pruefung import entwarnung_faellig, meldung_faellig, signatur  # noqa: E402
from waechter import hole_soll, pruefe  # noqa: E402

LOG = os.path.expanduser("~/.paperclip/logs/modell-wacht.log")
ZUSTAND = os.path.expanduser("~/.paperclip/logs/modell-wacht-last.json")
FIRMA = os.environ.get("MODELL_WACHT_FIRMA", "9cebf3cf-efe8-4597-a400-f06488900a87")

# Mail statt nur Issue seit 12.10.2026: Am 10.10. legte der Melder um 10:42 ein
# Issue an — ohne Assignee, im backlog. Niemand sah es; die RTX blieb zwei Tage
# weg. Ein Issue ist eine Akte, kein Alarm.
MAILHUB = "http://127.0.0.1:5678/webhook/mailhub/send"
MAILHUB_ENV = os.path.expanduser("~/.paperclip/instances/default/secrets/mailhub.env")
MAIL_VON = "cto@whitestag.ai"
MAIL_AN = os.environ.get("MODELL_WACHT_MAIL_AN", "ws@whitestag.ai")


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


def _html(titel: str, absaetze: list, punkte: list) -> str:
    teile = ['<div style="font-family:-apple-system,Segoe UI,sans-serif;max-width:640px;color:#1a1a1a">',
             "<h2>{}</h2>".format(html.escape(titel))]
    if punkte:
        teile.append("<ul>" + "".join("<li>{}</li>".format(html.escape(p)) for p in punkte) + "</ul>")
    teile += ['<p style="color:#555">{}</p>'.format(html.escape(a)) for a in absaetze]
    teile.append("</div>")
    return "".join(teile)


GERAETE_ARTEN = ("geraet_getrennt", "modell_fehlt", "falsches_geraet")


def betroffene_modelle(befunde, soll) -> set:
    """Modelle, die wegen eines Geräte-Befunds fehlen — deren «ID unbekannt»-
    Meldungen sind Folge, nicht Ursache."""
    getrennt = {b.quelle.split("«", 1)[-1].rstrip("»") for b in befunde if b.art == "geraet_getrennt"}
    modelle = {b.modell for b in befunde if b.art in ("modell_fehlt", "falsches_geraet") and b.modell}
    return modelle | {m for m, v in soll.items() if v.get("geraet") in getrennt}


def alarm_mail(befunde, kopfzeile: str, issue, geraete_modelle=None) -> tuple:
    """(Betreff, Text, HTML) der Alarm-Mail.

    Nur die HARTEN Befunde im Wortlaut. Am 10.10. stand der Geräteausfall
    zwischen dreißig «nicht geladen»-Zeilen — wer das liest, findet ihn nicht.
    Die niedrigen werden nur gezählt; vollständig stehen sie im Issue.

    Geräte-Befunde stehen zuerst und bestimmen den Betreff. «ID unbekannt»
    für ein Modell aus `geraete_modelle` ist Folge des Geräte-Befunds und wird
    zu einer Zeile gebündelt — am 14.10. waren es 48 solcher Zeilen vor dem
    einen, der die Ursache nannte.
    """
    geraete_modelle = geraete_modelle or set()
    hart = [b for b in befunde if b.schwere == "hoch"]
    niedrig = len(befunde) - len(hart)
    folge = [b for b in hart if b.art == "unbekannt" and b.modell in geraete_modelle]
    hart = sorted(
        (b for b in hart if b not in folge),
        key=lambda b: 0 if b.art in GERAETE_ARTEN else 1,
    )
    betreff = "Modell-Aufsicht: {}".format(hart[0].text.split(". ")[0].rstrip(".") if hart else "Befund")
    if len(hart) > 1:
        betreff += " (+{} weitere)".format(len(hart) - 1)
    absaetze = [kopfzeile]
    if niedrig:
        absaetze.append("Dazu {} niedrige Befunde (kein Handlungsbedarf), vollständig im Issue.".format(niedrig))
    absaetze.append("Issue: {}".format(issue or "nicht angelegt"))
    absaetze.append("Nächste Mail erst, wenn sich der Befundstand ändert oder alles wieder grün ist.")
    punkte = [b.text for b in hart]
    if folge:
        punkte.insert(
            sum(1 for b in hart if b.art in GERAETE_ARTEN),
            "Folge davon: {} Konfigurationen zeigen auf {} — Liste im Issue.".format(
                len(folge), ", ".join(sorted({b.modell for b in folge}))
            ),
        )
    text ="\n".join(["- " + p for p in punkte] + [""] + absaetze)
    return betreff, text, _html(betreff, absaetze, punkte)


def entwarnung_mail(kopfzeile: str) -> tuple:
    betreff = "Modell-Aufsicht: wieder grün"
    absaetze = ["Keine harten Befunde mehr.", kopfzeile]
    return betreff, "\n".join(absaetze), _html(betreff, absaetze, [])


def _mailhub_secret() -> str:
    with open(MAILHUB_ENV, encoding="utf-8") as fh:
        for zeile in fh:
            if zeile.startswith("MAILHUB_SECRET="):
                return zeile.split("=", 1)[1].strip().strip('"')
    raise RuntimeError("MAILHUB_SECRET fehlt in " + MAILHUB_ENV)


def _sende(betreff: str, text: str, html_text: str) -> None:
    daten = json.dumps({"from": MAIL_VON, "to": MAIL_AN, "subject": betreff,
                        "text": text, "html": html_text, "attachments": []}).encode()
    req = urllib.request.Request(MAILHUB, data=daten, headers={
        "Content-Type": "application/json", "X-Mailhub-Secret": _mailhub_secret()})
    with urllib.request.urlopen(req, timeout=30) as r:
        if not 200 <= r.status < 300:
            raise RuntimeError("Mailhub HTTP {}".format(r.status))


def main() -> int:
    befunde, ergebnis = pruefe()
    sig = signatur(befunde)
    zuletzt = _zuletzt()
    faellig = meldung_faellig(sig, zuletzt)

    if faellig:
        issue = None
        try:
            issue = _melde(befunde, ergebnis)
            _protokoll("MELDUNG {} Befund(e), Issue {}".format(len(sig), issue))
        except Exception as exc:  # noqa: BLE001
            _protokoll("MELDUNG FEHLGESCHLAGEN ({}): {}".format(len(sig), exc))
        # Getrennt abgesichert: scheitert das Issue, soll die Mail trotzdem raus.
        try:
            try:
                betroffen = betroffene_modelle(befunde, hole_soll())
            except Exception:  # noqa: BLE001 - ohne Soll nur ungebündelt, nie ohne Mail
                betroffen = set()
            _sende(*alarm_mail(befunde, ergebnis["kopfzeile"], issue, betroffen))
            _protokoll("MAIL an {} verschickt".format(MAIL_AN))
        except Exception as exc:  # noqa: BLE001
            _protokoll("MAIL FEHLGESCHLAGEN: {}".format(exc))
    elif entwarnung_faellig(sig, zuletzt):
        try:
            _sende(*entwarnung_mail(ergebnis["kopfzeile"]))
            _protokoll("ENTWARNUNG an {} verschickt: {}".format(MAIL_AN, ergebnis["kopfzeile"]))
        except Exception as exc:  # noqa: BLE001
            _protokoll("ENTWARNUNG FEHLGESCHLAGEN: {}".format(exc))
    elif sig:
        _protokoll("unveraendert: {} harte Befunde, keine neue Meldung".format(len(sig)))
    else:
        _protokoll("ok: {}".format(ergebnis["kopfzeile"]))

    _schreibe_zustand(sig, ergebnis)
    return 1 if sig else 0


if __name__ == "__main__":
    sys.exit(main())
