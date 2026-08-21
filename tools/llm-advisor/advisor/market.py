"""Modellmarkt: externe Kennzahlen und Neuigkeiten, gesammelt statt recherchiert.

Geholt wird nicht "vor dem Agentenlauf": `collect_ist_zustand.py` ist
Schritt 1 des Agenten-Briefs, es gibt keinen launchd-Job dafuer. Die Zahlen
in `state/ist-zustand.json` sind also genau so frisch wie dieser eine
Aufruf. Faellt er aus oder wird er uebersprungen, liest der Agent die Datei
der Vorwoche und haelt sie fuer aktuell -- alte Zahlen als neue ausgegeben,
also derselbe Fehlertyp, gegen den der nie gelesene Cache abgesichert ist,
nur durch die Vordertuer. Der Brief sagt das inzwischen so.

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

import datetime as _dt
import json
import os
import re
import time as _time
import urllib.error
import urllib.request
from pathlib import Path


def nicht_verfuegbar(grund, **felder):
    """Ein Ausfall-Eintrag in immer derselben Form.

    Vier Stellen bauten diesen Dict auf vier Arten zusammen -- und genau
    daran verlor der Fallback in `collect_ist_zustand.sammle_markt` die
    Felder `aa_stand` und `quelle`, die der Brief fuer die
    Pflicht-Quellenangabe verlangt. `status` und `grund` stehen immer vorn,
    alles Weitere reicht der Aufrufer als Schluesselwort nach.
    """
    aus = {"status": "nicht_verfuegbar", "grund": grund}
    aus.update(felder)
    return aus


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


def _overrides_nach_norm(tabelle):
    """Die Override-Tabelle zusaetzlich ueber die Normalform erreichbar machen.

    Ein Eintrag, dessen Schluessel bereits die Normalform IST, gilt als die
    allgemeine Regel und schlaegt einen Eintrag mit Quantisierungssuffix --
    sonst entschiede die Reihenfolge im Dict, welche Variante die Regel fuer
    alle ihre Geschwister stellt.
    """
    aus = {}
    for schluessel, ziel in tabelle.items():
        norm = normalisiere(schluessel)
        if norm not in aus or schluessel == norm:
            aus[norm] = ziel
    return aus


def match_slug(lm_key, slugs, overrides=None):
    """Den AA-Slug zu einem LM-Studio-Schluessel, oder None.

    Kein Fuzzy-Matching: exakter Treffer, Override oder nichts. Ein
    naeherungsweise passender Nachbar (qwen3-coder-30b -> das 480B-Modell)
    liefert eine Zahl, die falsch ist und richtig aussieht.

    Overrides greifen auf zwei Wegen: erst auf den rohen Schluessel, dann auf
    seine Normalform. Der erste echte AA-Abruf am 21.08. zeigte, warum die
    zweite Stufe noetig ist -- `mistral-small-3.2-24b-instruct-2506` stand in
    der Tabelle, die real geladene `-mlx`-Variante lief daran vorbei und
    landete in `nicht_gelistet`. Dieselbe Luecke hatte zuvor schon die
    Ablehnungsliste. Der rohe Treffer behaelt Vorrang, damit sich eine
    einzelne Quantisierung weiterhin gezielt anders behandeln laesst.
    """
    tabelle = OVERRIDES if overrides is None else overrides
    if lm_key in tabelle:
        return tabelle[lm_key]
    kandidat = normalisiere(lm_key)
    nach_norm = _overrides_nach_norm(tabelle)
    if kandidat in nach_norm:
        return nach_norm[kandidat]
    return kandidat if kandidat in slugs else None


AA_URL = os.environ.get(
    "AA_API_URL", "https://artificialanalysis.ai/api/v2/language/models/free")
AA_KEY_PFAD = Path(os.path.expanduser(
    "~/.paperclip/instances/default/secrets/artificialanalysis.env"))
QUELLE = "Artificial Analysis (Free API)"

# Deckel gegen ein has_more, das nie false wird. Das Free-Kontingent liegt bei
# 100 Requests pro 24 Stunden -- eine Schleife wuerde es in Sekunden leeren.
MAX_SEITEN = 20

# Gesamtbudget fuer alle Seiten zusammen. MAX_SEITEN mal Einzel-Timeout waeren
# 400 s -- der Sammellauf ist Schritt 1 des Agenten-Briefs und liegt in dem
# Wallclock, an dem zwei von drei Laeufen seit dem Traegerwechsel gestorben sind.
AA_BUDGET_S = 60

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


def fetch_aa(key, oeffner=None, timeout=20, cache_pfad=None,
             budget_s=AA_BUDGET_S, uhr=None):
    """Alle Modelle des Free-Endpunkts, paginiert und zeitlich gedeckelt.

    Kein Ausfall wirft: ein fehlender Key, ein 401 oder ein Netzfehler wird
    zu `status: "nicht_verfuegbar"` mit Grund. Der Advisor meldet die Luecke,
    statt ohne Marktdaten weiterzuraten.

    `budget_s` ist ein hartes Gesamtbudget ueber alle Seiten. MAX_SEITEN mal
    `timeout` liesse sonst bis zu 400 s zu, bevor die Websuche ueberhaupt
    beginnt -- und der Sammellauf ist Schritt 1 des Agenten-Briefs, liegt also
    in demselben Wallclock, an dem am 03.08. und 17.08. je ein Lauf gestorben
    ist. Ist das Budget erschoepft, kommt zurueck was da ist, mit `hinweis`;
    geworfen wird nichts. Der Einzel-Timeout wird auf das Restbudget gekuerzt,
    damit der letzte Request das Budget nicht doch noch ueberzieht.

    `cache_pfad` legt die Rohantwort ab -- zur **Nachvollziehbarkeit**, damit
    sich spaeter rekonstruieren laesst, was beim Lauf dastand. Der Cache wird
    bewusst **nie gelesen**: ein Lese-Fallback wuerde alte Zahlen als aktuelle
    ausgeben und damit genau den Fehlertyp erzeugen, den dieser Umbau
    beseitigen soll.
    """
    heute = _dt.date.today().isoformat()
    kopf = {"quelle": QUELLE, "aa_stand": heute}
    if not key:
        return nicht_verfuegbar(
            "kein API-Key hinterlegt (%s)" % AA_KEY_PFAD,
            modelle_roh=[], hinweis=None, **kopf)
    oeffner = oeffner or _oeffne
    uhr = uhr or _time.monotonic
    gesammelt = []
    hinweis = None
    start = uhr()
    try:
        for seite in range(1, MAX_SEITEN + 1):
            verbleibend = budget_s - (uhr() - start)
            if verbleibend <= 0:
                hinweis = ("Zeitbudget von %s s erschoepft nach %d Seite(n) -- "
                           "die Modell-Liste ist unvollstaendig."
                           % (budget_s, seite - 1))
                break
            trenner = "&" if "?" in AA_URL else "?"
            with oeffner("%s%spage=%d" % (AA_URL, trenner, seite), key,
                         min(timeout, max(1, verbleibend))) as antwort:
                doc = json.loads(antwort.read().decode("utf-8"))
            # JSON muss ein Objekt sein, nicht null oder array.
            if not isinstance(doc, dict):
                raise ValueError("API response is not a JSON object")
            # `data` muss eine Liste sein; andere Typen werden ignoriert.
            daten = doc.get("data")
            if isinstance(daten, list):
                gesammelt.extend(daten)
            # `pagination` muss ein dict sein; nur dann checken wir has_more.
            seiten_info = doc.get("pagination")
            if not isinstance(seiten_info, dict):
                seiten_info = {}
            if not seiten_info.get("has_more"):
                break
    except (OSError, urllib.error.URLError, ValueError) as e:
        return nicht_verfuegbar("%s: %s" % (type(e).__name__, e),
                                modelle_roh=[], hinweis=None, **kopf)
    ergebnis = dict(kopf, status="ok", grund=None, hinweis=hinweis,
                    modelle_roh=gesammelt)
    if cache_pfad is not None:
        try:
            Path(cache_pfad).parent.mkdir(parents=True, exist_ok=True)
            Path(cache_pfad).write_text(
                json.dumps(ergebnis, ensure_ascii=False, indent=2))
        except OSError:
            pass        # Ein nicht schreibbarer Cache ist kein Grund, den Lauf zu kippen.
    return ergebnis


WEBSUCHE_URL = os.environ.get("WEBSUCHE_URL", "http://127.0.0.1:7789/suche")


def _oeffne_websuche(url, rumpf, timeout):
    daten = json.dumps(rumpf).encode("utf-8")
    r = urllib.request.Request(
        url, data=daten, method="POST",
        headers={"Content-Type": "application/json"})
    return urllib.request.urlopen(r, timeout=timeout)


def fetch_web(frage, oeffner=None, quellen=3, zeichen=6000, deadline=30):
    """Den lokalen Websuche-Dienst fragen (siehe tools/websuche/).

    Kostet keine Agenten-Iteration -- aber sehr wohl Wallclock: der
    Sammellauf ist Schritt 1 des Briefs und laeuft im selben Zeitbudget.
    Deshalb die `deadline`, und deshalb hat `fetch_aa` davor ein eigenes.
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
        # JSON muss ein Objekt sein, nicht null oder array.
        if not isinstance(doc, dict):
            raise ValueError("Antwort ist kein JSON-Objekt")
    except (OSError, urllib.error.URLError, ValueError) as e:
        return nicht_verfuegbar("%s: %s" % (type(e).__name__, e), frage=frage,
                                abgerufen_am=heute, quellen=[], hinweis=None)
    # `quellen` muss eine Liste sein; andere Typen werden ignoriert.
    quellen_raw = doc.get("quellen")
    quellen_list = quellen_raw if isinstance(quellen_raw, list) else []
    return {"status": "ok", "frage": frage,
            "abgerufen_am": doc.get("abgerufen_am") or heute,
            "quellen": quellen_list,
            "hinweis": doc.get("hinweis")}


