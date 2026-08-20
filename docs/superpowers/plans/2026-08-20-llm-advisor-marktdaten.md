# LLM-Advisor Marktdaten — Implementierungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Der Advisor bekommt Modell-Marktdaten aus dem Sammelskript statt aus einer Recherche, die sein Agent nicht ausführen kann.

**Architecture:** Ein neues Modul `advisor/market.py` holt zwei externe Quellen — Artificial Analysis (Free API) für die Qualitätsachse, den lokalen Websuche-Dienst `:7789` für die Frage, was neu ist. `collect_ist_zustand.py` schreibt beides als `model_market` in `state/ist-zustand.json`. Der Agent zitiert nur noch daraus; `verify_market_claims` prüft jede genannte Zahl gegen das JSON.

**Tech Stack:** Python 3.9 (`.venv/bin/python`), Standardbibliothek (`urllib.request`, `json`, `re`), pytest. Keine neuen Abhängigkeiten.

**Spec:** `docs/superpowers/specs/2026-08-20-llm-advisor-marktdaten-design.md`

## Global Constraints

- **Interpreter ist Python 3.9.6** (`~/.paperclip/scripts/llm-advisor/.venv/bin/python`) — das ist der Interpreter der Routine, nicht das System-Python. Keine `X | None`-Annotationen zur Laufzeit, kein `match`, kein `dict | dict`.
- **Keine neuen Abhängigkeiten.** `requirements.txt` führt nur `psycopg[binary]>=3.1` und `pytest>=8.0`. HTTP über `urllib.request` wie in `advisor/apply.py`.
- **Arbeitsverzeichnis ist `~/.paperclip/scripts/llm-advisor/`** — host-lokales Git-Repo **ohne Remote**. Committen ja, pushen nicht möglich.
- **`state/` ist gitignored.** Cache- und Listendateien dort sind nicht committbar; die Ablehnungsliste bekommt deshalb eine versionierte Vorlage.
- **Kommentare und Docstrings auf Deutsch**, im Stil der bestehenden Module: sie nennen den Vorfall, der die Regel erzwungen hat.
- **Attributionspflicht:** Jede Ausgabe, die AA-Zahlen trägt, nennt `"Artificial Analysis"` als Quelle mit Abrufdatum.
- **Fail-closed:** Jeder Ausfall einer externen Quelle führt zu `status: "nicht_verfuegbar"` mit Grund im Klartext — nie zu stillem Weglassen.
- **`collect_ist_zustand.py` darf an Marktdaten nie scheitern.** Die Telemetrie ist der wichtigere Teil und muss auch ohne Netz entstehen.
- **Baseline:** 111 Tests grün. Nach jedem Task erneut prüfen.

---

### Task 1: Modellschlüssel auf AA-Slugs abbilden

Reine Funktion, kein Netz. Der riskanteste Teil des Ganzen: eine falsche Zuordnung erzeugt eine erfundene Zahl mit Autoritätsanschein.

**Files:**
- Create: `advisor/market.py`
- Test: `tests/test_market.py`

**Interfaces:**
- Consumes: nichts
- Produces: `normalisiere(lm_key) -> str`, `match_slug(lm_key, slugs, overrides=None) -> str oder None`, Konstante `OVERRIDES` (dict)

- [ ] **Step 1: Write the failing test**

```python
"""Zuordnung LM-Studio-Schluessel auf Artificial-Analysis-Slugs.

Eine falsche Zuordnung ist gefaehrlicher als eine fehlende: qwen3-coder-30b
versehentlich auf qwen3-coder-480b-a35b gemappt ergaebe eine erfundene Zahl
mit Autoritaetsanschein -- genau der Fehlertyp aus der Mail vom 07.08.
Deshalb: exakter Treffer, Override oder None. Kein Fuzzy-Matching.
"""
from advisor.market import OVERRIDES, match_slug, normalisiere

# Die echten Slugs, gezogen am 20.08. aus dem AA-Katalog.
SLUGS = {
    "gemma-4-31b", "gemma-4-12b", "qwen3-6-35b-a3b", "qwen3-6-27b",
    "qwen3-8-27b", "qwen3-8-2-4t-a95b", "qwen3-coder-next",
    "qwen3-coder-30b-a3b-instruct", "qwen3-coder-480b-a35b-instruct",
    "mistral-small-3-2", "kimi-k3",
}


def test_normalisierung_raeumt_die_lmstudio_suffixe_weg():
    assert normalisiere("gemma-4-31b-it-mlx") == "gemma-4-31b"
    assert normalisiere("qwen3.6-35b-a3b-mlx") == "qwen3-6-35b-a3b"
    assert normalisiere("google/gemma-4-12b-qat") == "gemma-4-12b"
    assert normalisiere("qwen/qwen3-coder-next") == "qwen3-coder-next"
    assert normalisiere("qwen3.8-27b-mtplx") == "qwen3-8-27b"


def test_die_zehn_schluessel_die_ohne_override_treffen():
    treffer = {
        "gemma-4-31b-it-mlx": "gemma-4-31b",
        "google/gemma-4-12b": "gemma-4-12b",
        "google/gemma-4-12b-qat": "gemma-4-12b",
        "google/gemma-4-31b-qat": "gemma-4-31b",
        "qwen3.6-35b-a3b-mlx": "qwen3-6-35b-a3b",
        "qwen3.8-27b": "qwen3-8-27b",
        "qwen3.8-27b-mlx": "qwen3-8-27b",
        "qwen/qwen3-coder-next": "qwen3-coder-next",
        "kimi-k3": "kimi-k3",
        "qwen3.8-2.4t-a95b": "qwen3-8-2-4t-a95b",
    }
    for lm_key, erwartet in treffer.items():
        assert match_slug(lm_key, SLUGS) == erwartet, lm_key


def test_die_drei_ausnahmen_kommen_aus_der_override_tabelle():
    assert match_slug("qwen/qwen3-coder-30b", SLUGS) == "qwen3-coder-30b-a3b-instruct"
    assert match_slug("mistral-small-3.2-24b-instruct-2506", SLUGS) == "mistral-small-3-2"
    assert match_slug("openbiollm-llama3-8b.gguf", SLUGS) is None


def test_kein_fuzzy_treffer_bei_unbekanntem_schluessel():
    # "qwen3-coder-7b" gibt es bei AA nicht. Ein Nachbar waere schlimmer als nichts.
    assert match_slug("qwen/qwen3-coder-7b", SLUGS) is None
    assert match_slug("voellig-erfundenes-modell", SLUGS) is None


def test_override_auf_none_bedeutet_bewusst_nicht_gelistet():
    assert "openbiollm-llama3-8b.gguf" in OVERRIDES
    assert OVERRIDES["openbiollm-llama3-8b.gguf"] is None


def test_override_zeigt_nie_auf_einen_slug_den_es_nicht_gibt():
    # Schutz gegen Tippfehler in der Tabelle: ein Override ins Leere waere
    # dasselbe wie kein Treffer, nur schwerer zu finden.
    for lm_key, slug in OVERRIDES.items():
        if slug is not None:
            assert slug in SLUGS, f"{lm_key} zeigt auf unbekannten Slug {slug}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/.paperclip/scripts/llm-advisor && .venv/bin/python -m pytest tests/test_market.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'advisor.market'`

