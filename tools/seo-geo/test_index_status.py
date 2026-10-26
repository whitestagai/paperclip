import index_status
from index_status import auswerten, alarm, render_markdown, inspect_urls


def _r(url, verdict="PASS", cov="Gesendet und indexiert", idx="INDEXING_ALLOWED", rob="ALLOWED"):
    return {"url": url, "verdict": verdict, "coverageState": cov,
            "indexingState": idx, "robotsTxtState": rob, "pageFetchState": "SUCCESSFUL"}


def test_noindex_auf_sitemap_seite_ist_gesperrt_und_alarmiert():
    a = auswerten([_r("https://a.de/"), _r("https://a.de/x/", "FAIL",
                   "Durch noindex-Tag ausgeschlossen", "BLOCKED_BY_META_TAG")])
    assert a["indexiert"] == 1
    assert [r["url"] for r in a["gesperrt"]] == ["https://a.de/x/"]
    assert alarm(a) is True


def test_robots_txt_sperre_ist_gesperrt():
    a = auswerten([_r("https://a.de/y/", "FAIL", "Durch robots.txt blockiert", rob="DISALLOWED")])
    assert len(a["gesperrt"]) == 1


def test_noch_nicht_indexiert_ist_kein_alarm():
    # Neue Seiten stehen oft wochenlang auf „Gefunden – zurzeit nicht indexiert“.
    a = auswerten([_r("https://a.de/neu/", "NEUTRAL", "Gefunden – zurzeit nicht indexiert")])
    assert len(a["nicht_indexiert"]) == 1
    assert alarm(a) is False


def test_rueckfall_gegen_vorwoche_alarmiert():
    prev = [_r("https://a.de/p/")]
    a = auswerten([_r("https://a.de/p/", "NEUTRAL", "Gecrawlt – zurzeit nicht indexiert")], prev)
    assert [r["url"] for r in a["rueckfaelle"]] == ["https://a.de/p/"]
    assert alarm(a) is True


def test_einzelfehler_kippt_die_site_nicht():
    class S:
        def post(self, url, json, timeout):
            raise RuntimeError("Quota")
    res = inspect_urls(S(), "sc-domain:a.de", ["https://a.de/"], workers=1)
    assert res == [{"url": "https://a.de/", "error": "Quota"}]
    a = auswerten(res)
    assert a["geprueft"] == 0 and len(a["fehler"]) == 1 and alarm(a) is False


def test_render_nennt_gesperrte_und_gruppiert_den_rest():
    a = auswerten([_r("https://a.de/x/", "FAIL", "Durch noindex-Tag ausgeschlossen", "BLOCKED_BY_META_TAG"),
                   _r("https://a.de/n/", "NEUTRAL", "Gefunden – zurzeit nicht indexiert")])
    md = render_markdown([{"name": "a.de", "auswertung": a},
                          {"name": "b.de", "error": "nicht in GSC"}])
    assert "🔴 gesperrt: https://a.de/x/" in md
    assert "Gefunden – zurzeit nicht indexiert (1): https://a.de/n/" in md
    assert "**b.de** — nicht in GSC" in md