def waehle_variante(records):
    """Slug -> Record. Bei Slug-Kollisionen gewinnt die Reasoning-Variante.

    AA fuehrt Reasoning und Non-Reasoning getrennt, oft unter dem gleichen
    Slug. Der Abstand ist erheblich (gemma-4-31b: 29,69 gegen 22,3). Diese
    Funktion bevorzugt die Reasoning-Variante auf Kollisionen, damit der
    Vergleich nicht ueber die Variantengrenze hinweg faellt. Die typische
    Slug-Aufloesung (qwen3.6 statt qwen3-6) geschieht in normalisiere/
    match_slug; diese Funktion traegt nur noch die Variant-Preference.
    """
    aus = {}
    for r in records:
        slug = r.get("slug")
        if slug:
            # Reasoning schlaegt Non-Reasoning beim gleichen Slug.
            if slug not in aus or _variante(r) == "Reasoning":
                aus[slug] = r
    return aus


def _variante(record):
    """Reasoning / Non-Reasoning / unbekannt aus dem Name-Feld.

    Die AA-Namen enthalten unterschiedliche Effort-Suffixe:
    - (Reasoning) / (Reasoning, Max Effort)
    - (Adaptive Reasoning, Low Effort)
    - (Non-reasoning) / (Non-reasoning, High Effort)

    Nur die Variante wird extrahiert; Effort-Angaben fallen weg. Die Reihenfolge
    der Checks ist kritisch: "non-reasoning" muss VOR "reasoning" geprueft werden,
    weil die erste ein Substring der zweiten ist (substring trap).
    """
    name = record.get("name") or ""
    name_lower = name.lower()
    # non-reasoning MUSS vor reasoning geprueft werden!
    if "non-reasoning" in name_lower:
        return "Non-Reasoning"
    if "reasoning" in name_lower:
        return "Reasoning"
    return "unbekannt"