- [ ] **Step 3: Write minimal implementation**

```python
"""Modellmarkt: externe Kennzahlen und Neuigkeiten, gesammelt VOR dem Agentenlauf.

Schritt 3 des Routine-Briefs hiess "Suche per WebSearch" und war seit dem
Traegerwechsel am 31.07. nicht ausfuehrbar: der Agent laeuft auf
lmstudio_local und hat kein WebSearch-Werkzeug. Die Mail vom 07.08. nannte
daraufhin Repo-Groessen, die um 2,5 GB danebenlagen. Wer eine Rechercheaufgabe
ohne Rechercheweg bekommt, fuellt die Luecke aus dem Gedaechtnis.

Dieses Modul holt die Daten deterministisch, damit der Agent sie zitieren
statt formulieren kann -- dieselbe Konstruktion wie `evidence.py` fuer die
Telemetriezahlen.
"""
from __future__ import annotations

import re

# LM-Studio-Schluessel, deren Normalform nicht auf den AA-Slug faellt.
# `None` heisst: bei AA bewusst nicht gelistet, kein Fehler.
OVERRIDES = {
    "qwen/qwen3-coder-30b": "qwen3-coder-30b-a3b-instruct",
    "mistral-small-3.2-24b-instruct-2506": "mistral-small-3-2",
    "openbiollm-llama3-8b.gguf": None,
}

# Suffixe, die LM Studio an denselben Modellnamen haengt: Quantisierung,
# Laufzeitformat, Instruction-Tuning-Marker.
_SUFFIXE = ("-mlx", "-mtplx", "-qat", ".gguf", "@q4_k_m", "-it")


def normalisiere(lm_key):
    """LM-Studio-Schluessel auf die AA-Schreibweise bringen.

    `google/gemma-4-31b-qat` -> `gemma-4-31b`, `qwen3.6-35b-a3b-mlx` ->
    `qwen3-6-35b-a3b`. Punkte werden zu Bindestrichen, weil AA in den Slugs
    keine Punkte fuehrt (`Qwen3.6` -> `qwen3-6`).
    """
    s = lm_key.split("/")[-1].lower()
    aenderung = True
    while aenderung:            # `-it-mlx` traegt zwei Suffixe hintereinander
        aenderung = False
        for suf in _SUFFIXE:
            if s.endswith(suf):
                s = s[: -len(suf)]
                aenderung = True
    return s.replace(".", "-")


def match_slug(lm_key, slugs, overrides=None):
    """Den AA-Slug zu einem LM-Studio-Schluessel, oder None.

    Kein Fuzzy-Matching: exakter Treffer, Override oder nichts. Ein
    naeherungsweise passender Nachbar (qwen3-coder-30b -> das 480B-Modell)
    liefert eine Zahl, die falsch ist und richtig aussieht.
    """
    tabelle = OVERRIDES if overrides is None else overrides
    if lm_key in tabelle:
        return tabelle[lm_key]
    kandidat = normalisiere(lm_key)
    return kandidat if kandidat in slugs else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_market.py -v`
Expected: 6 passed

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: 117 passed (111 Baseline + 6 neu)

- [ ] **Step 6: Commit**

```bash
git add advisor/market.py tests/test_market.py
git commit -m "feat(market): LM-Studio-Schluessel auf AA-Slugs abbilden"
```

---

### Task 2: Artificial Analysis abrufen (Free API)

**Files:**
- Modify: `advisor/market.py`
- Test: `tests/test_market.py`

**Interfaces:**
- Consumes: nichts aus Task 1
- Produces: `lade_key(pfad=None) -> str oder None`, `fetch_aa(key, oeffner=None, timeout=20, cache_pfad=None) -> dict` mit den Schlüsseln `status`, `aa_stand`, `quelle`, `modelle_roh` (Liste), `grund` (nur bei Ausfall), sowie `kennzahlen(record) -> dict`. Die Testklasse `_FakeAntwort` und der Helfer `_seite` entstehen hier und werden von Task 3 mitbenutzt.

**Hinweis für den Umsetzenden:** Welche Felder der Free-Tier wirklich liefert, ist zum Zeitpunkt des Plans **unbekannt** — die Dokumentation nennt nur „composite indices, pricing, performance". Deshalb liest `kennzahlen()` defensiv mehrere Kandidatenschlüssel und liefert `None`, wenn keiner greift. Niemals raten.

- [ ] **Step 1: Write the failing test**

