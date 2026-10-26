#!/usr/bin/env python3
"""Tägliche Arbeitszeit-Mail: wie lange Walter an welchen Claude-Code-Projekten war.

Woher die Zahlen kommen:
  1. STUNDEN aus den Sitzungsprotokollen von Claude Code
     (~/.claude/projects/*/*.jsonl). Jede Nachricht trägt einen Zeitstempel.
     Liegen zwischen zwei Nachrichten höchstens PAUSE_MIN Minuten, gilt die
     Zeit dazwischen als Arbeit; längere Lücken sind Pause.
     Die Vault-Chatverläufe kennen nur das Datum, keine Uhrzeit — daraus
     lässt sich keine Dauer berechnen.
  2. CHATS aus dem Vault (Claude Code/<Projekt>/yyyy-mm-tt Chatverlauf *.md):
     Anzahl der Chatverläufe je Projekt und Zeitraum.

Claude Code löscht seine Protokolle nach etwa 30 Tagen. Deshalb hält ein
eigenes Register (SQLite) die gemessenen Minuten fest; Sitzungen, deren
Protokoll verschwunden ist, bleiben dort erhalten.

Gleichzeitigkeit: Laufen in einer Minute Sitzungen zweier Projekte, bekommt
jedes eine halbe Minute. So ergibt die Summe der Projekte die tatsächlich
gearbeitete Zeit und die Prozente addieren sich zu 100.

Nicht gezählt: Läufe der Paperclip-Agenten (entrypoint "sdk-cli") und
Sitzungen in Agenten-Arbeitsordnern.

Aufruf:
  arbeitszeit.py                       # Bericht für gestern, senden
  arbeitszeit.py --dry-run --out x.html
  arbeitszeit.py --datum 2026-10-25    # Berichtstag festlegen
  arbeitszeit.py --nur-einlesen --quelle DIR   # Nachfüllen aus Sicherungen
"""
from __future__ import annotations

import argparse
import glob
import html
import json
import os
import re
import sqlite3
import sys
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

BERLIN = ZoneInfo("Europe/Berlin")
HOME = os.path.expanduser("~")

PROTOKOLLE = os.path.join(HOME, ".claude", "projects")
VAULT_CC = os.path.join(HOME, "Obsidian", "WHITESTAG-Vault", "Claude Code")
# Unter ~/.claude, weil system-secrets-backup diesen Ordner nach Hetzner sichert.
REGISTER = os.path.join(HOME, ".claude", "arbeitszeit", "claude-arbeitszeit.sqlite")

PAUSE_MIN = 15

MAILHUB_URL = "http://127.0.0.1:5678/webhook/mailhub/send"
MAILHUB_ENV = os.path.join(HOME, ".paperclip", "instances", "default", "secrets", "mailhub.env")
FROM_ADDR = "cto@whitestag.ai"
TO_ADDR = "ws@whitestag.ai"

# Ordnername im Arbeitsverzeichnis → Projektname wie im Vault.
ALIAS = {
    "WHITESTAG-ACADEMY": "WHITESTAG.ACADEMY",
    "whitestag-academy-web": "WHITESTAG.ACADEMY",
    "paperclip-adapter-lmstudio": "Paperclip",
    "Claude Code MAC": "Sonstiges",
}

WOCHENTAGE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
MONATE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August",
          "September", "Oktober", "November", "Dezember"]

# Kategorische Reihenfolge der dataviz-Referenzpalette (hell), feste Zuordnung
# nach Rang im Jahr. Alles ab Rang 8 fällt in „Weitere".
FARBEN = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6"]
FARBE_WEITERE = "#898781"
WEITERE = "Weitere"

INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#898781"
LINIE = "#e1e0d9"
FLAECHE = "#fcfcfb"
KOPF = "#012a3e"


def log(msg: str) -> None:
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}", flush=True)


# --- Projektzuordnung ---------------------------------------------------------
def projekt_aus_cwd(cwd: str | None) -> str:
    if not cwd:
        return "Sonstiges"
    teile = [t for t in cwd.split("/") if t]
    name = None
    for anker in ("Claude Code MAC", "Developer"):
        if anker in teile:
            i = teile.index(anker)
            rest = teile[i + 1:]
            if rest and rest[0] == "Apps" and len(rest) > 1:
                rest = rest[1:]
            name = rest[0] if rest else anker
            break
    if name is None:
        if ".paperclip" in teile or "whitestag-live" in teile:
            name = "Paperclip"
        elif ".claude" in teile:
            name = "Claude-Konfiguration"
        elif teile[:1] in (["tmp"], ["private"]):
            name = "Sonstiges"
        else:
            name = teile[-1] if teile else "Sonstiges"
    return ALIAS.get(name, name)