def lade_ablehnungen(pfad):
    """Die Ablehnungsliste als dict modell -> eintrag. Fehlt sie, ist sie leer.

    Shape-Guard: Die Datei kann von Hand editiert sein und damit fehlgeformt.
    Ein JSON-Objekt statt Array wird ignoriert; Nicht-Dicts in der Liste werden
    uebersprungen; Eintraege ohne truthy modell-Feld werden ignoriert. Ein
    Fehler wird nie geworfen (fail-closed).
    """
    try:
        roh = json.loads(Path(pfad).read_text())
    except (OSError, ValueError):
        return {}
    # JSON muss eine Liste sein.
    if not isinstance(roh, list):
        return {}
    aus = {}
    for e in roh:
        # Element muss ein dict sein mit einem truthy modell-Feld.
        if isinstance(e, dict) and e.get("modell"):
            aus[e["modell"]] = e
    return aus


def market_report(lm_keys, aa, web, ablehnungen=None):
    """Das `model_market`-Fragment fuer ist-zustand.json.

    Faellt eine der beiden Quellen aus, ist der Gesamtstatus
    `nicht_verfuegbar` samt Grund. Der Brief verbietet in diesem Fall jede
    Modellempfehlung -- ein Agent ohne Marktdaten, der trotzdem etwas sagen
    soll, erfindet (Mail vom 07.08.).
    """
    # Ablehnungen ueber die Normalform nachschlagen. Auf Platte liegen drei
    # Schluessel fuer dasselbe Modell (qwen3.8-27b, -mlx, -mtplx), die Liste
    # nennt nur einen -- und der Ablehnungsgrund ("MLX-Variante laesst
    # reasoning_effort=none nicht zu") betrifft ausgerechnet die Variante, die
    # bei exakter Schluesselgleichheit ungebrandmarkt durchrutschte: mit
    # Intelligence Index 52,0 der attraktivste Eintrag im ganzen Katalog.
    ablehnungen = ablehnungen or {}
    nach_norm = {}
    for schluessel, eintrag in ablehnungen.items():
        nach_norm.setdefault(normalisiere(schluessel), eintrag)

    nach_slug = waehle_variante(aa.get("modelle_roh") or [])
    slugs = set(nach_slug)
    aa_stand = aa.get("aa_stand")

    modelle, nicht_gelistet = {}, []
    for lm_key in lm_keys:
        slug = match_slug(lm_key, slugs)
        # `slug not in nach_slug` ist kein toter Zweig: match_slug liefert
        # Override-Ziele zurueck, ohne sie gegen `slugs` zu pruefen. Ein
        # Override auf einen Slug, den AA gerade nicht liefert, ergaebe sonst
        # einen KeyError mitten im Sammellauf.
        if slug is None or slug not in nach_slug:
            nicht_gelistet.append(lm_key)
            continue
        record = nach_slug[slug]
        eintrag = {"aa_slug": slug, "variante": _variante(record),
                   "release_date": record.get("release_date")}
        eintrag.update(kennzahlen(record))
        abgelehnt = nach_norm.get(normalisiere(lm_key))
        if abgelehnt is not None:
            eintrag["abgelehnt"] = True
            eintrag["ablehnungsgrund"] = abgelehnt.get("grund")
            eintrag["abgelehnt_am"] = abgelehnt.get("abgelehnt_am")
        # Der fertige Satz zum Uebernehmen -- wie `evidence` je Agent.
        eintrag["zeile"] = markt_zeile(lm_key, eintrag, aa_stand=aa_stand)
        modelle[lm_key] = eintrag

    # Der Status folgt den Quellen-Status, NICHT dem Vorhandensein eines
    # Grundtexts: eine Quelle, die `nicht_verfuegbar` ohne `grund` meldet,
    # ergab frueher Gesamtstatus "ok" -- fail-open in der einen Funktion,
    # die fail-closed sein muss.
    ausfaelle = [q for q in (aa, web) if q.get("status") != "ok"]
    gruende = [q.get("grund") for q in ausfaelle if q.get("grund")]
    return {
        "status": "nicht_verfuegbar" if ausfaelle else "ok",
        "grund": "; ".join(gruende) if gruende else None,
        "aa_stand": aa_stand,
        "quelle": aa.get("quelle"),
        "aa_hinweis": aa.get("hinweis"),
        "modelle": modelle,
        "nicht_gelistet": nicht_gelistet,
        "suche": web,
    }


