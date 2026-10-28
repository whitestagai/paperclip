# tools/voice-echo-bot/paperclip_status.py
"""Stand von Paperclip-Aufgaben für Jarvis (nur lesen).

`abfragen(was, tenant)` liefert ein kompaktes dict, das jarvis_brain dem
Modell als Kontext gibt — wie beim Vault-Lookup. `was` ist:
  eine Nummer („10652", „WHI 10652")  -> diese Aufgabe + letzte Kommentare
  „offen"                              -> Anzahl je Status + zuletzt bewegte
  „erledigt" / „heute"                 -> heute erledigte Aufgaben
  alles andere                         -> Volltextsuche

„Heute erledigt" kommt aus dem Aktivitätsprotokoll, nicht aus der Issue-
Liste: die sortiert zuerst nach Priorität, bei über 7.000 erledigten
Aufgaben fände man die von heute dort nicht zuverlässig. Das Protokoll ist
nach Zeit sortiert; 500 Einträge reichten am 28.10.2026 gut einen Tag zurück.

Hinweis: läuft im Satelliten-venv unter Python 3.9 — keine `X | None`-Syntax.
"""
import datetime
import re
import urllib.error
import urllib.parse

import paperclip_client

OFFEN = "todo,in_progress,blocked,in_review"
STATUS_DE = {"backlog": "zurückgestellt", "todo": "offen", "in_progress": "in Arbeit",
             "blocked": "blockiert", "in_review": "in Prüfung", "done": "erledigt",
             "cancelled": "abgebrochen"}
ZULETZT = 5
ERLEDIGT_MAX = 8
KOMMENTAR_ZEICHEN = 300

_NUMMER = re.compile(r"^\s*(?:[A-Za-z]+[\s-]*)?(\d+)\s*$")


_EINER = ("null", "eins", "zwei", "drei", "vier", "fünf", "sechs", "sieben", "acht",
          "neun", "zehn", "elf", "zwölf", "dreizehn", "vierzehn", "fünfzehn",
          "sechzehn", "siebzehn", "achtzehn", "neunzehn")
_ZEHNER = ("", "", "zwanzig", "dreißig", "vierzig", "fünfzig", "sechzig", "siebzig",
           "achtzig", "neunzig")


def _unter_hundert(n):
    if n < 20:
        return _EINER[n]
    zehner, einer = divmod(n, 10)
    if not einer:
        return _ZEHNER[zehner]
    return "{}und{}".format("ein" if einer == 1 else _EINER[einer], _ZEHNER[zehner])


def zahl_als_wort(n):
    """Anzahl als deutsches Wort (0-999), darüber Ziffern.

    Für die Sprachausgabe: das 12b sollte Ziffern selbst ausschreiben, machte
    aber aus 25 „fünfzigen" (Live-Befund 28.10.2026). „eine" statt „eins",
    weil es hier immer um „eine Aufgabe" geht.
    """
    if n == 1:
        return "eine"
    if n < 100:
        return _unter_hundert(n)
    if n < 1000:
        hunderter, rest = divmod(n, 100)
        kopf = ("ein" if hunderter == 1 else _EINER[hunderter]) + "hundert"
        return kopf + (_unter_hundert(rest) if rest else "")
    return str(n)


class PaperclipStatusError(Exception):
    """Paperclip nicht erreichbar oder Antwort unbrauchbar."""


def _liste(data, schluessel):
    if isinstance(data, list):
        return data
    return data.get(schluessel, data.get("data", []))


def _zeit(iso):
    return datetime.datetime.fromisoformat(iso.replace("Z", "+00:00"))


def _kurz(issue, namen, mit_status=True):
    eintrag = {"nummer": issue.get("identifier"), "titel": issue.get("title")}
    if mit_status:
        eintrag["status"] = STATUS_DE.get(issue.get("status"), issue.get("status"))
    eintrag["zustaendiger_agent"] = namen.get(issue.get("assigneeAgentId"))
    return eintrag


def abfragen(was, tenant, token=None, get_json=None, jetzt=None):
    get = get_json or (lambda path: paperclip_client._get_json(token, path))
    jetzt = jetzt or datetime.datetime.now().astimezone()
    cid = tenant["company_id"]
    was = (was or "").strip()
    try:
        namen = {a["id"]: a.get("name") for a in
                 _liste(get("/companies/{}/agents".format(cid)), "agents")}
        m = _NUMMER.match(was)
        if m:
            return _aufgabe("{}-{}".format(tenant.get("issue_prefix", "WHI"), m.group(1)),
                            get, namen)
        wort = was.lower()
        if wort.startswith("offen"):
            return _offen(get, cid, namen)
        if wort.startswith(("erledigt", "heute", "fertig")):
            return _erledigt_heute(get, cid, namen, jetzt)
        return _suche(was, get, cid, namen)
    except (urllib.error.URLError, OSError, ValueError, KeyError) as exc:
        raise PaperclipStatusError("Paperclip-Abfrage fehlgeschlagen: {}".format(exc)) from exc


def _aufgabe(nummer, get, namen):
    try:
        issue = get("/issues/{}".format(nummer))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {"art": "aufgabe", "fehler": "Aufgabe {} nicht gefunden".format(nummer)}
        raise
    kommentare = sorted(_liste(get("/issues/{}/comments".format(nummer)), "comments"),
                        key=lambda k: k.get("createdAt", ""))[-2:]
    eintrag = _kurz(issue, namen)
    eintrag["zuletzt_geaendert"] = issue.get("updatedAt")
    eintrag["letzte_kommentare"] = [
        {"von": namen.get(k.get("authorAgentId")) or ("Walter" if k.get("authorUserId") else "System"),
         "text": (k.get("body") or "")[:KOMMENTAR_ZEICHEN]} for k in kommentare]
    return {"art": "aufgabe", "aufgabe": eintrag}


def _offen(get, cid, namen):
    issues = _liste(get("/companies/{}/issues?status={}&limit=200".format(cid, OFFEN)), "issues")
    anzahl = {}
    for i in issues:
        de = STATUS_DE.get(i.get("status"), i.get("status"))
        anzahl[de] = anzahl.get(de, 0) + 1
    juengste = sorted(issues, key=lambda i: i.get("updatedAt", ""), reverse=True)[:ZULETZT]
    anzahl = {status: zahl_als_wort(n) for status, n in anzahl.items()}
    return {"art": "offen", "anzahl": anzahl,
            "zuletzt_bewegt": [_kurz(i, namen) for i in juengste]}


def _erledigt_heute(get, cid, namen, jetzt):
    eintraege = _liste(get("/companies/{}/activity?entityType=issue&limit=500".format(cid)),
                       "activity")
    heute = jetzt.date()
    nummern = []
    for e in eintraege:
        details = e.get("details") or {}
        if (e.get("action") == "issue.updated" and details.get("status") == "done"
                and details.get("identifier")
                and _zeit(e["createdAt"]).astimezone(jetzt.tzinfo).date() == heute
                and details["identifier"] not in nummern):
            nummern.append(details["identifier"])
    aufgaben = [_kurz(get("/issues/{}".format(n)), namen, mit_status=False)
                for n in nummern[:ERLEDIGT_MAX]]
    return {"art": "erledigt_heute", "anzahl": zahl_als_wort(len(nummern)),
            "aufgaben": aufgaben}


def _suche(begriff, get, cid, namen):
    issues = _liste(get("/companies/{}/issues?q={}&limit=5".format(
        cid, urllib.parse.quote(begriff))), "issues")
    return {"art": "suche", "begriff": begriff, "treffer": [_kurz(i, namen) for i in issues]}