def ist_agentenlauf(entrypoint: str | None, cwd: str | None) -> bool:
    if entrypoint == "sdk-cli":
        return True
    return bool(cwd and "/.paperclip/instances/" in cwd)


# --- Protokolle lesen ---------------------------------------------------------
def lies_sitzung(pfad: str) -> dict | None:
    """Zeitstempel, Einstieg und erstes Arbeitsverzeichnis einer Sitzung."""
    zeiten = []
    entrypoint = None
    cwd = None
    with open(pfad, encoding="utf-8", errors="replace") as fh:
        for zeile in fh:
            try:
                d = json.loads(zeile)
            except ValueError:
                continue
            if entrypoint is None and d.get("entrypoint"):
                entrypoint = d["entrypoint"]
            if cwd is None and d.get("cwd"):
                cwd = d["cwd"]
            if d.get("type") in ("user", "assistant") and d.get("timestamp"):
                try:
                    zeiten.append(datetime.fromisoformat(d["timestamp"].replace("Z", "+00:00")))
                except ValueError:
                    continue
    if not zeiten:
        return None
    return {"id": os.path.splitext(os.path.basename(pfad))[0], "zeiten": sorted(zeiten),
            "entrypoint": entrypoint, "cwd": cwd}


def minuten_der_sitzung(zeiten: list[datetime], pause_min: int = PAUSE_MIN) -> set[int]:
    """Aktive Minuten (Unix-Minute) einer Sitzung.

    Jede Nachricht markiert ihre Minute; liegen zwei Nachrichten höchstens
    pause_min auseinander, gelten auch alle Minuten dazwischen als aktiv.
    """
    aktiv: set[int] = set()
    vorher = None
    for t in zeiten:
        m = int(t.timestamp() // 60)
        aktiv.add(m)
        if vorher is not None and 0 < m - vorher <= pause_min:
            aktiv.update(range(vorher + 1, m))
        vorher = m
    return aktiv


def bereiche(minuten: set[int]) -> list[tuple[int, int]]:
    """Minutenmenge als geschlossene Bereiche [von, bis] (spart Platz im Register)."""
    aus: list[tuple[int, int]] = []
    for m in sorted(minuten):
        if aus and m == aus[-1][1] + 1:
            aus[-1] = (aus[-1][0], m)
        else:
            aus.append((m, m))
    return aus


# --- Register -----------------------------------------------------------------
def oeffne_register(pfad: str = REGISTER) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    db = sqlite3.connect(pfad)
    db.executescript("""
        CREATE TABLE IF NOT EXISTS sitzungen (
            id TEXT PRIMARY KEY, projekt TEXT NOT NULL, cwd TEXT,
            nachrichten INTEGER NOT NULL, aktualisiert TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS bereiche (
            sitzung TEXT NOT NULL, von INTEGER NOT NULL, bis INTEGER NOT NULL);
        CREATE INDEX IF NOT EXISTS bereiche_sitzung ON bereiche(sitzung);
    """)
    return db


def uebernimm(db: sqlite3.Connection, s: dict) -> bool:
    """Sitzung ins Register schreiben. Eine ältere, kürzere Fassung derselben
    Sitzung (z.B. aus einer Sicherung) überschreibt nie eine längere."""
    alt = db.execute("SELECT nachrichten FROM sitzungen WHERE id=?", (s["id"],)).fetchone()
    if alt and alt[0] > len(s["zeiten"]):
        return False
    projekt = projekt_aus_cwd(s["cwd"])
    db.execute("DELETE FROM bereiche WHERE sitzung=?", (s["id"],))
    db.executemany("INSERT INTO bereiche VALUES (?,?,?)",
                   [(s["id"], a, b) for a, b in bereiche(minuten_der_sitzung(s["zeiten"]))])
    db.execute("INSERT OR REPLACE INTO sitzungen VALUES (?,?,?,?,?)",
               (s["id"], projekt, s["cwd"], len(s["zeiten"]), datetime.now(timezone.utc).isoformat()))
    return True


def lies_ein(db: sqlite3.Connection, wurzel: str) -> tuple[int, int]:
    """Alle Hauptprotokolle unter wurzel/<projektordner>/*.jsonl einlesen."""
    neu = uebersprungen = 0
    for pfad in glob.glob(os.path.join(wurzel, "*", "*.jsonl")):
        s = lies_sitzung(pfad)
        if not s or ist_agentenlauf(s["entrypoint"], s["cwd"]):
            uebersprungen += 1
            continue
        if uebernimm(db, s):
            neu += 1
    db.commit()
    return neu, uebersprungen


# --- Auswertung ---------------------------------------------------------------
def minuten_je_tag_und_projekt(db: sqlite3.Connection, von: date, bis: date) -> dict:
    """{datum: {projekt: minuten}} im Zeitraum [von, bis] (Berliner Kalendertage).

    Gleichzeitige Projekte teilen sich die Minute zu gleichen Teilen.
    """
    start = int(datetime(von.year, von.month, von.day, tzinfo=BERLIN).timestamp() // 60)
    ende_tag = bis + timedelta(days=1)
    ende = int(datetime(ende_tag.year, ende_tag.month, ende_tag.day, tzinfo=BERLIN).timestamp() // 60)
    belegt: dict[int, set[str]] = defaultdict(set)
    for projekt, a, b in db.execute(
            "SELECT s.projekt, b.von, b.bis FROM bereiche b JOIN sitzungen s ON s.id=b.sitzung "
            "WHERE b.bis>=? AND b.von<?", (start, ende)):
        for m in range(max(a, start), min(b, ende - 1) + 1):
            belegt[m].add(projekt)
    aus: dict[date, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for m, projekte in belegt.items():
        tag = datetime.fromtimestamp(m * 60, BERLIN).date()
        for p in projekte:
            aus[tag][p] += 1 / len(projekte)
    return aus


def erste_messung(db: sqlite3.Connection, max_luecke_tage: int = 14) -> date | None:
    """Beginn der lückenlosen Messung.

    Einzelne alte Sitzungen (z.B. eine wieder aufgenommene vom Juni) sollen
    keinen frühen Messbeginn vortäuschen: gezählt wird ab dem ersten Tag, nach
    dem keine Lücke über max_luecke_tage mehr folgt.
    """
    tage = sorted({datetime.fromtimestamp(v * 60, BERLIN).date()
                   for (v,) in db.execute("SELECT von FROM bereiche")})
    if not tage:
        return None
    beginn = tage[0]
    for vorher, nachher in zip(tage, tage[1:]):
        if (nachher - vorher).days > max_luecke_tage:
            beginn = nachher
    return beginn


def chats_im_vault(wurzel: str = VAULT_CC) -> list[tuple[date, str]]:
    aus = []
    muster = re.compile(r"^(\d{4}-\d{2}-\d{2}) Chatverlauf .*\.md$")
    for pfad in glob.glob(os.path.join(wurzel, "**", "*.md"), recursive=True):
        m = muster.match(os.path.basename(pfad))
        if not m:
            continue
        rel = os.path.relpath(pfad, wurzel).split(os.sep)
        projekt = rel[0] if len(rel) > 1 else "Sonstiges"
        try:
            aus.append((date.fromisoformat(m.group(1)), ALIAS.get(projekt, projekt)))
        except ValueError:
            continue
    return aus


def zeitraeume(berichtstag: date) -> list[tuple[str, str, date, date]]:
    """(Schlüssel, Überschrift, von, bis) — alles bis einschließlich Berichtstag."""
    t = berichtstag
    return [
        ("tag", "Gestern", t, t),
        ("woche", "Woche", t - timedelta(days=t.weekday()), t),
        ("monat", "Monat", t.replace(day=1), t),
        ("jahr", "Jahr", t.replace(month=1, day=1), t),
    ]


def auswerten(db: sqlite3.Connection, berichtstag: date, chats: list[tuple[date, str]]) -> dict:
    perioden = zeitraeume(berichtstag)
    jahr_von = perioden[-1][2]
    tage = minuten_je_tag_und_projekt(db, min(jahr_von, berichtstag - timedelta(days=29)), berichtstag)
    werte = {}
    for key, titel, von, bis in perioden:
        summe: dict[str, float] = defaultdict(float)
        for tag, projekte in tage.items():
            if von <= tag <= bis:
                for p, m in projekte.items():
                    summe[p] += m
        anzahl: dict[str, int] = defaultdict(int)
        for d, p in chats:
            if von <= d <= bis:
                anzahl[p] += 1
        werte[key] = {"titel": titel, "von": von, "bis": bis,
                      "minuten": dict(summe), "chats": dict(anzahl),
                      "gesamt": sum(summe.values())}
    # Farbe folgt dem Projekt: Rang nach Jahresminuten, gilt für alle Grafiken.
    rang = sorted(werte["jahr"]["minuten"], key=lambda p: -werte["jahr"]["minuten"][p])
    farben = {p: FARBEN[i] for i, p in enumerate(rang[:len(FARBEN)])}
    verlauf = []
    for i in range(29, -1, -1):
        d = berichtstag - timedelta(days=i)
        verlauf.append((d, dict(tage.get(d, {}))))
    return {"berichtstag": berichtstag, "werte": werte, "farben": farben,
            "projekte": rang, "verlauf": verlauf, "seit": erste_messung(db)}


# --- Darstellung --------------------------------------------------------------
def h_text(minuten: float) -> str:
    h, m = divmod(int(round(minuten)), 60)
    return f"{h}:{m:02d} h"


def sichtbar(minuten: float) -> bool:
    """Weniger als eine angezeigte Minute erscheint nicht als „0:00 h"."""
    return int(round(minuten)) >= 1


def proz(teil: float, ganz: float) -> str:
    if not ganz:
        return "–"
    p = teil / ganz * 100
    return "< 1 %" if 0 < p < 0.5 else f"{p:.0f} %"


def datum_lang(d: date) -> str:
    return f"{WOCHENTAGE[d.weekday()]}, {d.day}. {MONATE[d.month - 1]} {d.year}"


def farbe(a: dict, p: str) -> str:
    return a["farben"].get(p, FARBE_WEITERE)


def gruppiert(a: dict, minuten: dict[str, float]) -> list[tuple[str, float]]:
    """Projekte mit eigener Farbe einzeln, der Rest als „Weitere"."""
    aus = [(p, minuten[p]) for p in a["projekte"] if p in a["farben"] and minuten.get(p)]
    rest = sum(m for p, m in minuten.items() if p not in a["farben"])
    if rest:
        aus.append((WEITERE, rest))
    return aus


def balken_100(a: dict, minuten: dict[str, float]) -> str:
    """Gestapelter 100-%-Balken, 2 px Lücke zwischen den Segmenten."""
    gesamt = sum(minuten.values())
    if not gesamt:
        return (f'<div style="height:16px;border-radius:4px;background:{LINIE}"></div>')
    zellen = []
    for p, m in gruppiert(a, minuten):
        breite = max(m / gesamt * 100, 0.6)
        zellen.append(f'<td title="{html.escape(p)}: {h_text(m)}" style="width:{breite:.2f}%;'
                      f'height:16px;background:{farbe(a, p) if p != WEITERE else FARBE_WEITERE};'
                      f'border-right:2px solid {FLAECHE};padding:0;font-size:0;line-height:0">&nbsp;</td>')
    return ('<table role="presentation" width="100%" cellspacing="0" cellpadding="0" '
            'style="border-collapse:collapse;table-layout:fixed;border-radius:4px;overflow:hidden">'
            f'<tr>{"".join(zellen)}</tr></table>')


def kacheln(a: dict) -> str:
    zellen = []
    for key in ("tag", "woche", "monat", "jahr"):
        w = a["werte"][key]
        zellen.append(
            f'<td style="width:25%;padding:12px 10px;background:#ffffff;border:1px solid {LINIE};'
            f'border-radius:6px;vertical-align:top">'
            f'<div style="font-size:12px;color:{INK2};text-transform:uppercase;letter-spacing:.04em">{w["titel"]}</div>'
            f'<div style="font-size:24px;font-weight:600;color:{INK};margin-top:4px">{h_text(w["gesamt"])}</div>'
            f'<div style="font-size:12px;color:{MUTED};margin-top:2px">{sum(w["chats"].values())} Chats im Vault</div>'
            '</td>')
    return ('<table role="presentation" width="100%" cellspacing="6" cellpadding="0" '
            f'style="border-collapse:separate"><tr>{"".join(zellen)}</tr></table>')


def anteile_grafik(a: dict) -> str:
    zeilen = []
    for key in ("tag", "woche", "monat", "jahr"):
        w = a["werte"][key]
        zeilen.append(
            f'<tr><td style="width:70px;padding:6px 8px 6px 0;font-size:13px;color:{INK2};white-space:nowrap">'
            f'{w["titel"]}</td><td style="padding:6px 0">{balken_100(a, w["minuten"])}</td></tr>')
    return ('<table role="presentation" width="100%" cellspacing="0" cellpadding="0">'
            f'{"".join(zeilen)}</table>{legende(a)}')


def marke(f: str, groesse: int = 15) -> str:
    """Farbmarke als Zeichen: leere, nur hinterlegte Elemente werfen Gmail und
    Outlook weg, ein „■" in Schriftfarbe überlebt jedes Mailprogramm."""
    return (f'<span style="color:{f};font-size:{groesse}px;line-height:1;'
            f'font-family:Arial,sans-serif">&#9632;</span>')


def legende(a: dict) -> str:
    """Projekte mit ihren Farben, in der Reihenfolge der Jahresstunden."""
    namen = [p for p in a["projekte"] if p in a["farben"]]
    rest = [p for p in a["projekte"] if p not in a["farben"] and sichtbar(a["werte"]["jahr"]["minuten"][p])]
    zelle = f'style="padding:3px 18px 3px 0;font-size:13px;color:{INK2};white-space:nowrap"'
    zellen = "".join(
        f'<td {zelle}>{marke(farbe(a, p))}&nbsp;{html.escape(p)}</td>'
        + ("</tr><tr>" if i % 3 == 2 else "")
        for i, p in enumerate(namen))
    weitere = ""
    if rest:
        weitere = (f'<tr><td colspan="3" style="padding:3px 0;font-size:13px;color:{INK2}">'
                   f'{marke(FARBE_WEITERE)}&nbsp;{WEITERE}: {html.escape(", ".join(rest))}</td></tr>')
    return (f'<table role="presentation" cellspacing="0" cellpadding="0" style="margin-top:10px">'
            f'<tr>{zellen}</tr>{weitere}</table>')


def tabelle(a: dict) -> str:
    perioden = ("tag", "woche", "monat", "jahr")
    w = a["werte"]
    jahr_chats = w["jahr"]["chats"]
    reihen = [p for p in a["projekte"] if sichtbar(w["jahr"]["minuten"][p])]
    ohne_zeit = sorted((p for p in jahr_chats if p not in reihen), key=lambda p: (-jahr_chats[p], p))
    th = (f'style="padding:6px 6px;font-size:12px;font-weight:600;color:{INK2};text-align:right;'
          f'border-bottom:1px solid {LINIE};white-space:nowrap"')
    kopf = (f'<tr><th {th.replace("text-align:right", "text-align:left")}>Projekt</th>'
            + "".join(f'<th colspan="2" {th.replace("text-align:right", "text-align:center")}>{w[k]["titel"]}</th>'
                      for k in perioden) + f'<th {th}>Chats</th></tr>')
    unterkopf = (f'<tr><th {th}></th>'
                 + "".join(f'<th {th}>Std.</th><th {th}>%</th>' for _ in perioden)
                 + f'<th {th}>Jahr</th></tr>')
    td = (f'style="padding:5px 6px;font-size:13px;color:{INK};text-align:right;'
          f'border-bottom:1px solid {LINIE};font-variant-numeric:tabular-nums;white-space:nowrap"')
    leise = td.replace(f"color:{INK}", f"color:{MUTED}")
    zeilen = []
    for p in reihen:
        name = (f'<td style="padding:5px 6px;font-size:13px;color:{INK};border-bottom:1px solid {LINIE}">'
                f'{marke(farbe(a, p), 13)}&nbsp;{html.escape(p)}</td>')
        zellen = []
        for k in perioden:
            m = w[k]["minuten"].get(p, 0)
            da = sichtbar(m)
            zellen.append(f'<td {td if da else leise}>{h_text(m) if da else "–"}</td>'
                          f'<td {td if da else leise}>{proz(m, w[k]["gesamt"]) if da else "–"}</td>')
        zellen.append(f'<td {leise}>{jahr_chats.get(p) or "–"}</td>')
        zeilen.append(f"<tr>{name}{''.join(zellen)}</tr>")
    fett = td.replace("border-bottom", "font-weight:600;border-bottom")
    summe = (f'<tr><td style="padding:6px 6px;font-size:13px;font-weight:600;color:{INK}">Summe</td>'
             + "".join(f'<td {fett}>{h_text(w[k]["gesamt"])}</td>'
                       f'<td {td}>{"100 %" if w[k]["gesamt"] else "–"}</td>' for k in perioden)
             + f'<td {leise}>{sum(jahr_chats.values()) or "–"}</td></tr>')
    fuss = ""
    if ohne_zeit:
        fuss = (f'<p style="font-size:12px;color:{INK2};line-height:1.5;margin:10px 0 0">'
                '<b>Chats im Jahr ohne gemessene Zeit</b> (vor Messbeginn oder auf einem anderen Rechner): '
                + ", ".join(f"{html.escape(p)} ({jahr_chats[p]})" for p in ohne_zeit) + "</p>")
    return ('<div style="overflow-x:auto"><table cellspacing="0" cellpadding="0" '
            'style="border-collapse:collapse;width:100%">'
            f"{kopf}{unterkopf}{''.join(zeilen)}{summe}</table></div>{fuss}")


def verlauf_grafik(a: dict) -> str:
    """Gestapelte Tagessäulen der letzten 30 Tage."""
    hoehe = 120
    maxi = max((sum(p.values()) for _, p in a["verlauf"]), default=0)
    skala = max(60.0, maxi)
    spalten = []
    for d, projekte in a["verlauf"]:
        gesamt = sum(projekte.values())
        segmente = []
        for p, m in reversed(gruppiert(a, projekte)):
            px = max(1, round(m / skala * hoehe))
            f = farbe(a, p) if p != WEITERE else FARBE_WEITERE
            segmente.append(f'<tr><td title="{html.escape(p)}: {h_text(m)}" style="height:{px}px;'
                            f'background:{f};border-top:1px solid {FLAECHE};font-size:0;line-height:0;'
                            f'padding:0">&nbsp;</td></tr>')
        leer = hoehe - sum(max(1, round(m / skala * hoehe)) for _, m in gruppiert(a, projekte))
        wochenende = d.weekday() >= 5
        beschriftung = f"{d.day}." if d.day == 1 or d.weekday() == 0 or d == a["berichtstag"] else ""
        spalten.append(
            f'<td title="{datum_lang(d)}: {h_text(gesamt)}" style="vertical-align:bottom;padding:0 1px;'
            f'width:3.33%">'
            f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse">'
            f'<tr><td style="height:{max(leer, 0)}px;font-size:0;line-height:0;padding:0">&nbsp;</td></tr>'
            f'{"".join(segmente)}</table>'
            f'<div style="border-top:1px solid #c3c2b7;font-size:10px;color:{MUTED if not wochenende else LINIE};'
            f'text-align:center;padding-top:3px;height:12px">{beschriftung}</div></td>')
    return (f'<div style="font-size:12px;color:{MUTED};margin-bottom:4px">Höchster Tag: {h_text(maxi)}</div>'
            '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" '
            f'style="border-collapse:collapse;table-layout:fixed"><tr>{"".join(spalten)}</tr></table>'
            f'{legende(a)}')


def html_mail(a: dict) -> str:
    t = a["berichtstag"]
    seit = a["seit"]
    hinweis = ""
    if seit and seit > a["werte"]["jahr"]["von"]:
        hinweis = (f"Stunden sind ab {seit.day}. {MONATE[seit.month - 1]} {seit.year} gemessen; "
                   "davor gibt es keine Sitzungsprotokolle mehr. Die Chat-Zahlen kommen aus dem Vault "
                   "und reichen über das ganze Jahr. ")
    abschnitt = (f'<h2 style="font-size:15px;color:{INK};margin:26px 0 10px;padding-bottom:6px;'
                 f'border-bottom:2px solid {KOPF}">')
    return (
        f'<!doctype html><html lang="de"><head><meta charset="utf-8"></head>'
        f'<body style="margin:0;padding:0;background:#f9f9f7">'
        f'<div style="max-width:760px;margin:0 auto;padding:16px;font-family:system-ui,-apple-system,'
        f'BlinkMacSystemFont,\'Segoe UI\',sans-serif;color:{INK}">'
        f'<div style="background:{KOPF};color:#ffffff;padding:18px 22px;border-radius:8px 8px 0 0">'
        f'<div style="font-size:19px;font-weight:600">Claude-Code-Arbeitszeit</div>'
        f'<div style="font-size:13px;opacity:.8;margin-top:3px">{datum_lang(t)}</div></div>'
        f'<div style="background:{FLAECHE};padding:14px 22px 22px;border-radius:0 0 8px 8px;'
        f'border:1px solid {LINIE};border-top:0">'
        f'{kacheln(a)}'
        f'{abschnitt}Anteile je Zeitraum</h2>{anteile_grafik(a)}'
        f'{abschnitt}Letzte 30 Tage</h2>{verlauf_grafik(a)}'
        f'{abschnitt}Stunden, Anteile und Chats</h2>{tabelle(a)}'
        f'<p style="font-size:12px;color:{MUTED};line-height:1.5;margin-top:22px">'
        f'Woche ab Montag, Monat und Jahr jeweils bis einschließlich {t.day}.{t.month}. '
        f'Gezählt wird Zeit in Claude-Code-Sitzungen; Lücken über {PAUSE_MIN} Minuten gelten als Pause, '
        f'gleichzeitige Projekte teilen sich die Minute. Läufe der Paperclip-Agenten zählen nicht. '
        f'{hinweis}</p>'
        '</div></div></body></html>')


def text_mail(a: dict) -> str:
    w = a["werte"]
    zeilen = [f"Claude-Code-Arbeitszeit — {datum_lang(a['berichtstag'])}", ""]
    for k in ("tag", "woche", "monat", "jahr"):
        zeilen.append(f"{w[k]['titel']}: {h_text(w[k]['gesamt'])} ({sum(w[k]['chats'].values())} Chats)")
        for p, m in sorted(w[k]["minuten"].items(), key=lambda x: -x[1]):
            if not sichtbar(m):
                continue
            zeilen.append(f"  {p:<28} {h_text(m):>9}  {proz(m, w[k]['gesamt']):>5}")
        zeilen.append("")
    if a["seit"]:
        zeilen.append(f"Stunden gemessen ab {a['seit']:%d.%m.%Y}.")
    return "\n".join(zeilen)


def betreff(a: dict) -> str:
    w = a["werte"]
    return (f"Claude-Code-Zeit {a['berichtstag']:%d.%m.}: gestern {h_text(w['tag']['gesamt'])} · "
            f"Woche {h_text(w['woche']['gesamt'])} · Monat {h_text(w['monat']['gesamt'])} · "
            f"Jahr {h_text(w['jahr']['gesamt'])}")


# --- Versand ------------------------------------------------------------------
def mailhub_secret() -> str:
    with open(MAILHUB_ENV, encoding="utf-8") as fh:
        for zeile in fh:
            if zeile.startswith("MAILHUB_SECRET="):
                return zeile.split("=", 1)[1].strip().strip('"')
    raise RuntimeError("MAILHUB_SECRET fehlt in " + MAILHUB_ENV)


def senden(subject: str, text: str, html_body: str) -> int:
    payload = {"from": FROM_ADDR, "to": TO_ADDR, "subject": subject,
               "text": text, "html": html_body, "attachments": []}
    req = urllib.request.Request(
        MAILHUB_URL, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Mailhub-Secret": mailhub_secret()},
        method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        log(f"mailhub {r.status}: {r.read()[:200].decode('utf-8', 'replace')}")
        return r.status


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--datum", help="Berichtstag JJJJ-MM-TT (Standard: gestern)")
    ap.add_argument("--quelle", action="append", default=[],
                    help="zusätzlicher Protokoll-Ordner (Aufbau wie ~/.claude/projects)")
    ap.add_argument("--register", default=REGISTER)
    ap.add_argument("--nur-einlesen", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="nicht senden")
    ap.add_argument("--out", help="HTML zusätzlich in diese Datei schreiben")
    args = ap.parse_args(argv)

    db = oeffne_register(args.register)
    for wurzel in args.quelle + [PROTOKOLLE]:
        neu, weg = lies_ein(db, wurzel)
        log(f"{wurzel}: {neu} Sitzungen übernommen, {weg} übersprungen")
    if args.nur_einlesen:
        return 0

    berichtstag = (date.fromisoformat(args.datum) if args.datum
                   else datetime.now(BERLIN).date() - timedelta(days=1))
    a = auswerten(db, berichtstag, chats_im_vault())
    html_body = html_mail(a)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(html_body)
        log(f"HTML geschrieben: {args.out}")
    log(betreff(a))
    if args.dry_run:
        print(text_mail(a))
        return 0
    return 0 if senden(betreff(a), text_mail(a), html_body) == 200 else 1


if __name__ == "__main__":
    sys.exit(main())