# Indexnamen: Kurzform (regex) -> Feldname im Modell-dict.
_FELD_NAMEN = {"intelligence": "intelligence_index",
               "coding": "coding_index",
               "agentic": "agentic_index"}

# Reihenfolge der Indizes in der gerenderten Zeile.
_FELD_LABEL = (("intelligence_index", "Intelligence Index"),
               ("coding_index", "Coding Index"),
               ("agentic_index", "Agentic Index"))

# Findet nur die Index-Labels, nicht die Zahlen (um deutsches Prosa zu handhaben).
_LABEL = re.compile(
    r"\b(intelligence|coding|agentic)\s*-?\s*index\b",
    re.IGNORECASE)

# Findet Zahlen mit Dezimaltrennern, aber nicht Nummern aus Identifiern wie "gemma-4-31b".
# Negative lookbehind: nicht nach Buchstabe oder Bindestrich.
# Negative lookahead: nicht vor Buchstabe (aber Bindestrich ist ok, um "55,0" zu erlauben).
_NUMBER = re.compile(r"(?<![a-zA-Z-])\d+(?:[.,]\d+)?(?![a-zA-Z-])")

# Fensterbreite zwischen Index-Label und zugehoeriger Zahl, in beide Richtungen.
_WINDOW_SIZE = 40