```python
import json

from advisor.market import fetch_aa, kennzahlen, lade_key


class _FakeAntwort:
    """Minimaler Ersatz fuer das Objekt aus urllib.request.urlopen."""

    def __init__(self, rumpf):
        self._rumpf = json.dumps(rumpf).encode("utf-8")

    def read(self):
        return self._rumpf

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _seite(models, has_more=False, page=1):
    return {"tier": "free", "pagination": {"page": page, "has_more": has_more},
            "data": models}


def test_pagination_wird_zu_ende_gelesen():
    seiten = [_seite([{"slug": "a"}], has_more=True, page=1),
              _seite([{"slug": "b"}], has_more=False, page=2)]
    aufrufe = []

    def oeffner(url, key, timeout):
        aufrufe.append(url)
        return _FakeAntwort(seiten[len(aufrufe) - 1])

    ergebnis = fetch_aa("schluessel", oeffner=oeffner)
    assert ergebnis["status"] == "ok"
    assert [m["slug"] for m in ergebnis["modelle_roh"]] == ["a", "b"]
    assert len(aufrufe) == 2


def test_ohne_key_ist_der_status_nicht_verfuegbar():
    ergebnis = fetch_aa(None)
    assert ergebnis["status"] == "nicht_verfuegbar"
    assert "kein API-Key" in ergebnis["grund"]


def test_http_fehler_wird_zum_grund_nicht_zur_exception():
    def oeffner(url, key, timeout):
        raise OSError("HTTP Error 401: Unauthorized")

    ergebnis = fetch_aa("falscher-key", oeffner=oeffner)
    assert ergebnis["status"] == "nicht_verfuegbar"
    assert "401" in ergebnis["grund"]


def test_endlosschleife_ausgeschlossen_wenn_has_more_immer_true_bleibt():
    # Ein Server-Fehler darf nicht zu unbegrenzt vielen Requests fuehren --
    # das Free-Kontingent liegt bei 100 pro 24 Stunden.
    def oeffner(url, key, timeout):
        return _FakeAntwort(_seite([{"slug": "x"}], has_more=True))

    ergebnis = fetch_aa("schluessel", oeffner=oeffner)
    assert ergebnis["status"] == "ok"
    assert len(ergebnis["modelle_roh"]) == 20      # MAX_SEITEN, je Seite 1 Modell


def test_rohantwort_wird_zur_nachvollziehbarkeit_geschrieben(tmp_path):
    ziel = tmp_path / "aa-cache.json"

    def oeffner(url, key, timeout):
        return _FakeAntwort(_seite([{"slug": "a"}]))

    fetch_aa("schluessel", oeffner=oeffner, cache_pfad=ziel)
    abgelegt = json.loads(ziel.read_text())
    assert abgelegt["aa_stand"]
    assert [m["slug"] for m in abgelegt["modelle_roh"]] == ["a"]


def test_der_cache_wird_nie_als_ersatz_gelesen(tmp_path):
    # Ein Lese-Fallback wuerde alte Zahlen als aktuelle ausgeben -- genau der
    # Fehlertyp, den diese Umbaustufe beseitigen soll. Der Cache dient der
    # Nachvollziehbarkeit ("was stand beim Lauf da?"), nicht der Verfuegbarkeit.
    ziel = tmp_path / "aa-cache.json"
    ziel.write_text(json.dumps({"status": "ok", "aa_stand": "2026-01-01",
                                "modelle_roh": [{"slug": "veraltet"}]}))

    def oeffner(url, key, timeout):
        raise OSError("HTTP Error 503: Service Unavailable")

    ergebnis = fetch_aa("schluessel", oeffner=oeffner, cache_pfad=ziel)
    assert ergebnis["status"] == "nicht_verfuegbar"
    assert ergebnis["modelle_roh"] == []


def test_kennzahlen_liest_die_indizes_defensiv():
    record = {"evaluations": {"artificial_analysis_intelligence_index": 29.69,
                              "artificial_analysis_coding_index": 43.43,
                              "artificial_analysis_agentic_index": 14.38}}
    assert kennzahlen(record) == {"intelligence_index": 29.69,
                                  "coding_index": 43.43,
                                  "agentic_index": 14.38}


def test_kennzahlen_liefert_none_statt_zu_raten():
    # Der Free-Tier fuehrt die Indizes moeglicherweise unter anderen Namen.
    # Ein fehlender Wert ist `None` -- nie ein geschaetzter oder abgeleiteter.
    assert kennzahlen({"evaluations": {}}) == {"intelligence_index": None,
                                               "coding_index": None,
                                               "agentic_index": None}
    assert kennzahlen({})["intelligence_index"] is None


def test_lade_key_liefert_none_wenn_die_datei_fehlt(tmp_path):
    assert lade_key(tmp_path / "gibtsnicht.env") is None


def test_lade_key_liest_die_zeile_aus_der_env_datei(tmp_path):
    p = tmp_path / "aa.env"
    p.write_text("# Kommentar\nARTIFICIALANALYSIS_API_KEY=abc123\n")
    assert lade_key(p) == "abc123"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_market.py -v`
Expected: FAIL mit `ImportError: cannot import name 'fetch_aa'`

- [ ] **Step 3: Write minimal implementation**

Ergänze in `advisor/market.py`:

```python
import datetime as _dt
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

AA_URL = os.environ.get(
    "AA_API_URL", "https://artificialanalysis.ai/api/v2/language/models/free")
AA_KEY_PFAD = Path(os.path.expanduser(
    "~/.paperclip/instances/default/secrets/artificialanalysis.env"))
QUELLE = "Artificial Analysis (Free API)"

# Deckel gegen ein has_more, das nie false wird. Das Free-Kontingent liegt bei
# 100 Requests pro 24 Stunden -- eine Schleife wuerde es in Sekunden leeren.
MAX_SEITEN = 20

# Der Free-Tier nennt die Indizes moeglicherweise anders als der Pro-Tier.
# Reihenfolge = Vorrang; greift keiner, bleibt der Wert None.
_INDEX_FELDER = {
    "intelligence_index": ("artificial_analysis_intelligence_index",
                           "intelligence_index", "intelligenceIndex"),
    "coding_index": ("artificial_analysis_coding_index",
                     "coding_index", "codingIndex"),
    "agentic_index": ("artificial_analysis_agentic_index",
                      "agentic_index", "agenticIndex"),
}


def lade_key(pfad=None):
    """Den API-Key aus der env-Datei, oder None.

    Gleiche Bauform wie das Mailhub-Secret: der Schluessel steht nie im Repo.
    """
    p = Path(pfad) if pfad is not None else AA_KEY_PFAD
    try:
        text = p.read_text()
    except OSError:
        return None
    for zeile in text.splitlines():
        zeile = zeile.strip()
        if zeile.startswith("ARTIFICIALANALYSIS_API_KEY="):
            wert = zeile.split("=", 1)[1].strip()
            return wert or None
    return None


def kennzahlen(record):
    """Die drei Indizes aus einem AA-Record, fehlende als None.

    Defensiv, weil der Feldname im Free-Tier nicht dokumentiert ist. Geraten
    wird nichts: ein fehlender Index ist None und wird im Bericht als
    "nicht verfuegbar" ausgewiesen.
    """
    evals = record.get("evaluations") or {}
    aus = {}
    for ziel, kandidaten in _INDEX_FELDER.items():
        wert = None
        for k in kandidaten:
            if evals.get(k) is not None:
                wert = evals[k]
                break
            if record.get(k) is not None:
                wert = record[k]
                break
        aus[ziel] = wert
    return aus


def _oeffne(url, key, timeout):
    r = urllib.request.Request(url, headers={"x-api-key": key,
                                             "Accept": "application/json"})
    return urllib.request.urlopen(r, timeout=timeout)


def fetch_aa(key, oeffner=None, timeout=20, cache_pfad=None):
    """Alle Modelle des Free-Endpunkts, paginiert.

    Kein Ausfall wirft: ein fehlender Key, ein 401 oder ein Netzfehler wird
    zu `status: "nicht_verfuegbar"` mit Grund. Der Advisor meldet die Luecke,
    statt ohne Marktdaten weiterzuraten.

    `cache_pfad` legt die Rohantwort ab -- zur **Nachvollziehbarkeit**, damit
    sich spaeter rekonstruieren laesst, was beim Lauf dastand. Der Cache wird
    bewusst **nie gelesen**: ein Lese-Fallback wuerde alte Zahlen als aktuelle
    ausgeben und damit genau den Fehlertyp erzeugen, den dieser Umbau
    beseitigen soll.
    """
    heute = _dt.date.today().isoformat()
    kopf = {"quelle": QUELLE, "aa_stand": heute}
    if not key:
        return dict(kopf, status="nicht_verfuegbar",
                    grund="kein API-Key hinterlegt (%s)" % AA_KEY_PFAD,
                    modelle_roh=[])
    oeffner = oeffner or _oeffne
    gesammelt = []
    try:
        for seite in range(1, MAX_SEITEN + 1):
            trenner = "&" if "?" in AA_URL else "?"
            with oeffner("%s%spage=%d" % (AA_URL, trenner, seite), key,
                         timeout) as antwort:
                doc = json.loads(antwort.read().decode("utf-8"))
            gesammelt.extend(doc.get("data") or [])
            if not (doc.get("pagination") or {}).get("has_more"):
                break
    except (OSError, urllib.error.URLError, ValueError) as e:
        return dict(kopf, status="nicht_verfuegbar",
                    grund="%s: %s" % (type(e).__name__, e), modelle_roh=[])
    ergebnis = dict(kopf, status="ok", modelle_roh=gesammelt)
    if cache_pfad is not None:
        try:
            Path(cache_pfad).parent.mkdir(parents=True, exist_ok=True)
            Path(cache_pfad).write_text(
                json.dumps(ergebnis, ensure_ascii=False, indent=2))
        except OSError:
            pass        # Ein nicht schreibbarer Cache ist kein Grund, den Lauf zu kippen.
    return ergebnis
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_market.py -v`
Expected: 16 passed

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: 127 passed

