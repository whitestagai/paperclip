# tools/voice-echo-bot/kurs_ideen.py
"""Kursideen-Eingang fuer die WHITESTAG.ACADEMY (`/kurs <link> <notiz>`).

Walter schickt Jarvis einen Link (YouTube-Video oder Artikel) oder nur eine
Themenidee. Der Bot traegt sie als Zeile in `Workshops/_ideen-eingang.md` ein
und legt den Inhalt der Quelle als Material-Datei unter `Workshops/_ideen/`
ab. Die Kurs-Routine (CEO) nimmt die aelteste offene Idee, bevor sie selbst
ein Thema waehlt.

Warum das Material gleich mitgeholt wird: ein Agent kann kein Video ansehen.
Ruft er die YouTube-Seite ab, bekommt er Titel und Beschreibung, nicht den
Inhalt. Deshalb holt der Bot das Transkript — bevorzugt die Untertitelspur in
Originalsprache, sonst die Tonspur durch das lokale Whisper.

Nur EINE Untertitelspur anfragen: `--sub-langs "de.*"` zieht auch YouTubes
automatische Uebersetzungen (`de-en`, …) und laeuft in HTTP 429.
"""
import glob
import html
import json
import os
import re
import subprocess
import tempfile
import threading
import urllib.request
from datetime import datetime
from html.parser import HTMLParser

import transcribe

URL_RE = re.compile(r"https?://\S+")
YOUTUBE_RE = re.compile(r"^https?://(www\.|m\.|music\.)?(youtube\.com|youtu\.be)/", re.IGNORECASE)

PLATZHALTER_TITEL = "⏳"
MAX_AUDIO_SEKUNDEN = 3 * 3600
ABSATZ_WOERTER = 120
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

# Die Liste wird vom Bot-Hauptthread (neue Zeile) und vom Material-Thread
# (Titel nachtragen) beschrieben.
_LOCK = threading.Lock()

KOPF = """---
title: "WHITESTAG.ACADEMY — Kursideen-Eingang"
type: arbeitsliste
tags: [whitestag-academy, workshops]
zusammenfassung: Kursideen von Walter (per Jarvis `/kurs`). Die Kurs-Routine baut die aelteste offene Idee, bevor sie selbst ein Thema waehlt.
---

# Kursideen-Eingang — WHITESTAG.ACADEMY

Walter schickt Ideen per Telegram an Jarvis: `/kurs <Link> <Notiz>` oder nur
`/kurs <Thema>`. Jarvis traegt sie hier ein und legt den Inhalt der Quelle
(Video-Transkript bzw. Artikeltext) unter `Workshops/_ideen/` ab.

**Status:** `offen` → `in Arbeit (WHI-…)` → `gebaut (<slug>)`, oder
`doppelt (<slug>)` / `verworfen (<Grund>)`.

**Regel fuer die Kurs-Routine:** Die aelteste Zeile mit Status `offen` wird
als naechster Kurs gebaut. Das Material ist Anstoss und Faktenquelle, keine
Vorlage — nicht abschreiben, die `_KURS-SPEC.md` gilt unveraendert.

## Ideen

| ID | Eingang | Status | Quelle | Titel | Notiz | Material |
|---|---|---|---|---|---|---|
"""


def _zelle(text):
    """Text tabellensicher machen: keine Zeilenumbrueche, Pipes escapen."""
    return " ".join((text or "").split()).replace("|", "\\|")


def parse_befehl(rest):
    """`/kurs`-Argument -> (url|None, notiz). Der erste Link ist die Quelle."""
    rest = (rest or "").strip()
    m = URL_RE.search(rest)
    if not m:
        return None, " ".join(rest.split())
    url = m.group(0).rstrip(").,;>")
    notiz = (rest[:m.start()] + " " + rest[m.end():]).strip()
    return url, " ".join(notiz.split())


def ist_youtube(url):
    return bool(YOUTUBE_RE.match(url or ""))


def offene_ideen(datei):
    if not os.path.exists(datei):
        return 0
    with open(datei, "r", encoding="utf-8") as fh:
        return sum(1 for ln in fh if ln.startswith("| K-") and ln.split("|")[3].strip() == "offen")


def neue_idee(url, notiz, datei, material_dir, jetzt=None):
    """Haengt eine Zeile an die Ideenliste. Gibt die Idee als dict zurueck."""
    jetzt = jetzt or datetime.now()
    idee_id = "K-" + jetzt.strftime("%Y%m%d-%H%M%S")
    material = "_ideen/{}.md".format(idee_id) if url else "—"
    titel = PLATZHALTER_TITEL if url else _zelle(notiz)
    zeile = "| {} | {} | offen | {} | {} | {} | {} |\n".format(
        idee_id, jetzt.strftime("%Y-%m-%d"), url or "—", titel, _zelle(notiz) or "—", material)
    with _LOCK:
        os.makedirs(os.path.dirname(datei), exist_ok=True)
        if not os.path.exists(datei):
            with open(datei, "w", encoding="utf-8") as fh:
                fh.write(KOPF)
        with open(datei, "r", encoding="utf-8") as fh:
            inhalt = fh.read()
        with open(datei, "a", encoding="utf-8") as fh:
            if inhalt and not inhalt.endswith("\n"):
                fh.write("\n")
            fh.write(zeile)
    return {"id": idee_id, "url": url, "notiz": notiz, "datum": jetzt.strftime("%Y-%m-%d"),
            "datei": datei,
            "material_pfad": os.path.join(material_dir, idee_id + ".md") if url else None,
            "platz": offene_ideen(datei)}