# Satzende: Punkt, Ausrufe-, Fragezeichen oder Semikolon, gefolgt von Leerraum
# oder Textende. Der Punkt in "29.69" faellt nicht darunter, weil ihm eine
# Ziffer folgt. Begrenzt das Vorwaertsfenster zusaetzlich zur Zeichenzahl.
_SATZENDE = re.compile(r"[.!?;](?=\s|$)")

# Trennzeile einer Markdown-Tabelle: nur |, -, : und Leerzeichen.
_TABELLEN_TRENNER = re.compile(r"^[\s|:-]*-[\s|:-]*$")


def _zahl_de(wert):
    """Eine Zahl in deutscher Schreibweise, ohne sie zu veraendern.

    `str()` statt Formatstring: 29.69 bleibt "29,69" und 52.0 bleibt "52,0".
    Gerundet wird hier nichts -- der Waechter laesst Runden zwar durchgehen,
    aber gerendert wird immer der Wert, der im JSON steht.
    """
    if isinstance(wert, (int, float)) and not isinstance(wert, bool):
        return str(wert).replace(".", ",")
    return str(wert)


def markt_zeile(lm_key, eintrag, aa_stand=None):
    """Die Marktzahlen eines Modells als uebernehmbarer Satz.

    Gegenstueck zu `evidence.evidence_line` -- und die Haelfte, die dem
    Marktteil bis zum Branch-Review vom 20.08. fehlte. Ein Waechter allein
    laesst den Agenten die Zahlen weiter frei formulieren und faengt den
    Fehler erst hinterher; erst der fertige Satz nimmt ihm das Formulieren
    ab. Genau das war die Lehre aus dem Approval vom 31.07. (WHI-3389).

    Der Satz traegt alles, was der Brief verlangt: die drei Indizes, die
    Variante (Reasoning und Non-Reasoning liegen bei gemma-4-31b 7,4 Punkte
    auseinander) und die Pflicht-Quellenangabe mit `aa_stand`. Ein fehlender
    Index steht als "nicht verfuegbar" -- nie als geschaetzte Zahl.

    Traegt der Eintrag `abgelehnt`, steht das mit im Satz: die Zahl ohne den
    Ablehnungsgrund ist genau die Halbinformation, die qwen3.8-27b (Index
    52,0) jede Woche neu zur Empfehlung gemacht hat.
    """
    eintrag = eintrag or {}
    teile = []
    for feld, label in _FELD_LABEL:
        wert = eintrag.get(feld)
        teile.append("%s %s" % (
            label, "nicht verfuegbar" if wert is None else _zahl_de(wert)))
    kopf = "%s (AA-Slug %s, Variante %s)" % (
        lm_key, eintrag.get("aa_slug") or "unbekannt",
        eintrag.get("variante") or "unbekannt")
    satz = "%s: %s -- Quelle: Artificial Analysis, Stand %s" % (
        kopf, ", ".join(teile), aa_stand or "unbekannt")
    if eintrag.get("abgelehnt"):
        satz += " [abgelehnt am %s: %s]" % (
            eintrag.get("abgelehnt_am") or "unbekannt",
            eintrag.get("ablehnungsgrund") or "ohne Grundangabe")
    return satz