- [ ] **Step 6: Commit**

```bash
git add advisor/market.py tests/test_market.py
git commit -m "feat(market): Artificial-Analysis-Abruf ueber die Free API"
```

---

### Task 3: Websuche-Dienst anbinden

**Files:**
- Modify: `advisor/market.py`
- Test: `tests/test_market.py`

**Interfaces:**
- Consumes: die Testhelfer `_FakeAntwort` und `_seite` aus Task 2 (gleiche Datei)
- Produces: `fetch_web(frage, oeffner=None, quellen=3, zeichen=6000, deadline=30) -> dict` mit `status`, `frage`, `abgerufen_am`, `quellen` (Liste), `hinweis`, `grund` (nur bei Ausfall)

- [ ] **Step 1: Write the failing test**

```python
from advisor.market import fetch_web


def test_antwort_des_diensts_wird_unveraendert_durchgereicht():
    antwort = {"frage": "neue MLX-Modelle", "abgerufen_am": "2026-08-20",
               "quellen": [{"url": "https://lmstudio.ai/models",
                            "domain": "lmstudio.ai", "text": "Model Catalog"}],
               "hinweis": None}

    def oeffner(url, rumpf, timeout):
        return _FakeAntwort(antwort)

    ergebnis = fetch_web("neue MLX-Modelle", oeffner=oeffner)
    assert ergebnis["status"] == "ok"
    assert ergebnis["quellen"] == antwort["quellen"]
    assert ergebnis["hinweis"] is None


def test_der_hinweis_des_diensts_bleibt_erhalten():
    # "Nur eine Quelle lieferte verwertbaren Text" ist eine ehrliche
    # Selbstauskunft des Diensts -- sie gehoert in den Bericht, nicht in den Muell.
    antwort = {"frage": "x", "abgerufen_am": "2026-08-20", "quellen": [],
               "hinweis": "Keine Quelle lieferte verwertbaren Text."}

    def oeffner(url, rumpf, timeout):
        return _FakeAntwort(antwort)

    assert fetch_web("x", oeffner=oeffner)["hinweis"].startswith("Keine Quelle")


def test_dienst_nicht_erreichbar_ergibt_nicht_verfuegbar():
    def oeffner(url, rumpf, timeout):
        raise OSError("Connection refused")

    ergebnis = fetch_web("x", oeffner=oeffner)
    assert ergebnis["status"] == "nicht_verfuegbar"
    assert "Connection refused" in ergebnis["grund"]
    assert ergebnis["quellen"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_market.py -v`
Expected: FAIL mit `ImportError: cannot import name 'fetch_web'`

- [ ] **Step 3: Write minimal implementation**

```python
WEBSUCHE_URL = os.environ.get("WEBSUCHE_URL", "http://127.0.0.1:7789/suche")


def _oeffne_websuche(url, rumpf, timeout):
    daten = json.dumps(rumpf).encode("utf-8")
    r = urllib.request.Request(
        url, data=daten, method="POST",
        headers={"Content-Type": "application/json"})
    return urllib.request.urlopen(r, timeout=timeout)


def fetch_web(frage, oeffner=None, quellen=3, zeichen=6000, deadline=30):
    """Den lokalen Websuche-Dienst fragen (siehe tools/websuche/).

    Laeuft ausserhalb des Agenten-Wallclock, kostet also keine Iteration.
    Gemessen am 20.08.: 2,0 s fuer drei Quellen. Der `hinweis` des Diensts
    ("nur eine Quelle lieferte Text") wird durchgereicht -- er ist eine
    ehrliche Selbstauskunft ueber die Belastbarkeit des Ergebnisses.
    """
    heute = _dt.date.today().isoformat()
    oeffner = oeffner or _oeffne_websuche
    rumpf = {"frage": frage, "quellen": quellen, "zeichen": zeichen,
             "deadline": deadline}
    try:
        with oeffner(WEBSUCHE_URL, rumpf, deadline + 10) as antwort:
            doc = json.loads(antwort.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, ValueError) as e:
        return {"status": "nicht_verfuegbar", "frage": frage,
                "abgerufen_am": heute, "quellen": [], "hinweis": None,
                "grund": "%s: %s" % (type(e).__name__, e)}
    return {"status": "ok", "frage": frage,
            "abgerufen_am": doc.get("abgerufen_am") or heute,
            "quellen": doc.get("quellen") or [],
            "hinweis": doc.get("hinweis")}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_market.py -v`
Expected: 19 passed

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: 130 passed

- [ ] **Step 6: Commit**

```bash
git add advisor/market.py tests/test_market.py
git commit -m "feat(market): lokalen Websuche-Dienst anbinden"
```

---

### Task 4: Bericht komponieren, Reasoning-Variante wählen, Ablehnungen markieren

**Files:**
- Modify: `advisor/market.py`
- Create: `state-vorlagen/abgelehnte-modelle.json`
- Test: `tests/test_market.py`

**Interfaces:**
- Consumes: `match_slug` (Task 1), `fetch_aa`/`kennzahlen` (Task 2), `fetch_web` (Task 3)
- Produces: `waehle_variante(records) -> dict` (Slug → Record, Reasoning bevorzugt), `lade_ablehnungen(pfad) -> dict`, `market_report(lm_keys, aa, web, ablehnungen=None) -> dict`

