"""Indexstatus der Sitemap-Seiten über die URL-Prüfung der Search Console.

Die Suchstatistik (gsc.py) zeigt nur, was Google ausspielt, nicht, warum eine
Seite fehlt. Gründe wie „Durch noindex ausgeschlossen“ stehen nur in der
URL-Prüfung. Ein Aufruf dauert rund 6 s, daher parallel; das Kontingent liegt
bei 600 Aufrufen je Minute und 2000 je Tag und Property.
"""
from concurrent.futures import ThreadPoolExecutor

INSPECT_URL = "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"
_FELDER = ("verdict", "coverageState", "indexingState", "robotsTxtState", "pageFetchState")


def inspect_url(session, prop, url):
    r = session.post(INSPECT_URL, json={"inspectionUrl": url, "siteUrl": prop,
                                        "languageCode": "de"}, timeout=60)
    r.raise_for_status()
    res = r.json().get("inspectionResult", {}).get("indexStatusResult", {})
    return {"url": url, **{k: res.get(k) for k in _FELDER}}


def inspect_urls(session, prop, urls, workers=4):
    def _eine(url):
        # Ein zweiter Versuch: Google antwortet vereinzelt mit 500.
        for versuch in (1, 2):
            try:
                return inspect_url(session, prop, url)
            except Exception as e:  # noqa: BLE001 — eine Adresse darf die Site nicht kippen
                if versuch == 2:
                    return {"url": url, "error": str(e)}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(_eine, urls))


def gesperrt(r):
    """Von uns verursacht: noindex, robots.txt oder Abruf scheitert."""
    return (str(r.get("indexingState") or "").startswith("BLOCKED")
            or r.get("robotsTxtState") == "DISALLOWED")


def auswerten(results, prev_results=None):
    """Zählt indexiert/nicht indexiert und findet Rückfälle gegenüber der Vorwoche."""
    vorher_pass = {r["url"] for r in (prev_results or []) if r.get("verdict") == "PASS"}
    ok = [r for r in results if "error" not in r]
    return {
        "geprueft": len(ok),
        "fehler": [r for r in results if "error" in r],
        "indexiert": sum(1 for r in ok if r.get("verdict") == "PASS"),
        "gesperrt": [r for r in ok if gesperrt(r)],
        "nicht_indexiert": [r for r in ok if r.get("verdict") != "PASS" and not gesperrt(r)],
        "rueckfaelle": [r for r in ok if r["url"] in vorher_pass and r.get("verdict") != "PASS"],
    }


def alarm(auswertung):
    return bool(auswertung["gesperrt"] or auswertung["rueckfaelle"])


def render_markdown(per_site, max_urls=5):
    lines = ["", "## Indexstatus (URL-Prüfung, Sitemap-Seiten)", ""]
    for s in per_site:
        name = s["name"]
        if s.get("error"):
            lines.append(f"**{name}** — {s['error']}")
            continue
        a = s["auswertung"]
        amp = "🔴" if alarm(a) else ("🟡" if a["nicht_indexiert"] or a["fehler"] else "🟢")
        lines.append(f"**{name}** {amp} — {a['indexiert']}/{a['geprueft']} indexiert")
        for r in a["gesperrt"]:
            lines.append(f"  - 🔴 gesperrt: {r['url']} ({r.get('indexingState')}, "
                         f"robots.txt {r.get('robotsTxtState')})")
        for r in a["rueckfaelle"]:
            lines.append(f"  - 🔴 nicht mehr indexiert: {r['url']} ({r.get('coverageState')})")
        gruppen = {}
        for r in a["nicht_indexiert"]:
            gruppen.setdefault(r.get("coverageState") or "unbekannt", []).append(r["url"])
        for grund, urls in sorted(gruppen.items()):
            mehr = f" … (+{len(urls) - max_urls})" if len(urls) > max_urls else ""
            lines.append(f"  - {grund} ({len(urls)}): " + ", ".join(urls[:max_urls]) + mehr)
        if a["fehler"]:
            lines.append(f"  - ⚠️ {len(a['fehler'])} Prüfungen fehlgeschlagen, "
                         f"z. B. {a['fehler'][0]['error'][:120]}")
    lines.append("")
    return "\n".join(lines)