def titel_eintragen(datei, idee_id, titel):
    """Ersetzt den Platzhalter-Titel in der Zeile der Idee."""
    with _LOCK:
        with open(datei, "r", encoding="utf-8") as fh:
            zeilen = fh.readlines()
        for i, ln in enumerate(zeilen):
            if ln.startswith("| {} |".format(idee_id)):
                zellen = ln.split(" | ")
                if len(zellen) > 4 and zellen[4] == PLATZHALTER_TITEL:
                    zellen[4] = _zelle(titel)
                    zeilen[i] = " | ".join(zellen)
        with open(datei, "w", encoding="utf-8") as fh:
            fh.writelines(zeilen)


# ---------- Textaufbereitung ----------

def vtt_zu_text(vtt):
    """WebVTT -> Fliesstext. YouTube-Auto-Untertitel wiederholen jede Zeile im
    Folge-Cue (rollende Anzeige); aufeinanderfolgende Dubletten fallen weg."""
    zeilen = []
    for ln in vtt.splitlines():
        s = ln.strip()
        if (not s or s == "WEBVTT" or "-->" in s or s.isdigit()
                or re.match(r"^(Kind|Language|NOTE|STYLE|Region)\b", s)):
            continue
        s = html.unescape(re.sub(r"<[^>]+>", "", s)).strip()
        if s and (not zeilen or zeilen[-1] != s):
            zeilen.append(s)
    return absaetze(" ".join(zeilen))


def absaetze(text, woerter=ABSATZ_WOERTER):
    w = text.split()
    return "\n\n".join(" ".join(w[i:i + woerter]) for i in range(0, len(w), woerter))


class _ArtikelParser(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "nav", "footer", "header", "aside",
            "form", "button", "iframe", "template"}
    BLOCK = {"p", "h1", "h2", "h3", "h4", "h5", "li", "blockquote", "pre", "br", "div",
             "section", "article", "tr", "figcaption"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.in_title = False
        self.titel = ""
        self.og_titel = ""
        self.teile = []

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag == "title":
            self.in_title = True
        elif tag == "meta":
            a = dict(attrs)
            if a.get("property") == "og:title" and a.get("content"):
                self.og_titel = a["content"].strip()
        if tag in self.BLOCK:
            self.teile.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        elif tag == "title":
            self.in_title = False
        if tag in self.BLOCK:
            self.teile.append("\n")

    def handle_data(self, data):
        if self.in_title:
            self.titel += data
        elif not self.skip:
            self.teile.append(data)


def html_zu_text(roh):
    p = _ArtikelParser()
    p.feed(roh)
    bloecke = []
    for b in "".join(p.teile).split("\n"):
        b = " ".join(b.split())
        # Menuepunkte, Buttons, Cookie-Reste: kurze Fetzen ohne Satzzeichen weg.
        if len(b.split()) >= 6 or (b and b[-1] in ".!?:"):
            bloecke.append(b)
    titel = (p.og_titel or " ".join(p.titel.split())).strip()
    return titel, "\n\n".join(bloecke)


# ---------- Quellen holen ----------

def _run(args, timeout):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=timeout)


def waehle_spur(info):
    """-> ("subs"|"auto", sprachschluessel) oder None. Originalsprache zuerst."""
    orig = (info.get("language") or "").split("-")[0]
    prefs = [l for l in (orig, "de", "en") if l]
    subs = info.get("subtitles") or {}
    autos = info.get("automatic_captions") or {}
    for l in prefs:
        for k in subs:
            if k == l or k.startswith(l + "-"):
                return "subs", k
    for l in prefs:
        for k in (l + "-orig", l):
            if k in autos:
                return "auto", k
    return None