def _bekannte_namen(model_market):
    """Jeder Name, unter dem ein Modell im Text auftauchen kann.

    Kleingeschriebener Name -> (Anzeigename, gelistet?). Nicht gelistete
    Modelle zaehlen ausdruecklich mit: ueber sie gibt es gar keine
    Qualitaetsaussage, also ist jede Indexzahl zu ihnen erfunden. Der alte
    Waechter kannte sie nicht und liess sie deshalb komplett durch -- und
    genau das sind die Kandidatenmodelle, ueber die der Advisor schreibt.
    """
    mm = model_market or {}
    modelle = mm.get("modelle")
    if not isinstance(modelle, dict):
        modelle = {}
    ungelistet = mm.get("nicht_gelistet")
    if not isinstance(ungelistet, list):
        ungelistet = []
    namen = {}
    for lm_key, eintrag in modelle.items():
        namen.setdefault(lm_key.lower(), (lm_key, True))
        slug = eintrag.get("aa_slug") if isinstance(eintrag, dict) else None
        if slug:
            namen.setdefault(slug.lower(), (lm_key, True))
    for name in ungelistet:
        if isinstance(name, str) and name:
            namen.setdefault(name.lower(), (name, False))
    return namen


def _vorkommen(text_lower, namen):
    """Alle Fundstellen bekannter Modellnamen als (start, ziel), sortiert."""
    treffer = []
    for name, ziel in namen.items():
        start = text_lower.find(name)
        while start != -1:
            treffer.append((start, ziel))
            start = text_lower.find(name, start + 1)
    treffer.sort(key=lambda t: t[0])
    return treffer


def _modell_vor(vorkommen, pos):
    """Das Modell, dessen Name der Stelle `pos` zuletzt vorausging, oder None.

    Die Bindung an genau ein Modell ist der Kern des Umbaus vom 20.08.: der
    alte Waechter hielt jede Zahl gegen jedes im Text genannte Modell und
    erzeugte damit bei einem korrekten Vergleich von n Modellen rund n*(n-1)
    Scheinbefunde.
    """
    ziel = None
    for start, kandidat in vorkommen:
        if start < pos:
            ziel = kandidat
        else:
            break
    return ziel


def _zellen(zeile, zeilen_start):
    """Die Zellen einer Markdown-Tabellenzeile als (offset, text)-Liste.

    Fuehrende und abschliessende Leerzelle (aus `| a | b |`) fallen weg,
    damit Kopf- und Datenzeile dieselbe Spaltennummerierung haben.
    """
    aus, pos = [], 0
    for teil in zeile.split("|"):
        aus.append((zeilen_start + pos, teil))
        pos += len(teil) + 1
    if aus and not aus[0][1].strip():
        aus = aus[1:]
    if aus and not aus[-1][1].strip():
        aus = aus[:-1]
    return aus