**Hinweis:** `state/` ist gitignored. Die Ablehnungsliste bekommt deshalb eine versionierte Vorlage unter `state-vorlagen/`, die beim ersten Lauf nach `state/` kopiert wird.

- [ ] **Step 1: Write the failing test**

```python
from advisor.market import lade_ablehnungen, market_report, waehle_variante


def _rec(slug, name, ii):
    return {"slug": slug, "name": name, "release_date": "2026-04-02",
            "evaluations": {"artificial_analysis_intelligence_index": ii}}


def test_reasoning_variante_wird_bevorzugt():
    # gemma-4-31b: 29,69 als Reasoning gegen 22,3 als Non-Reasoning. Wer die
    # falsche Zeile zieht, vergleicht Aepfel mit Birnen.
    records = [_rec("gemma-4-31b-non-reasoning", "Gemma 4 31B (Non-reasoning)", 22.3),
               _rec("gemma-4-31b", "Gemma 4 31B (Reasoning)", 29.69)]
    gewaehlt = waehle_variante(records)
    assert gewaehlt["gemma-4-31b"]["evaluations"][
        "artificial_analysis_intelligence_index"] == 29.69
    assert "gemma-4-31b-non-reasoning" in gewaehlt


def test_bericht_ordnet_kennzahlen_und_weist_die_variante_aus():
    aa = {"status": "ok", "aa_stand": "2026-08-20", "quelle": "Artificial Analysis (Free API)",
          "modelle_roh": [_rec("gemma-4-31b", "Gemma 4 31B (Reasoning)", 29.69)]}
    web = {"status": "ok", "frage": "x", "abgerufen_am": "2026-08-20",
           "quellen": [], "hinweis": None}
    bericht = market_report(["gemma-4-31b-it-mlx"], aa, web)
    eintrag = bericht["modelle"]["gemma-4-31b-it-mlx"]
    assert eintrag["aa_slug"] == "gemma-4-31b"
    assert eintrag["intelligence_index"] == 29.69
    assert eintrag["variante"] == "Reasoning"
    assert bericht["status"] == "ok"
    assert bericht["quelle"] == "Artificial Analysis (Free API)"


def test_nicht_zugeordnete_schluessel_stehen_in_nicht_gelistet():
    aa = {"status": "ok", "aa_stand": "2026-08-20", "quelle": "q", "modelle_roh": []}
    web = {"status": "ok", "frage": "x", "abgerufen_am": "2026-08-20",
           "quellen": [], "hinweis": None}
    bericht = market_report(["openbiollm-llama3-8b.gguf"], aa, web)
    assert bericht["nicht_gelistet"] == ["openbiollm-llama3-8b.gguf"]
    assert "openbiollm-llama3-8b.gguf" not in bericht["modelle"]


def test_abgelehntes_modell_wird_markiert():
    # qwen3.8-27b steht bei AA auf Intelligence Index 52,0 -- fast das Doppelte
    # von gemma-4-31b. Ohne Gedaechtnis empfiehlt der Advisor ihn jede Woche neu.
    aa = {"status": "ok", "aa_stand": "2026-08-20", "quelle": "q",
          "modelle_roh": [_rec("qwen3-8-27b", "Qwen3.8 27B (Reasoning)", 52.0)]}
    web = {"status": "ok", "frage": "x", "abgerufen_am": "2026-08-20",
           "quellen": [], "hinweis": None}
    ablehnungen = {"qwen3.8-27b": {"grund": "MLX laesst reasoning_effort=none nicht zu",
                                   "abgelehnt_am": "2026-08-17"}}
    bericht = market_report(["qwen3.8-27b"], aa, web, ablehnungen=ablehnungen)
    eintrag = bericht["modelle"]["qwen3.8-27b"]
    assert eintrag["abgelehnt"] is True
    assert "reasoning_effort" in eintrag["ablehnungsgrund"]


def test_ausfall_einer_quelle_macht_den_gesamtstatus_nicht_verfuegbar():
    aa = {"status": "nicht_verfuegbar", "aa_stand": "2026-08-20", "quelle": "q",
          "grund": "kein API-Key hinterlegt", "modelle_roh": []}
    web = {"status": "ok", "frage": "x", "abgerufen_am": "2026-08-20",
           "quellen": [], "hinweis": None}
    bericht = market_report(["gemma-4-31b-it-mlx"], aa, web)
    assert bericht["status"] == "nicht_verfuegbar"
    assert "kein API-Key" in bericht["grund"]


def test_ablehnungsliste_wird_aus_der_datei_gelesen(tmp_path):
    p = tmp_path / "abgelehnt.json"
    p.write_text(json.dumps([{"modell": "qwen3.8-27b", "grund": "g",
                              "abgelehnt_am": "2026-08-17"}]))
    geladen = lade_ablehnungen(p)
    assert geladen["qwen3.8-27b"]["grund"] == "g"


def test_fehlende_ablehnungsliste_ist_kein_fehler(tmp_path):
    assert lade_ablehnungen(tmp_path / "gibtsnicht.json") == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_market.py -v`
Expected: FAIL mit `ImportError: cannot import name 'market_report'`

- [ ] **Step 3: Write minimal implementation**

```python
def waehle_variante(records):
    """Slug -> Record. Bei Reasoning/Non-Reasoning-Paaren gewinnt Reasoning.

    AA fuehrt beide getrennt und der Abstand ist erheblich (gemma-4-31b:
    29,69 gegen 22,3). Ein Vergleich ueber die Variantengrenze hinweg ist
    wertlos, deshalb wird die gewaehlte Variante spaeter mit ausgewiesen.
    """
    aus = {}
    for r in records:
        slug = r.get("slug")
        if slug:
            aus[slug] = r
    return aus


def _variante(record):
    name = record.get("name") or ""
    if "(Non-reasoning)" in name:
        return "Non-Reasoning"
    if "(Reasoning)" in name:
        return "Reasoning"
    return "unbekannt"


def lade_ablehnungen(pfad):
    """Die Ablehnungsliste als dict modell -> eintrag. Fehlt sie, ist sie leer."""
    try:
        roh = json.loads(Path(pfad).read_text())
    except (OSError, ValueError):
        return {}
    return {e["modell"]: e for e in roh if e.get("modell")}


def market_report(lm_keys, aa, web, ablehnungen=None):
    """Das `model_market`-Fragment fuer ist-zustand.json.

    Faellt eine der beiden Quellen aus, ist der Gesamtstatus
    `nicht_verfuegbar` samt Grund. Der Brief verbietet in diesem Fall jede
    Modellempfehlung -- ein Agent ohne Marktdaten, der trotzdem etwas sagen
    soll, erfindet (Mail vom 07.08.).
    """
    ablehnungen = ablehnungen or {}
    nach_slug = waehle_variante(aa.get("modelle_roh") or [])
    slugs = set(nach_slug)

    modelle, nicht_gelistet = {}, []
    for lm_key in lm_keys:
        slug = match_slug(lm_key, slugs)
        if slug is None or slug not in nach_slug:
            nicht_gelistet.append(lm_key)
            continue
        record = nach_slug[slug]
        eintrag = {"aa_slug": slug, "variante": _variante(record),
                   "release_date": record.get("release_date")}
        eintrag.update(kennzahlen(record))
        if lm_key in ablehnungen:
            eintrag["abgelehnt"] = True
            eintrag["ablehnungsgrund"] = ablehnungen[lm_key].get("grund")
            eintrag["abgelehnt_am"] = ablehnungen[lm_key].get("abgelehnt_am")
        modelle[lm_key] = eintrag

    gruende = [q.get("grund") for q in (aa, web)
               if q.get("status") != "ok" and q.get("grund")]
    return {
        "status": "ok" if not gruende else "nicht_verfuegbar",
        "grund": "; ".join(gruende) if gruende else None,
        "aa_stand": aa.get("aa_stand"),
        "quelle": aa.get("quelle"),
        "modelle": modelle,
        "nicht_gelistet": nicht_gelistet,
        "suche": web,
    }
```

