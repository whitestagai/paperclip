import datetime
import urllib.error

import pytest

import paperclip_status as ps

TENANT = {"company_id": "c-1", "issue_prefix": "WHI"}
JETZT = datetime.datetime(2026, 10, 28, 16, 0).astimezone()
AGENTEN = [{"id": "a-ceo", "name": "CEO"}, {"id": "a-cmo", "name": "CMO"}]


def _fake(antworten):
    """get_json-Double: Pfad-Präfix -> Antwort (oder Exception)."""
    gefragt = []
    def get(path):
        gefragt.append(path)
        for praefix, antwort in antworten.items():
            if path.startswith(praefix):
                if isinstance(antwort, Exception):
                    raise antwort
                return antwort
        raise AssertionError("unerwarteter Pfad " + path)
    get.gefragt = gefragt
    return get


def test_nummer_liefert_eine_aufgabe_mit_letzten_kommentaren():
    get = _fake({
        "/companies/c-1/agents": AGENTEN,
        "/issues/WHI-10652/comments": [
            {"body": "erster", "createdAt": "2026-10-28T14:00:00Z", "authorAgentId": "a-ceo"},
            {"body": "zweiter", "createdAt": "2026-10-28T14:05:00Z", "authorAgentId": "a-ceo"},
            {"body": "dritter", "createdAt": "2026-10-28T14:10:00Z", "authorUserId": "u"}],
        "/issues/WHI-10652": {"id": "i-1", "identifier": "WHI-10652", "title": "Wie spät ist es?",
                              "status": "done", "assigneeAgentId": "a-ceo",
                              "updatedAt": "2026-10-28T14:55:20Z"},
    })
    d = ps.abfragen("10652", TENANT, get_json=get, jetzt=JETZT)
    assert d["art"] == "aufgabe"
    a = d["aufgabe"]
    assert (a["nummer"], a["titel"], a["status"], a["zustaendiger_agent"]) == \
        ("WHI-10652", "Wie spät ist es?", "erledigt", "CEO")
    assert [k["text"] for k in a["letzte_kommentare"]] == ["zweiter", "dritter"]
    assert a["letzte_kommentare"][1]["von"] == "Walter"


def test_nummer_mit_praefix_und_leerzeichen():
    get = _fake({"/companies/c-1/agents": [],
                 "/issues/WHI-77/comments": [],
                 "/issues/WHI-77": {"id": "i", "identifier": "WHI-77", "title": "t", "status": "todo"}})
    assert ps.abfragen("WHI 77", TENANT, get_json=get, jetzt=JETZT)["aufgabe"]["nummer"] == "WHI-77"


def test_unbekannte_nummer_meldet_nicht_gefunden():
    nf = urllib.error.HTTPError("u", 404, "nf", {}, None)
    get = _fake({"/companies/c-1/agents": [], "/issues/WHI-1": nf})
    d = ps.abfragen("1", TENANT, get_json=get, jetzt=JETZT)
    assert "nicht gefunden" in d["fehler"]


def test_offen_zaehlt_nach_status_und_nennt_die_juengsten():
    issues = [
        {"identifier": "WHI-1", "title": "alt", "status": "blocked", "updatedAt": "2026-10-01T00:00:00Z"},
        {"identifier": "WHI-2", "title": "neu", "status": "todo", "updatedAt": "2026-10-28T10:00:00Z",
         "assigneeAgentId": "a-cmo"},
        {"identifier": "WHI-3", "title": "mitte", "status": "blocked", "updatedAt": "2026-10-20T00:00:00Z"},
    ]
    get = _fake({"/companies/c-1/agents": AGENTEN, "/companies/c-1/issues?status=": issues})
    d = ps.abfragen("offen", TENANT, get_json=get, jetzt=JETZT)
    assert d["art"] == "offen"
    assert d["anzahl"] == {"offen": "eine", "blockiert": "zwei"}
    assert [x["nummer"] for x in d["zuletzt_bewegt"]] == ["WHI-2", "WHI-3", "WHI-1"]
    assert d["zuletzt_bewegt"][0]["zustaendiger_agent"] == "CMO"


def test_erledigt_heute_aus_dem_aktivitaetsprotokoll():
    akt = [
        {"action": "issue.updated", "createdAt": "2026-10-28T14:00:00Z",
         "details": {"status": "done", "identifier": "WHI-10"}},
        {"action": "issue.updated", "createdAt": "2026-10-28T13:00:00Z",
         "details": {"status": "done", "identifier": "WHI-10"}},          # doppelt
        {"action": "issue.updated", "createdAt": "2026-10-28T12:00:00Z",
         "details": {"status": "in_progress", "identifier": "WHI-11"}},   # nicht erledigt
        {"action": "issue.updated", "createdAt": "2026-10-27T12:00:00Z",
         "details": {"status": "done", "identifier": "WHI-9"}},           # gestern
        {"action": "issue.comment_added", "createdAt": "2026-10-28T15:00:00Z", "details": {}},
    ]
    get = _fake({"/companies/c-1/agents": AGENTEN,
                 "/companies/c-1/activity": akt,
                 "/issues/WHI-10": {"identifier": "WHI-10", "title": "Rechnung", "status": "done",
                                    "assigneeAgentId": "a-ceo"}})
    d = ps.abfragen("erledigt", TENANT, get_json=get, jetzt=JETZT)
    assert d["art"] == "erledigt_heute"
    assert d["anzahl"] == "eine"
    assert d["aufgaben"] == [{"nummer": "WHI-10", "titel": "Rechnung", "zustaendiger_agent": "CEO"}]


def test_sonst_wird_gesucht():
    get = _fake({"/companies/c-1/agents": [],
                 "/companies/c-1/issues?q=Stadtmuseum": [
                     {"identifier": "WHI-5", "title": "Angebot Stadtmuseum", "status": "in_review"}]})
    d = ps.abfragen("Stadtmuseum", TENANT, get_json=get, jetzt=JETZT)
    assert d["art"] == "suche"
    assert d["treffer"][0] == {"nummer": "WHI-5", "titel": "Angebot Stadtmuseum",
                               "status": "in Prüfung", "zustaendiger_agent": None}


@pytest.mark.parametrize("n,wort", [
    (0, "null"), (1, "eine"), (7, "sieben"), (16, "sechzehn"), (21, "einundzwanzig"),
    (25, "fünfundzwanzig"), (30, "dreißig"), (62, "zweiundsechzig"), (100, "einhundert"),
    (101, "einhunderteins"), (258, "zweihundertachtundfünfzig"), (1234, "1234")])
def test_zahlen_kommen_als_woerter(n, wort):
    # Live-Befund 28.10.: das 12b machte aus 25 „fünfzigen" — die Wörter
    # liefern wir deshalb fertig mit.
    assert ps.zahl_als_wort(n) == wort


def test_zaehlungen_stehen_als_woerter_in_den_daten():
    get = _fake({"/companies/c-1/agents": [], "/companies/c-1/issues?status=": [
        {"identifier": "WHI-1", "title": "t", "status": "blocked"}] * 62})
    assert ps.abfragen("offen", TENANT, get_json=get, jetzt=JETZT)["anzahl"] == \
        {"blockiert": "zweiundsechzig"}


def test_paperclip_nicht_erreichbar_wirft_eigenen_fehler():
    get = _fake({"/companies/c-1/agents": urllib.error.URLError("weg")})
    with pytest.raises(ps.PaperclipStatusError):
        ps.abfragen("offen", TENANT, get_json=get, jetzt=JETZT)