def _tabellen_claims(text, vorkommen):
    """Index-Claims aus Markdown-Tabellen, spaltenweise zugeordnet.

    In einer Tabelle steht das Label in der Kopfzeile und die Zahl in der
    Datenzeile darunter -- oft Dutzende Zeichen entfernt und in anderer
    Reihenfolge. Der positionsnahe Finder pruefte deshalb die
    Intelligence-Zahl gegen den Coding-Index und sah die letzte Spalte gar
    nicht (Sonde 2 des Reviews vom 20.08.).

    Liefert (claims, bereiche): die Claims und die Zeichenbereiche der
    verarbeiteten Tabellenzeilen, damit der Prosa-Durchlauf sie auslaesst.
    """
    claims, bereiche = [], []
    zeilen, offset = [], 0
    for zeile in text.split("\n"):
        zeilen.append((offset, zeile))
        offset += len(zeile) + 1

    i = 0
    while i < len(zeilen) - 1:
        kopf_start, kopf = zeilen[i]
        trenn_zeile = zeilen[i + 1][1]
        if ("|" not in kopf or not _LABEL.search(kopf)
                or "|" not in trenn_zeile
                or not _TABELLEN_TRENNER.match(trenn_zeile)):
            i += 1
            continue
        spalten = {}
        for nr, (_, zelle) in enumerate(_zellen(kopf, kopf_start)):
            treffer = _LABEL.search(zelle)
            if treffer:
                spalten[nr] = _FELD_NAMEN[treffer.group(1).lower()]
        bereiche.append((kopf_start, kopf_start + len(kopf)))
        bereiche.append((zeilen[i + 1][0], zeilen[i + 1][0] + len(trenn_zeile)))

        j = i + 2
        while j < len(zeilen):
            start, zeile = zeilen[j]
            if "|" not in zeile or not zeile.strip():
                break
            bereiche.append((start, start + len(zeile)))
            # Das Modell der Zeile steht meist in der ersten Spalte -- also
            # NACH keiner, aber vor manchen Zahlen. Deshalb gilt hier die
            # ganze Zeile als Bezug, nicht die Position.
            modell = None
            for v_start, ziel in vorkommen:
                if start <= v_start < start + len(zeile):
                    modell = ziel
                    break
            if modell is None:
                modell = _modell_vor(vorkommen, start)
            for nr, (zell_start, zelle) in enumerate(_zellen(zeile, start)):
                feld = spalten.get(nr)
                if not feld:
                    continue
                zahl = _NUMBER.search(zelle)
                if zahl:
                    claims.append((feld, float(zahl.group(0).replace(",", ".")),
                                   zell_start + zahl.start(), modell, True))
            j += 1
        i = j
    return claims, bereiche


def _prosa_claims(maskiert):
    """Index-Claims aus Fliesstext, in beiden Leserichtungen.

    Vorwaerts: die ERSTE Zahl zwischen Label und der naechsten Grenze --
    naechstes Label, Satzende oder `_WINDOW_SIZE`, was zuerst kommt.

    Vorher wurden alle Zahlen im Fenster geprueft, mit der Begruendung,
    "Intelligence Index 29,69 (Vorwoche 27,1)" enthalte zwei Behauptungen.
    Der erste Praxisblick am 21.08. widerlegte das: was hinter der ersten
    Zahl steht, ist im Bericht praktisch immer Kontext -- Kontextlaenge,
    RAM, Skala, Abstand zum Nachbarn, Vorwochenwert. Sechs natuerliche
    KORREKTE Saetze loesten dadurch Fehlalarm aus, und ein Befund heisst
    laut Brief "nicht senden". Historische Werte kann der Waechter ohnehin
    nicht pruefen: `model_market` fuehrt keine Historie, jeder Vorwochenwert
    waere also per Konstruktion ein Befund.

    Rueckwaerts (nur wenn vorwaerts nichts steht): die naechste noch nicht
    vergebene Zahl vor dem Label. "erreicht 41,2 Punkte im Intelligence
    Index" ist die Sonde, an der der alte Waechter nichts fand.

    Bekannte Grenze: "Intelligence Index und Coding Index liegen bei 29,7
    und 43,4" ordnet die erste Zahl dem zweiten Label zu. Der Brief laesst
    den Agenten die fertige `zeile` kopieren, in der dieser Fall nicht
    vorkommt.
    """
    labels = [(m.start(), m.end(), _FELD_NAMEN[m.group(1).lower()])
              for m in _LABEL.finditer(maskiert)]
    zahlen = [(m.start(), float(m.group(0).replace(",", ".")))
              for m in _NUMBER.finditer(maskiert)]
    claims, verbraucht, offen = [], set(), []

    for nr, (_, label_ende, feld) in enumerate(labels):
        grenze = label_ende + _WINDOW_SIZE
        if nr + 1 < len(labels):
            grenze = min(grenze, labels[nr + 1][0])
        satz = _SATZENDE.search(maskiert, label_ende, grenze)
        if satz is not None:
            grenze = satz.start()
        gefunden = False
        for z_start, wert in zahlen:
            if label_ende <= z_start < grenze:
                claims.append((feld, wert, z_start, None, False))
                verbraucht.add(z_start)
                gefunden = True
                break          # nur die erste Zahl ist die Behauptung
        if not gefunden:
            offen.append(nr)

    for nr in offen:
        label_start, _, feld = labels[nr]
        grenze = label_start - _WINDOW_SIZE
        if nr > 0:
            grenze = max(grenze, labels[nr - 1][1])
        kandidat = None
        for z_start, wert in zahlen:
            if grenze <= z_start < label_start and z_start not in verbraucht:
                kandidat = (z_start, wert)     # die naechstliegende gewinnt
        if kandidat is not None:
            claims.append((feld, kandidat[1], kandidat[0], None, False))
            verbraucht.add(kandidat[0])
    return claims