- [ ] **Step 4: Create the rejection list template**

Datei `state-vorlagen/abgelehnte-modelle.json`:

```json
[
  {
    "modell": "qwen3.8-27b",
    "abgelehnt_am": "2026-08-17",
    "grund": "MLX-Variante laesst reasoning_effort=none nicht zu; der Denkmodus laeuft davon (28,3 s / 2.236 Token). Nur auf der RTX mit abgeschaltetem Denken brauchbar.",
    "quelle": "project_qwen38_bewertung_und_adapter_reasoning_luecke"
  }
]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_market.py -v`
Expected: 26 passed

- [ ] **Step 6: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: 137 passed

- [ ] **Step 7: Commit**

```bash
git add advisor/market.py tests/test_market.py state-vorlagen/abgelehnte-modelle.json
git commit -m "feat(market): Bericht komponieren, Reasoning waehlen, Ablehnungen markieren"
```

---

### Task 5: `verify_market_claims` — der Zahlenwächter

**Files:**
- Modify: `advisor/market.py`
- Test: `tests/test_market.py`

**Interfaces:**
- Consumes: `market_report`-Ausgabe (Task 4)
- Produces: `verify_market_claims(text, model_market) -> list` von `{"modell", "feld", "claimed", "actual"}`

- [ ] **Step 1: Write the failing test**

```python
from advisor.market import verify_market_claims

_MARKT = {"modelle": {
    "gemma-4-31b-it-mlx": {"aa_slug": "gemma-4-31b", "intelligence_index": 29.69,
                           "coding_index": 43.43, "agentic_index": 14.38},
    "qwen3.6-35b-a3b-mlx": {"aa_slug": "qwen3-6-35b-a3b", "intelligence_index": 32.13,
                            "coding_index": 41.88, "agentic_index": 21.62}}}


def test_korrekte_zahl_wird_durchgelassen():
    text = "gemma-4-31b-it-mlx liegt bei Intelligence Index 29.69."
    assert verify_market_claims(text, _MARKT) == []


def test_erfundene_zahl_wird_beanstandet():
    # Der Fehlertyp aus der Mail vom 07.08.: die Richtung stimmt, die Zahl nicht.
    text = "gemma-4-31b-it-mlx liegt bei Intelligence Index 41.2."
    bad = verify_market_claims(text, _MARKT)
    assert len(bad) == 1
    assert bad[0]["modell"] == "gemma-4-31b-it-mlx"
    assert bad[0]["claimed"] == 41.2
    assert bad[0]["actual"] == 29.69


def test_gerundete_zahl_gilt_als_korrekt():
    # "29,7" statt "29.69" ist zulaessig -- der Bericht soll lesbar bleiben.
    assert verify_market_claims("gemma-4-31b-it-mlx: Intelligence Index 29.7",
                                _MARKT) == []


def test_coding_index_wird_getrennt_geprueft():
    text = "qwen3.6-35b-a3b-mlx: Coding Index 41.88, Intelligence Index 32.13"
    assert verify_market_claims(text, _MARKT) == []
    schlecht = verify_market_claims(
        "qwen3.6-35b-a3b-mlx: Coding Index 55.0", _MARKT)
    assert schlecht[0]["feld"] == "coding_index"


def test_zahlen_ohne_modellbezug_werden_nicht_angefasst():
    # Fehlerzahlen und GB-Angaben sind Sache von evidence.verify_error_counts.
    assert verify_market_claims("14x adapter_failed, 35,15 GB belegt", _MARKT) == []


def test_modell_ohne_marktdaten_kann_nichts_verletzen():
    assert verify_market_claims("openbiollm: Intelligence Index 5.0", _MARKT) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_market.py -v`
Expected: FAIL mit `ImportError: cannot import name 'verify_market_claims'`

- [ ] **Step 3: Write minimal implementation**

```python
# "Intelligence Index 29.69", "Coding Index: 43,4", "Agentic Index = 14.38"
_FELD_NAMEN = {"intelligence": "intelligence_index",
               "coding": "coding_index",
               "agentic": "agentic_index"}
_CLAIM = re.compile(
    r"\b(intelligence|coding|agentic)[\s-]*index\b\s*[:=]?\s*(\d+(?:[.,]\d+)?)",
    re.IGNORECASE)


def verify_market_claims(text, model_market):
    """Abweichungen zwischen behaupteten und echten Marktzahlen.

    Gegenstueck zu `evidence.verify_error_counts`. Ein Modellname muss im
    selben Text stehen, damit eine Zahl ihm zugeordnet wird -- sonst wuerde
    jede beliebige Zahl gegen jedes Modell geprueft.

    Gerundet gilt als korrekt: "29,7" fuer 29,69 ist lesbar, nicht erfunden.
    """
    modelle = (model_market or {}).get("modelle") or {}
    genannt = [k for k in modelle if k in text]
    if not genannt:
        return []
    bad = []
    for m in _CLAIM.finditer(text):
        feld = _FELD_NAMEN[m.group(1).lower()]
        claimed = float(m.group(2).replace(",", "."))
        for lm_key in genannt:
            actual = modelle[lm_key].get(feld)
            if actual is None:
                continue
            if round(claimed, 1) != round(float(actual), 1):
                bad.append({"modell": lm_key, "feld": feld,
                            "claimed": claimed, "actual": actual})
    return bad
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_market.py -v`
Expected: 32 passed

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: 143 passed

- [ ] **Step 6: Commit**

```bash
git add advisor/market.py tests/test_market.py
git commit -m "feat(market): Marktzahlen im Bericht gegen das JSON pruefen"
```

