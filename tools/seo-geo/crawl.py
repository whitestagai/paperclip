import json
from dataclasses import dataclass, field
from bs4 import BeautifulSoup

@dataclass
class PageSignals:
    url: str
    title: str | None = None
    meta_description: str | None = None
    og_title: str | None = None
    og_description: str | None = None
    canonical: str | None = None
    h1_count: int = 0
    images_total: int = 0
    images_missing_alt: int = 0
    images_without_alt: list[str] = field(default_factory=list)
    jsonld_types: list[str] = field(default_factory=list)
    robots: str | None = None

def _meta(soup, **attrs):
    tag = soup.find("meta", attrs=attrs)
    return tag.get("content").strip() if tag and tag.get("content") else None

def _fehlt_alt(img, leeres_alt_ist_schmuck: bool) -> bool:
    alt = img.get("alt")
    if alt is None:
        return True
    # alt="" markiert ein Schmuckbild — auf statischen Sites bewusst gesetzt.
    # WordPress schreibt alt="" aber auch, wenn niemand einen Text eingetragen
    # hat; dort bleibt es ein Befund. Nur Leerzeichen sind nie Absicht.
    if alt == "":
        return not leeres_alt_ist_schmuck
    return not alt.strip()

def parse_page(url: str, html: str, leeres_alt_ist_schmuck: bool = False) -> PageSignals:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text().strip() if soup.title else None
    canonical_tag = soup.find("link", rel="canonical")
    imgs = soup.find_all("img")
    # Nicht nur zählen — die konkreten Quellen merken, sonst kann niemand sie
    # einer WordPress-Media-ID zuordnen.
    ohne = [i for i in imgs if _fehlt_alt(i, leeres_alt_ist_schmuck)]
    no_alt = [i.get("src", "").strip() for i in ohne if i.get("src", "").strip()]
    types = []
    for s in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(s.get_text())
        except (ValueError, TypeError):
            continue
        for node in (data if isinstance(data, list) else [data]):
            if not isinstance(node, dict):
                continue
            # Yoast & Co. verpacken die Typen in @graph statt in einem Top-Level-@type.
            graph = node.get("@graph")
            inner = graph if isinstance(graph, list) else [node]
            for n in inner:
                if not isinstance(n, dict):
                    continue
                t = n.get("@type")
                if isinstance(t, str):
                    types.append(t)
                elif isinstance(t, list):
                    types.extend(x for x in t if isinstance(x, str))
    return PageSignals(
        url=url,
        title=title,
        meta_description=_meta(soup, name="description"),
        og_title=_meta(soup, property="og:title"),
        og_description=_meta(soup, property="og:description"),
        canonical=canonical_tag.get("href").strip() if canonical_tag and canonical_tag.get("href") else None,
        h1_count=len(soup.find_all("h1")),
        images_total=len(imgs),
        images_missing_alt=len(ohne),
        images_without_alt=no_alt,
        jsonld_types=types,
        robots=_meta(soup, name="robots"),
    )