def verify_market_claims(text, model_market):
    """Abweichungen zwischen behaupteten und echten Marktzahlen.

    Gegenstueck zu `markt_zeile` und Zwilling von
    `evidence.verify_error_counts`: gerendert wird oben, geprueft wird hier.

    Jede Zahl wird an **genau ein** Modell gebunden -- das, dessen Name ihr
    zuletzt vorausging, in Tabellen das der eigenen Zeile. Der alte Waechter
    prueft jede Zahl gegen jedes genannte Modell; ein korrekter Vergleich
    zweier Modelle ergab damit vier Fehlalarme, und weil der Brief einen
    beanstandeten Text zum Korrigieren zurueckgibt, haette er die
    Normalausgabe des Advisors zuverlaessig blockiert.

    Ein Befund entsteht, wenn die Zahl abweicht, wenn das Feld im JSON `null`
    ist, wenn das Modell in `nicht_gelistet` steht (ueber es gibt es keine
    Qualitaetsaussage) -- und wenn ueberhaupt kein Modell vorausgeht. Dann
    steht `modell` leer: eine Zahl, die an nichts haengt, ist nicht
    rueckverfolgbar und gehoert einem Menschen vorgelegt, nicht
    stillschweigend durchgelassen.

    Modellnamen: LM-Studio-Schluessel, aa_slug und die Namen aus
    `nicht_gelistet`, jeweils case-insensitiv.

    Gerundet gilt als korrekt: "29,7" fuer 29,69 ist lesbar, nicht erfunden.
    """
    text = text or ""
    mm = model_market or {}
    modelle = mm.get("modelle")
    if not isinstance(modelle, dict):
        modelle = {}

    vorkommen = _vorkommen(text.lower(), _bekannte_namen(mm))
    claims, bereiche = _tabellen_claims(text, vorkommen)

    # Tabellenzeilen ausblenden, ohne die Offsets zu verschieben: der
    # Prosa-Durchlauf wuerde dort die Kopfzeilen-Labels an die Zahlen der
    # Datenzeilen binden.
    maske = list(text)
    for start, ende in bereiche:
        for pos in range(start, min(ende, len(maske))):
            maske[pos] = " "
    claims.extend(_prosa_claims("".join(maske)))

    bad, gesehen = [], set()
    for feld, behauptet, pos, modell, fest in sorted(claims, key=lambda c: c[2]):
        if not fest:
            modell = _modell_vor(vorkommen, pos)
        if modell is None:
            name, gelistet = "", False
        else:
            name, gelistet = modell
        eintrag = modelle.get(name) if gelistet else None
        tatsaechlich = eintrag.get(feld) if isinstance(eintrag, dict) else None
        # Shape-Check an der Stelle der Nutzung: ein Index, der keine Zahl
        # ist, deckt keine Behauptung -- er wird zum Befund, nicht zum Absturz.
        if (isinstance(tatsaechlich, (int, float))
                and not isinstance(tatsaechlich, bool)
                and round(behauptet, 1) == round(float(tatsaechlich), 1)):
            continue
        schluessel = (name, feld, behauptet)
        if schluessel in gesehen:
            continue
        gesehen.add(schluessel)
        bad.append({"modell": name, "feld": feld,
                    "claimed": behauptet, "actual": tatsaechlich})
    return bad