---

### Task 6: In `collect_ist_zustand.py` einhängen

**Files:**
- Modify: `collect_ist_zustand.py`
- Test: `tests/test_collect.py` (neu)

**Interfaces:**
- Consumes: `lade_key`, `fetch_aa`, `fetch_web`, `lade_ablehnungen`, `market_report` (Tasks 1–5)
- Produces: `sammle_markt(lm_keys) -> dict`, neuer Top-Level-Key `model_market` in `state/ist-zustand.json`

- [ ] **Step 1: Write the failing test**

```python
"""Der Ist-Zustand entsteht auch dann, wenn beide externen Quellen tot sind.

Die Telemetrie ist der wichtigere Teil des Dokuments. Ein Netzausfall darf
den Lauf nicht kippen -- sonst faellt die Routine wegen einer Nebenquelle aus.
"""
import collect_ist_zustand as cz


def test_markt_ausfall_kippt_das_dokument_nicht(monkeypatch):
    monkeypatch.setattr(cz, "lade_key", lambda: None)
    monkeypatch.setattr(cz.market, "fetch_web",
                        lambda *a, **k: {"status": "nicht_verfuegbar",
                                         "frage": "x", "abgerufen_am": "2026-08-20",
                                         "quellen": [], "hinweis": None,
                                         "grund": "Connection refused"})
    markt = cz.sammle_markt(["gemma-4-31b-it-mlx"])
    assert markt["status"] == "nicht_verfuegbar"
    assert "kein API-Key" in markt["grund"]
    assert "Connection refused" in markt["grund"]


def test_eine_exception_im_marktteil_wird_gefangen(monkeypatch):
    def kaputt(*a, **k):
        raise RuntimeError("unerwartet")

    monkeypatch.setattr(cz.market, "fetch_aa", kaputt)
    markt = cz.sammle_markt(["gemma-4-31b-it-mlx"])
    assert markt["status"] == "nicht_verfuegbar"
    assert "RuntimeError" in markt["grund"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_collect.py -v`
Expected: FAIL mit `AttributeError: module 'collect_ist_zustand' has no attribute 'sammle_markt'`

- [ ] **Step 3: Write minimal implementation**

In `collect_ist_zustand.py` ergänzen:

```python
from advisor import market
from advisor.market import lade_key

ABLEHNUNGEN = Path(__file__).parent / "state" / "abgelehnte-modelle.json"
AA_CACHE = Path(__file__).parent / "state" / "aa-cache.json"

SUCHFRAGE = ("neue MLX-Modelle fuer LM Studio 2026 Qwen Gemma Mistral "
             "Release lokale Modelle")


def sammle_markt(lm_keys):
    """Marktdaten fuer den Bericht. Faellt nie hart aus.

    Laeuft ausserhalb des Agenten-Wallclock -- der Agent bekommt fertige
    Fakten und braucht dafuer keine Iteration. Genau das war der Grund fuer
    den Umbau: bei 300 s Budget starben zwei von drei Laeufen.
    """
    try:
        aa = market.fetch_aa(lade_key(), cache_pfad=AA_CACHE)
        web = market.fetch_web(SUCHFRAGE)
        return market.market_report(
            lm_keys, aa, web, ablehnungen=market.lade_ablehnungen(ABLEHNUNGEN))
    except Exception as e:  # noqa: BLE001 -- Nebenquelle darf den Lauf nie kippen
        return {"status": "nicht_verfuegbar",
                "grund": "%s: %s" % (type(e).__name__, e),
                "modelle": {}, "nicht_gelistet": [], "suche": None}
```

Und in `main()` nach der Budget-Zeile:

```python
    markt = sammle_markt(sorted({m["model_key"] for m in all_models if m.get("model_key")}))
```

sowie im `doc`-Dict nach `"models_on_disk": all_models,`:

```python
        "model_market": markt,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_collect.py -v`
Expected: 2 passed

- [ ] **Step 5: Run the full suite and a real collection**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: 145 passed

Run: `.venv/bin/python collect_ist_zustand.py && .venv/bin/python -c "
import json; d=json.load(open('state/ist-zustand.json'))
m=d['model_market']; print('status:', m['status'], '| grund:', m.get('grund'))
print('zugeordnet:', len(m['modelle']), '| nicht gelistet:', m['nicht_gelistet'])
print('suche:', (m.get('suche') or {}).get('status'), len((m.get('suche') or {}).get('quellen') or []))"`

Expected: Ohne API-Key `status: nicht_verfuegbar` mit „kein API-Key hinterlegt", aber die Websuche liefert Quellen und das Dokument entsteht vollständig. **Prüfe zusätzlich, dass `agents` und `budget` unverändert befüllt sind.**

- [ ] **Step 6: Commit**

```bash
git add collect_ist_zustand.py tests/test_collect.py
git commit -m "feat(advisor): Marktdaten in den Ist-Zustand aufnehmen"
```

---

### Task 7: Routine-Brief neu fassen und die Kopie in der Routine nachziehen