def youtube_holen(url, whisper_model, run=_run, transcriber=None):
    transcriber = transcriber or transcribe.transcribe
    # launchd-PATH kennt Homebrew nicht zuverlaessig; transcribe sucht dort mit.
    yt = transcribe._resolve_binary("yt-dlp")
    info = json.loads(run([yt, "-J", "--skip-download", "--no-playlist", url], 120).stdout)
    erg = {"art": "youtube", "titel": info.get("title") or url,
           "kanal": info.get("channel") or info.get("uploader") or "",
           "dauer_min": round((info.get("duration") or 0) / 60),
           "beschreibung": (info.get("description") or "")[:4000]}
    tmp = tempfile.mkdtemp(prefix="kursidee-")
    spur = waehle_spur(info)
    if spur:
        art, lang = spur
        try:
            run([yt, "--skip-download", "--no-playlist",
                 "--write-subs" if art == "subs" else "--write-auto-subs",
                 "--sub-langs", lang, "--sub-format", "vtt",
                 "-o", os.path.join(tmp, "sub.%(ext)s"), url], 180)
            vtts = glob.glob(os.path.join(tmp, "*.vtt"))
            if vtts:
                with open(vtts[0], "r", encoding="utf-8") as fh:
                    text = vtt_zu_text(fh.read())
                if text:
                    erg["text"] = text
                    erg["transkript"] = "untertitel ({}, {})".format(
                        "manuell" if art == "subs" else "automatisch", lang)
                    return erg
        except (subprocess.SubprocessError, OSError):
            pass  # weiter mit Whisper
    if (info.get("duration") or 0) > MAX_AUDIO_SEKUNDEN:
        raise RuntimeError("keine Untertitel und Video laenger als 3 Stunden")
    run([yt, "-f", "bestaudio", "--no-playlist", "-o", os.path.join(tmp, "audio.%(ext)s"), url], 900)
    audios = glob.glob(os.path.join(tmp, "audio.*"))
    if not audios:
        raise RuntimeError("Tonspur nicht herunterladbar")
    erg["text"] = absaetze(transcriber(audios[0], whisper_model, workdir=tmp,
                                       language="auto", timeout=3600))
    erg["transkript"] = "whisper (lokal)"
    return erg


def artikel_holen(url, opener=urllib.request.urlopen):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                               "Accept-Language": "de,en;q=0.8"})
    with opener(req, timeout=30) as resp:
        roh = resp.read(4 * 1024 * 1024)
        charset = resp.headers.get_content_charset() or "utf-8"
    titel, text = html_zu_text(roh.decode(charset, errors="replace"))
    erg = {"art": "artikel", "titel": titel or url, "text": text, "transkript": "artikeltext"}
    if len(text.split()) < 200:
        erg["hinweis"] = ("Nur wenig Text gefunden — die Seite ist evtl. hinter einer "
                          "Paywall oder laedt per JavaScript nach.")
    return erg


def material_schreiben(idee, erg):
    def fm(s):
        return '"' + str(s).replace('"', "'") + '"'
    kopf = ["---", "title: " + fm(erg.get("titel", "")), "quelle: " + idee["url"],
            "art: " + erg.get("art", "unbekannt"), "idee_id: " + idee["id"],
            "eingang: " + idee["datum"], "transkript: " + fm(erg.get("transkript", "keins"))]
    if erg.get("kanal"):
        kopf.append("kanal: " + fm(erg["kanal"]))
    if erg.get("dauer_min"):
        kopf.append("dauer_min: {}".format(erg["dauer_min"]))
    kopf.append("---")
    teile = ["\n".join(kopf), "# " + (erg.get("titel") or idee["url"]),
             "**Walters Notiz:** " + (idee.get("notiz") or "—"),
             "> Material fuer die Kurs-Routine. Anstoss und Faktenquelle, **keine Vorlage**: "
             "nicht abschreiben, Aussagen zu KI-Werkzeugen gegen `_KI-TOOL-STAND.md` pruefen, "
             "Aufbau nach `_KURS-SPEC.md`."]
    if erg.get("fehler"):
        teile.append("## Abruf fehlgeschlagen\n\n" + erg["fehler"] +
                     "\n\nDer Autor recherchiert das Thema anhand von Link und Notiz selbst.")
    if erg.get("hinweis"):
        teile.append("> ⚠️ " + erg["hinweis"])
    if erg.get("beschreibung"):
        teile.append("## Beschreibung (von der Quelle)\n\n" + erg["beschreibung"].strip())
    if erg.get("text"):
        teile.append("## " + ("Transkript" if erg.get("art") == "youtube" else "Text") +
                     "\n\n" + erg["text"].strip())
    os.makedirs(os.path.dirname(idee["material_pfad"]), exist_ok=True)
    with open(idee["material_pfad"], "w", encoding="utf-8") as fh:
        fh.write("\n\n".join(teile) + "\n")


def material_holen(idee, whisper_model, youtube=youtube_holen, artikel=artikel_holen):
    """Holt den Inhalt, schreibt die Material-Datei, traegt den Titel nach.
    Wirft bei Fehler weiter, nachdem eine Fehler-Material-Datei geschrieben ist."""
    try:
        erg = youtube(idee["url"], whisper_model) if ist_youtube(idee["url"]) \
            else artikel(idee["url"])
    except Exception as exc:  # noqa: BLE001
        erg = {"art": "youtube" if ist_youtube(idee["url"]) else "artikel",
               "titel": idee.get("notiz") or idee["url"], "fehler": str(exc)[:500]}
        material_schreiben(idee, erg)
        titel_eintragen(idee["datei"], idee["id"], erg["titel"])
        raise
    material_schreiben(idee, erg)
    titel_eintragen(idee["datei"], idee["id"], erg["titel"])
    erg["woerter"] = len((erg.get("text") or "").split())
    return erg