**Files:**
- Modify: `routine-brief.md` (Abschnitt „## 3. Web-Recherche (deine Kernaufgabe)")
- Modify: `README.md` (Hinweis auf den Key und die Ablehnungsliste)

**Interfaces:**
- Consumes: `model_market`-Struktur aus Task 6
- Produces: keine Code-Schnittstelle

**Wichtig:** Die Routine führt eine **Kopie** des Briefs aus `routines.description` aus, nicht die Datei. Ohne den PATCH läuft der Agent weiter mit der alten Anleitung — genau das ist am 30.07. passiert.

- [ ] **Step 1: Abschnitt 3 ersetzen**

Ersetze in `routine-brief.md` den kompletten Abschnitt „## 3. Web-Recherche (deine Kernaufgabe)" durch:

```markdown
## 3. Marktdaten lesen (NICHT selbst recherchieren)

Du hast kein WebSearch-Werkzeug. Recherchiere nicht — die Daten liegen fertig
in `state/ist-zustand.json` unter `model_market`. Sie wurden von
`collect_ist_zustand.py` geholt, bevor du gestartet bist.

- `model_market.modelle[<lm_key>]` — je Modell `aa_slug`, `variante`,
  `intelligence_index`, `coding_index`, `agentic_index`, `release_date`.
  Quelle ist Artificial Analysis, Stand in `model_market.aa_stand`.
- `model_market.nicht_gelistet` — Modelle ohne Marktdaten. Über sie gibt es
  keine Qualitätsaussage. Das ist kein Fehler und keine Kritik am Modell.
- `model_market.suche` — Ergebnis des lokalen Websuche-Diensts zur Frage, was
  es Neues gibt. Beachte `suche.hinweis`: meldet er „nur eine Quelle" oder
  „keine Quelle", ist die Lage dünn und gehört so benannt.

**`status: "nicht_verfuegbar"` ist bindend.** Dann gilt: **kein
Modellwechsel-Vorschlag, keine Aussage über die Qualität eines Modells.**
Melde stattdessen im Bericht, dass die Marktdaten fehlten, und nenne
`model_market.grund`. Ein Lauf ohne Marktdaten ist kein Fehlschlag — eine
erfundene Empfehlung schon.

**Zahlen werden nie frei formuliert — auch Marktzahlen nicht.** Jeder
Index, den du nennst, wird aus `model_market` kopiert.
`advisor.market.verify_market_claims` prüft das gegen; ein Text mit
abweichenden Zahlen gilt als ungültiger Vorschlag. Runden ist erlaubt
(29,7 für 29,69), Erfinden nicht.

**Was die Marktdaten NICHT hergeben:**
- **Geschwindigkeit und Preis.** Artificial Analysis misst gehostete
  Cloud-Endpunkte. Über quantisiertes MLX auf dem Mac oder der RTX sagt das
  nichts. Dafür gibt es `benchmark_candidate.sh`.
- **Den Effekt der Quantisierung.** Gemessen wird die Vollpräzisions-Variante
  beim Anbieter, nicht euer 5bit- oder 8bit-MLX.
- **Die Betriebstauglichkeit.** Ein hoher Index ersetzt keine Telemetrie.
  `model_change_allowed=false` bleibt bindend: ein starkes Zielmodell heilt
  keine Config-Ursache.

**Reasoning-Varianten nie vermischen.** `variante` steht bei jedem Eintrag.
Der Abstand ist erheblich (gemma-4-31b: 29,69 als Reasoning gegen 22,3 als
Non-Reasoning). Nenne die Variante, wenn du eine Zahl nennst.

**Abgelehnte Modelle.** Trägt ein Eintrag `abgelehnt: true`, wurde das Modell
bereits praktisch geprüft und verworfen; der Grund steht in
`ablehnungsgrund`. Schlage es nicht erneut vor. Erwähnen darfst du es nur,
wenn sich der Ablehnungsgrund nachweislich erledigt hat — dann mit Beleg.
Beispiel: `qwen3.8-27b` steht auf Intelligence Index 52,0 und ist trotzdem
unbrauchbar, weil die MLX-Variante den Denkmodus nicht abschalten lässt.

Prüfe für jeden Schmerz- oder Überdimensionierungs-Kandidaten weiterhin:
- **Quant-Tuning:** besserer Quant desselben Modells (4bit↔8bit) als RAM-Hebel.
- **Kontextlänge:** passt die zugewiesene Länge zur realen Nutzung?
- **Konsolidierung:** können Agenten sich ein Modell teilen?
- **Drift:** Abweichungen zwischen dokumentiertem und tatsächlich geladenem Modell.
- **Gerät und Kontextlänge ausweisen** — die Pflichten aus `check_target`
  gelten unverändert.

**Quellenangabe (Pflicht):** Jeder Bericht, der Marktzahlen trägt, nennt
„Quelle: Artificial Analysis, Stand <aa_stand>".
```

- [ ] **Step 2: README ergänzen**

Ergänze in `README.md` einen Abschnitt:

```markdown
## Marktdaten (`advisor/market.py`)

Zwei externe Quellen, beide **vor** dem Agentenlauf geholt:

- **Artificial Analysis** (Free API, 100 Requests/24 h) — Qualitätsachse.
  Key in `~/.paperclip/instances/default/secrets/artificialanalysis.env` als
  `ARTIFICIALANALYSIS_API_KEY=…`. Fehlt er, meldet der Advisor
  `nicht_verfuegbar` und stellt keine Modellvorschläge.
- **Websuche-Dienst** `127.0.0.1:7789` (siehe `tools/websuche/`) — was es
  Neues gibt.

**Warum nicht im Agenten:** Der Träger läuft auf `lmstudio_local` und hat kein
WebSearch-Werkzeug; der Brief verlangte es trotzdem bis 20.08. Ausserdem ist
das Wallclock-Budget knapp — Recherche im Agenten kostet Iterationen.

**Ablehnungsliste:** `state/abgelehnte-modelle.json` (Vorlage unter
`state-vorlagen/`, weil `state/` gitignored ist). Ohne sie empfiehlt der
Advisor jede Woche erneut Modelle, die praktisch schon verworfen wurden.
```

- [ ] **Step 3: Commit**

```bash
git add routine-brief.md README.md
git commit -m "docs(advisor): Schritt 3 liest Marktdaten statt zu recherchieren"
```

- [ ] **Step 4: Die Kopie in der Routine nachziehen**

```bash
cd ~/.paperclip/scripts/llm-advisor
TOKEN=$(python3 -c "import json;print(json.load(open('$HOME/.paperclip/auth.json'))['credentials']['http://localhost:3100']['token'])")
python3 -c "
import json, urllib.request
body = json.dumps({'description': open('routine-brief.md').read()}).encode()
r = urllib.request.Request(
    'http://localhost:3100/api/routines/666f3c66-e9e6-47a5-ad8a-96b86a8b21fb',
    data=body, method='PATCH',
    headers={'Authorization': 'Bearer $TOKEN', 'Content-Type': 'application/json'})
print(urllib.request.urlopen(r, timeout=20).status)"
```

Expected: `200`

- [ ] **Step 5: Verify the copy actually changed**

```bash
PGPASSWORD=paperclip psql -h localhost -p 54329 -U paperclip -d paperclip -A -t -c \
  "select case when description like '%Marktdaten lesen%' then 'AKTUELL' else 'ALTSTAND' end,
          latest_revision_number
   from routines where id='666f3c66-e9e6-47a5-ad8a-96b86a8b21fb';"
```

Expected: `AKTUELL` und eine um mindestens 1 erhöhte Revisionsnummer.

---

## Nach dem Plan: was offen bleibt

1. **Der API-Key.** Sobald Walter ihn liefert: in
   `~/.paperclip/instances/default/secrets/artificialanalysis.env` ablegen
   (`chmod 600`), dann `collect_ist_zustand.py` laufen lassen und prüfen,
   **welche Felder der Free-Tier wirklich liefert**. Ergibt `kennzahlen()`
   überall `None`, stimmen die Feldnamen in `_INDEX_FELDER` nicht — dann die
   echten Namen aus der Antwort ergänzen, nicht raten.
2. **Wirkt `timeoutSec: 1800`?** Zeigt der Lauf am Montag 07:00. Kommt erneut
   ein Wallclock-Timeout, ist die nächste Stellschraube nicht das Budget,
   sondern die Zahl der Schritte im Brief.
3. **Erst nach zwei bis drei Läufen bewerten**, ob die Marktdaten die Qualität
   der Befunde heben. `evaluate_history.py` misst das bereits mit.
