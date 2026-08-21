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


def test_fetch_aa_bricht_am_zeitbudget_ab_statt_weiterzulaufen():
    # MAX_SEITEN=20 mal timeout=20 lassen bis zu 400 s zu, bevor die Websuche
    # ueberhaupt anfaengt. Der Sammellauf ist Schritt 1 des Agenten-Briefs und
    # liegt damit im selben Wallclock, an dem zwei von drei Laeufen seit dem
    # Traegerwechsel gestorben sind. Also: hartes Gesamtbudget, und was bis
    # dahin da ist, wird zurueckgegeben statt geworfen.
    stand = [0.0]
    aufrufe = []

    def uhr():
        return stand[0]

    def oeffner(url, key, timeout):
        aufrufe.append(timeout)
        stand[0] += 25.0        # jede Seite kostet 25 s
        return _FakeAntwort(_seite([{"slug": "s%d" % len(aufrufe)}], has_more=True))

    ergebnis = fetch_aa("schluessel", oeffner=oeffner, budget_s=60, uhr=uhr)
    assert ergebnis["status"] == "ok"
    assert len(aufrufe) == 3          # bei 75 s ist Schluss, nicht bei 20 Seiten
    assert len(ergebnis["modelle_roh"]) == 3
    assert "Zeitbudget" in ergebnis["hinweis"]


def test_fetch_aa_kuerzt_den_einzel_timeout_auf_das_restbudget():
    # Ohne das koennte ein haengender Request nach 59 s noch einmal volle
    # 20 s draufpacken -- das Budget waere nur ungefaehr eingehalten.
    stand = [0.0]
    aufrufe = []

    def uhr():
        return stand[0]

    def oeffner(url, key, timeout):
        aufrufe.append(timeout)
        stand[0] += 25.0
        return _FakeAntwort(_seite([{"slug": "x"}], has_more=True))

    fetch_aa("schluessel", oeffner=oeffner, budget_s=60, timeout=20, uhr=uhr)
    assert aufrufe == [20, 20, 10]


def test_fetch_aa_ohne_budgetdruck_meldet_keinen_hinweis():
    def oeffner(url, key, timeout):
        return _FakeAntwort(_seite([{"slug": "a"}]))

    assert fetch_aa("schluessel", oeffner=oeffner)["hinweis"] is None


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


def test_malformed_json_null_wird_zu_nicht_verfuegbar():
    # JSON ist syntaktisch valid aber hat keine .get() Methode.
    def oeffner(url, key, timeout):
        return _FakeAntwort(None)  # Wird zu JSON null

    ergebnis = fetch_aa("schluessel", oeffner=oeffner)
    assert ergebnis["status"] == "nicht_verfuegbar"
    assert ergebnis["grund"]  # Fehlergrund gespeichert
    assert ergebnis["modelle_roh"] == []


def test_malformed_json_array_wird_zu_nicht_verfuegbar():
    # JSON-Array statt Objekt - keine .get() Methode.
    def oeffner(url, key, timeout):
        return _FakeAntwort([{"slug": "a"}])  # Array, nicht dict

    ergebnis = fetch_aa("schluessel", oeffner=oeffner)
    assert ergebnis["status"] == "nicht_verfuegbar"
    assert ergebnis["grund"]
    assert ergebnis["modelle_roh"] == []


def test_vollkommen_invalides_json_wird_zu_nicht_verfuegbar():
    # JSON ist nicht einmal syntaktisch valid.
    def oeffner(url, key, timeout):
        resp = _FakeAntwort(None)
        resp._rumpf = b"{invalid json"  # Syntaktisch invalid
        return resp

    ergebnis = fetch_aa("schluessel", oeffner=oeffner)
    assert ergebnis["status"] == "nicht_verfuegbar"
    assert ergebnis["grund"]
    assert ergebnis["modelle_roh"] == []


def test_pagination_ist_kein_dict_wird_als_leer_behandelt():
    # pagination kann eine Zahl oder array sein -- wird wie "kein has_more" behandelt.
    seiten = [
        _seite([{"slug": "a"}], has_more=True),  # Erste Seite mit has_more=True
        {"tier": "free", "pagination": 5,  # Zweite Seite: pagination ist int
         "data": [{"slug": "b"}]},  # has_more ist absent, wird als False interpretiert
    ]
    aufrufe = []

    def oeffner(url, key, timeout):
        aufrufe.append(url)
        return _FakeAntwort(seiten[len(aufrufe) - 1])

    ergebnis = fetch_aa("schluessel", oeffner=oeffner)
    assert ergebnis["status"] == "ok"
    assert [m["slug"] for m in ergebnis["modelle_roh"]] == ["a", "b"]
    assert len(aufrufe) == 2  # Stoppt bei zweiter Seite weil pagination falsch geformt


def test_data_ist_keine_liste_wird_als_leer_behandelt():
    # data kann eine Zahl, String oder null sein -- wird wie leeres array behandelt.
    seite = {"tier": "free", "pagination": {"page": 1, "has_more": False},
             "data": "invalid"}  # data ist string statt list

    def oeffner(url, key, timeout):
        return _FakeAntwort(seite)

    ergebnis = fetch_aa("schluessel", oeffner=oeffner)
    assert ergebnis["status"] == "ok"
    assert ergebnis["modelle_roh"] == []  # Leere Liste, kein Fehler


def test_data_ist_null_wird_als_leer_behandelt():
    seite = {"tier": "free", "pagination": {"page": 1, "has_more": False},
             "data": None}  # data ist null

    def oeffner(url, key, timeout):
        return _FakeAntwort(seite)

    ergebnis = fetch_aa("schluessel", oeffner=oeffner)
    assert ergebnis["status"] == "ok"
    assert ergebnis["modelle_roh"] == []


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


def test_json_null_wird_zu_nicht_verfuegbar():
    # JSON ist syntaktisch valid aber hat keine .get() Methode.
    def oeffner(url, rumpf, timeout):
        return _FakeAntwort(None)  # Wird zu JSON null

    ergebnis = fetch_web("x", oeffner=oeffner)
    assert ergebnis["status"] == "nicht_verfuegbar"
    assert ergebnis["grund"]  # Fehlergrund gespeichert
    assert ergebnis["quellen"] == []


def test_json_array_wird_zu_nicht_verfuegbar():
    # JSON-Array statt Objekt - keine .get() Methode.
    def oeffner(url, rumpf, timeout):
        return _FakeAntwort([{"url": "a"}])  # Array, nicht dict

    ergebnis = fetch_web("x", oeffner=oeffner)
    assert ergebnis["status"] == "nicht_verfuegbar"
    assert ergebnis["grund"]
    assert ergebnis["quellen"] == []


def test_quellen_ist_keine_liste_wird_als_leer_behandelt():
    # quellen kann eine Zahl, String oder null sein -- wird wie leeres array behandelt.
    antwort = {"frage": "x", "abgerufen_am": "2026-08-20",
               "quellen": "invalid", "hinweis": None}

    def oeffner(url, rumpf, timeout):
        return _FakeAntwort(antwort)

    ergebnis = fetch_web("x", oeffner=oeffner)
    assert ergebnis["status"] == "ok"
    assert ergebnis["quellen"] == []  # Leere Liste, kein Fehler
    assert ergebnis["hinweis"] is None


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


def test_ablehnung_deckt_alle_quantisierungs_geschwister():
    # Auf Platte liegen drei Schluessel fuer dasselbe Modell; die Liste nennt
    # nur `qwen3.8-27b`. Der Ablehnungsgrund betrifft aber ausgerechnet die
    # MLX-Variante -- die bei exakter Schluesselgleichheit ungebrandmarkt mit
    # Intelligence Index 52,0 durchrutschte, dem hoechsten Wert im Katalog.
    aa = {"status": "ok", "aa_stand": "2026-08-20", "quelle": "q",
          "modelle_roh": [_rec("qwen3-8-27b", "Qwen3.8 27B (Reasoning)", 52.0)]}
    web = {"status": "ok", "frage": "x", "abgerufen_am": "2026-08-20",
           "quellen": [], "hinweis": None}
    ablehnungen = {"qwen3.8-27b": {"grund": "MLX laesst reasoning_effort=none nicht zu",
                                   "abgelehnt_am": "2026-08-17"}}
    auf_platte = ["qwen3.8-27b", "qwen3.8-27b-mlx", "qwen3.8-27b-mtplx"]
    bericht = market_report(auf_platte, aa, web, ablehnungen=ablehnungen)
    for lm_key in auf_platte:
        eintrag = bericht["modelle"][lm_key]
        assert eintrag["abgelehnt"] is True, lm_key
        assert "reasoning_effort" in eintrag["ablehnungsgrund"], lm_key
        assert eintrag["abgelehnt_am"] == "2026-08-17", lm_key
        assert "abgelehnt am 2026-08-17" in eintrag["zeile"], lm_key


def test_ausfall_ohne_grundtext_ist_trotzdem_nicht_verfuegbar():
    # Der Status folgt den Quellen-Status, nicht dem Vorhandensein eines
    # Grundtexts. Frueher ergab eine Quelle mit `nicht_verfuegbar` ohne
    # `grund` den Gesamtstatus "ok" -- fail-open in der einen Funktion, die
    # fail-closed sein muss.
    aa = {"status": "nicht_verfuegbar", "aa_stand": None, "quelle": "q",
          "modelle_roh": []}
    web = {"status": "ok", "frage": "x", "abgerufen_am": "2026-08-20",
           "quellen": [], "hinweis": None}
    bericht = market_report(["gemma-4-31b-it-mlx"], aa, web)
    assert bericht["status"] == "nicht_verfuegbar"
    assert bericht["grund"] is None


def test_override_ins_leere_landet_in_nicht_gelistet_statt_zu_werfen():
    # match_slug gibt Override-Ziele zurueck, ohne sie gegen die gelieferten
    # Slugs zu pruefen. Liefert AA den Zielslug gerade nicht (Ausfall,
    # Umbenennung, Paginierungsabbruch), waere der direkte Zugriff ein
    # KeyError mitten im Sammellauf -- deshalb der zweite Teil der Bedingung.
    aa = {"status": "ok", "aa_stand": "2026-08-20", "quelle": "q",
          "modelle_roh": [_rec("gemma-4-31b", "Gemma 4 31B (Reasoning)", 29.69)]}
    web = {"status": "ok", "frage": "x", "abgerufen_am": "2026-08-20",
           "quellen": [], "hinweis": None}
    # Der Override zeigt auf einen Slug, den AA in dieser Antwort nicht fuehrt.
    bericht = market_report(["qwen/qwen3-coder-30b"], aa, web)
    assert bericht["nicht_gelistet"] == ["qwen/qwen3-coder-30b"]
    assert bericht["modelle"] == {}


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


def test_ablehnungsliste_als_json_objekt_wird_zu_leerer_liste(tmp_path):
    # Shape-guard: Datei enthaelt ein JSON-Objekt statt Array.
    p = tmp_path / "abgelehnt.json"
    p.write_text(json.dumps({"modell": "qwen3.8-27b", "grund": "g"}))
    geladen = lade_ablehnungen(p)
    assert geladen == {}


def test_ablehnungsliste_mit_nicht_dict_elementen_springt_ueber(tmp_path):
    # Shape-guard: Liste enthaelt Nicht-Dicts neben gueltigen Eintraegen.
    p = tmp_path / "abgelehnt.json"
    p.write_text(json.dumps([
        {"modell": "qwen3.8-27b", "grund": "g1"},
        "invalid string",
        42,
        {"modell": "gemma-4-31b", "grund": "g2"},
        None,
        {},  # dict aber kein modell-Feld
    ]))
    geladen = lade_ablehnungen(p)
    assert len(geladen) == 2
    assert geladen["qwen3.8-27b"]["grund"] == "g1"
    assert geladen["gemma-4-31b"]["grund"] == "g2"


def test_waehle_variante_bevorzugt_reasoning_bei_gleicher_slug_reasoning_zuerst():
    # Slug-Kollision: Reasoning zuerst, dann Non-Reasoning.
    # Reasoning muss gewinnen.
    records = [
        _rec("gemma-4-31b", "Gemma 4 31B (Reasoning)", 29.69),
        _rec("gemma-4-31b", "Gemma 4 31B (Non-reasoning)", 22.3),
    ]
    gewaehlt = waehle_variante(records)
    assert gewaehlt["gemma-4-31b"]["evaluations"][
        "artificial_analysis_intelligence_index"] == 29.69


def test_waehle_variante_bevorzugt_reasoning_bei_gleicher_slug_non_reasoning_zuerst():
    # Slug-Kollision: Non-Reasoning zuerst, dann Reasoning.
    # Reasoning muss gewinnen (nicht last-write-wins).
    records = [
        _rec("gemma-4-31b", "Gemma 4 31B (Non-reasoning)", 22.3),
        _rec("gemma-4-31b", "Gemma 4 31B (Reasoning)", 29.69),
    ]
    gewaehlt = waehle_variante(records)
    assert gewaehlt["gemma-4-31b"]["evaluations"][
        "artificial_analysis_intelligence_index"] == 29.69


def test_variante_erkennt_reasoning():
    # Plain "(Reasoning)" form.
    rec = {"name": "Gemma 4 31B (Reasoning)"}
    from advisor.market import _variante
    assert _variante(rec) == "Reasoning"


def test_variante_erkennt_reasoning_mit_effort():
    # "(Reasoning, Max Effort)" form.
    rec = {"name": "Qwen 3.6 35B (Reasoning, Max Effort)"}
    from advisor.market import _variante
    assert _variante(rec) == "Reasoning"


def test_variante_erkennt_adaptive_reasoning():
    # "(Adaptive Reasoning, Low Effort)" form.
    rec = {"name": "GPT-4 (Adaptive Reasoning, Low Effort)"}
    from advisor.market import _variante
    assert _variante(rec) == "Reasoning"


def test_variante_erkennt_non_reasoning():
    # Plain "(Non-reasoning)" form.
    rec = {"name": "Gemma 4 31B (Non-reasoning)"}
    from advisor.market import _variante
    assert _variante(rec) == "Non-Reasoning"


def test_variante_erkennt_non_reasoning_mit_effort():
    # "(Non-reasoning, High Effort)" form.
    rec = {"name": "Mistral 12B (Non-reasoning, High Effort)"}
    from advisor.market import _variante
    assert _variante(rec) == "Non-Reasoning"


def test_variante_substring_trap_non_reasoning_muss_vor_reasoning_geprueft_werden():
    # Substring trap: "non-reasoning" enthaelt "reasoning".
    # Wenn wir "reasoning" ZUERST pruefen, bekommen wir
    # "(Non-reasoning)" als "Reasoning" falsch erkannt.
    rec = {"name": "Model (Non-reasoning, Max Effort)"}
    from advisor.market import _variante
    assert _variante(rec) == "Non-Reasoning"  # NICHT "Reasoning"


def test_variante_unbekannt_ohne_parenthetical():
    # Name hat keine Variant-Angabe.
    rec = {"name": "Some Model"}
    from advisor.market import _variante
    assert _variante(rec) == "unbekannt"


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


def test_index_zahl_ohne_modellbezug_wird_gemeldet():
    # Frueher lieferte diese Sonde [] -- eine Zahl, die an keinem bekannten
    # Modell haengt, verschwand stillschweigend. Der Brief verlangt aber, dass
    # JEDE Zahl rueckverfolgbar ist. Also: Befund mit leerem Modellfeld, damit
    # ein Mensch draufschaut. (Geaendert am 20.08. nach dem Branch-Review; der
    # alte Test hielt das Durchwinken fest.)
    bad = verify_market_claims("openbiollm: Intelligence Index 5.0", _MARKT)
    assert len(bad) == 1
    assert bad[0]["modell"] == ""
    assert bad[0]["claimed"] == 5.0
    assert bad[0]["actual"] is None


def test_aa_slug_wird_als_modellname_erkannt():
    # Die aa_slug ist die verkürzete Form (z.B. "gemma-4-31b" statt "gemma-4-31b-it-mlx").
    # Ein Bericht kann sie verwenden -- aber das disabliert nicht alle Prüfungen.
    text = "gemma-4-31b: Intelligence Index 99.9"
    bad = verify_market_claims(text, _MARKT)
    assert len(bad) == 1
    assert bad[0]["claimed"] == 99.9
    assert bad[0]["actual"] == 29.69


def test_aa_slug_case_insensitive():
    # Slug-Matching ist case-insensitiv.
    text = "Gemma-4-31B: Intelligence Index 99.9"
    bad = verify_market_claims(text, _MARKT)
    assert len(bad) == 1


def test_aa_slug_mit_korrektem_wert_wird_akzeptiert():
    text = "gemma-4-31b: Intelligence Index 29.69"
    assert verify_market_claims(text, _MARKT) == []


def test_deutsches_verb_liegt_bei():
    # Deutsches Prosa: "Intelligence Index liegt bei 41.2"
    text = "gemma-4-31b-it-mlx: Intelligence Index liegt bei 41.2."
    bad = verify_market_claims(text, _MARKT)
    assert len(bad) == 1
    assert bad[0]["claimed"] == 41.2


def test_deutsches_verb_betraegt():
    text = "gemma-4-31b-it-mlx: Coding Index beträgt 55.0."
    bad = verify_market_claims(text, _MARKT)
    assert len(bad) == 1
    assert bad[0]["feld"] == "coding_index"


def test_deutsches_verb_ist():
    text = "gemma-4-31b-it-mlx Agentic Index ist 99.9."
    bad = verify_market_claims(text, _MARKT)
    assert len(bad) == 1


def test_zwei_indizes_in_einem_satz_mit_korrekten_werten():
    # Zwei Index-Claims im selben Satz dürfen sich die Zahlen nicht klauen.
    text = "qwen3.6-35b-a3b-mlx: Intelligence Index 32.13, Coding Index 41.88"
    assert verify_market_claims(text, _MARKT) == []


# --------------------------------------------------------------------------
# Die vier Sonden aus dem Branch-Review vom 20.08.
#
# Der alte Waechter suchte ein Index-Label und nahm die erste Zahl in den
# folgenden 40 Zeichen -- gegen JEDES im Text genannte Modell. Drei erfundene
# Zahlen kamen so durch, und ein korrekter Zwei-Modell-Vergleich erzeugte vier
# Fehlalarme. Weil der Brief verlangt, einen beanstandeten Text vor dem Senden
# zu korrigieren, haette der Waechter genau die Normalausgabe des Advisors
# blockiert.
# --------------------------------------------------------------------------

def test_sonde_1_zahl_vor_dem_label_wird_gefunden():
    # "41,2 Punkte im Intelligence Index" -- die Zahl steht VOR dem Label.
    text = "gemma-4-31b-it-mlx erreicht 41,2 Punkte im Intelligence Index."
    bad = verify_market_claims(text, _MARKT)
    assert len(bad) == 1
    assert bad[0]["modell"] == "gemma-4-31b-it-mlx"
    assert bad[0]["feld"] == "intelligence_index"
    assert bad[0]["claimed"] == 41.2
    assert bad[0]["actual"] == 29.69


def test_sonde_2_markdown_tabelle_ordnet_spaltenweise_zu():
    # Label in der Kopfzeile, Zahl in der Datenzeile darunter. Positionsnahes
    # Suchen pruefte 41.2 gegen coding_index und sah 55.0 nie.
    text = (
        "| Modell | Intelligence Index | Coding Index |\n"
        "|---|---|---|\n"
        "| gemma-4-31b-it-mlx | 41.2 | 55.0 |\n"
    )
    bad = verify_market_claims(text, _MARKT)
    nach_feld = {b["feld"]: b for b in bad}
    assert set(nach_feld) == {"intelligence_index", "coding_index"}
    assert nach_feld["intelligence_index"]["claimed"] == 41.2
    assert nach_feld["intelligence_index"]["actual"] == 29.69
    assert nach_feld["coding_index"]["claimed"] == 55.0
    assert nach_feld["coding_index"]["actual"] == 43.43
    assert all(b["modell"] == "gemma-4-31b-it-mlx" for b in bad)


def test_sonde_2b_korrekte_tabelle_ist_sauber():
    text = (
        "| Modell | Intelligence Index | Coding Index |\n"
        "|---|---|---|\n"
        "| gemma-4-31b-it-mlx | 29.69 | 43.43 |\n"
        "| qwen3.6-35b-a3b-mlx | 32.13 | 41.88 |\n"
    )
    assert verify_market_claims(text, _MARKT) == []


def test_sonde_3_der_vergleichswert_dahinter_ist_kein_befund():
    # Ersetzt `test_sonde_3_zweite_zahl_im_fenster_wird_mitgeprueft` (21.08.).
    #
    # Der alte Test verlangte, dass "(Vorwoche 27.1)" beanstandet wird, weil
    # `model_market` keine Historie fuehrt und die Zahl also nirgends steht.
    # Zu Ende gedacht heisst das: JEDE Vorwochenangabe ist ein Befund, und ein
    # Befund heisst laut Brief "nicht senden". Damit waere eine Berichtsform
    # verboten, die `evaluate_history.py` ausdruecklich verlangt -- der Bericht
    # soll mit "Was aus den letzten Befunden wurde" eroeffnen.
    #
    # Ein Waechter kann nur pruefen, wozu er Daten hat. Was er nicht pruefen
    # kann, darf er nicht verbieten. Geprueft wird die Behauptung ueber den
    # AKTUELLEN Wert, also die erste Zahl hinter dem Label.
    text = "gemma-4-31b-it-mlx: Intelligence Index 29.69 (Vorwoche 27.1)"
    assert verify_market_claims(text, _MARKT) == []

    # Die Behauptung selbst bleibt pruefbar -- der Vergleichswert deckt sie nicht.
    falsch = "gemma-4-31b-it-mlx: Intelligence Index 41.2 (Vorwoche 27.1)"
    bad = verify_market_claims(falsch, _MARKT)
    assert len(bad) == 1
    assert bad[0]["claimed"] == 41.2
    assert bad[0]["modell"] == "gemma-4-31b-it-mlx"


def test_sonde_4_korrekter_zwei_modell_vergleich_ist_sauber():
    # Der schlimmste Fall: vier Fehlalarme bei einem fehlerfreien Text, weil
    # jede Zahl gegen JEDES genannte Modell geprueft wurde. Ein Bericht ueber
    # n Modelle ergab rund n*(n-1) Scheinbefunde -- und Vergleiche sind die
    # Normalausgabe des Advisors.
    text = ("gemma-4-31b-it-mlx (Intelligence Index 29,69, Coding Index 43,43) "
            "liegt unter qwen3.6-35b-a3b-mlx (Intelligence Index 32,13, "
            "Coding Index 41,88).")
    assert verify_market_claims(text, _MARKT) == []


def test_jede_zahl_gehoert_dem_zuletzt_genannten_modell():
    # Bindung an das naechststehende vorangehende Modell: die zweite Zahl ist
    # falsch, die erste richtig -- nur ein Befund, und zwar beim richtigen Modell.
    text = ("gemma-4-31b-it-mlx: Intelligence Index 29,69. "
            "qwen3.6-35b-a3b-mlx: Intelligence Index 99,9.")
    bad = verify_market_claims(text, _MARKT)
    assert len(bad) == 1
    assert bad[0]["modell"] == "qwen3.6-35b-a3b-mlx"
    assert bad[0]["claimed"] == 99.9


# --------------------------------------------------------------------------
# Nicht gelistete Modelle (Review-Befund 5)
# --------------------------------------------------------------------------

_MARKT_MIT_LUECKE = {
    "modelle": dict(_MARKT["modelle"]),
    "nicht_gelistet": ["qwen/qwen3-coder-30b", "openbiollm-llama3-8b.gguf"],
}


def test_index_fuer_nicht_gelistetes_modell_ist_immer_falsch():
    # Ueber ein Modell ohne Marktdaten gibt es keine Qualitaetsaussage --
    # jede Indexzahl dazu ist erfunden. Frueher lieferte diese Sonde [],
    # weil der Waechter nur die gelisteten Modelle kannte.
    text = "qwen/qwen3-coder-30b bringt einen Intelligence Index von 61,4 mit."
    bad = verify_market_claims(text, _MARKT_MIT_LUECKE)
    assert len(bad) == 1
    assert bad[0]["modell"] == "qwen/qwen3-coder-30b"
    assert bad[0]["feld"] == "intelligence_index"
    assert bad[0]["claimed"] == 61.4
    assert bad[0]["actual"] is None


def test_nicht_gelistetes_modell_ohne_zahl_ist_kein_befund():
    # Es zu erwaehnen ist erlaubt -- nur eine Kennzahl dazu nicht.
    text = ("openbiollm-llama3-8b.gguf steht bei Artificial Analysis nicht "
            "im Katalog; dazu gibt es keine Qualitaetsaussage.")
    assert verify_market_claims(text, _MARKT_MIT_LUECKE) == []


def test_feld_ohne_wert_kann_nicht_zitiert_werden():
    # Ein Index, der im JSON `null` ist, hat keine Zahl. Wer trotzdem eine
    # nennt, hat sie erfunden.
    markt = {"modelle": {"kimi-k3": {"aa_slug": "kimi-k3",
                                     "intelligence_index": None}}}
    bad = verify_market_claims("kimi-k3: Intelligence Index 40,0", markt)
    assert len(bad) == 1
    assert bad[0]["actual"] is None


# --------------------------------------------------------------------------
# markt_zeile: die fehlende Haelfte des Waechters (Review-Befund 1a)
# --------------------------------------------------------------------------

from advisor.market import markt_zeile


def test_markt_zeile_traegt_zahlen_variante_und_quelle():
    zeile = markt_zeile("gemma-4-31b-it-mlx",
                        {"aa_slug": "gemma-4-31b", "variante": "Reasoning",
                         "intelligence_index": 29.69, "coding_index": 43.43,
                         "agentic_index": 14.38},
                        aa_stand="2026-08-20")
    assert zeile.startswith("gemma-4-31b-it-mlx")
    assert "Reasoning" in zeile
    assert "Intelligence Index 29,69" in zeile
    assert "Coding Index 43,43" in zeile
    assert "Agentic Index 14,38" in zeile
    assert "Quelle: Artificial Analysis, Stand 2026-08-20" in zeile


def test_markt_zeile_kommt_durch_den_eigenen_waechter():
    # Das ist der Sinn der Uebung: der Satz, den der Agent einfuegt, muss die
    # Pruefung bestehen, die derselbe Text danach durchlaeuft. evidence.py
    # traegt beide Haelften seit dem 31.07.; market.py hatte nur die Pruefung.
    eintrag = _MARKT["modelle"]["gemma-4-31b-it-mlx"]
    zeile = markt_zeile("gemma-4-31b-it-mlx", eintrag, aa_stand="2026-08-20")
    assert verify_market_claims(zeile, _MARKT) == []


def test_markt_zeile_erfindet_keine_zahl_fuer_fehlende_felder():
    zeile = markt_zeile("kimi-k3", {"aa_slug": "kimi-k3", "variante": "unbekannt",
                                    "intelligence_index": 40.0,
                                    "coding_index": None,
                                    "agentic_index": None},
                        aa_stand=None)
    assert "Coding Index nicht verfuegbar" in zeile
    assert "Stand unbekannt" in zeile
    markt = {"modelle": {"kimi-k3": {"aa_slug": "kimi-k3",
                                     "intelligence_index": 40.0,
                                     "coding_index": None,
                                     "agentic_index": None}}}
    assert verify_market_claims(zeile, markt) == []


def test_markt_zeile_nennt_die_ablehnung_mit():
    zeile = markt_zeile("qwen3.8-27b-mlx",
                        {"aa_slug": "qwen3-8-27b", "variante": "Reasoning",
                         "intelligence_index": 52.0, "coding_index": None,
                         "agentic_index": None, "abgelehnt": True,
                         "abgelehnt_am": "2026-08-17",
                         "ablehnungsgrund": "MLX laesst reasoning_effort=none nicht zu"},
                        aa_stand="2026-08-20")
    assert "abgelehnt am 2026-08-17" in zeile
    assert "reasoning_effort" in zeile


def test_die_abgelehnt_zeile_stolpert_nicht_ueber_zahlen_im_grund():
    # Der echte Ablehnungsgrund aus state-vorlagen/ traegt Zahlen
    # ("28,3 s / 2.236 Token"). Sie duerfen keinem Index-Label zufallen --
    # sonst beanstandet der Waechter die Zeile, die er selbst gerendert hat.
    markt = {"modelle": {"qwen3.8-27b-mlx": {
        "aa_slug": "qwen3-8-27b", "variante": "Reasoning",
        "intelligence_index": 52.0, "coding_index": None, "agentic_index": None,
        "abgelehnt": True, "abgelehnt_am": "2026-08-17",
        "ablehnungsgrund": ("MLX-Variante laesst reasoning_effort=none nicht zu; "
                            "der Denkmodus laeuft davon (28,3 s / 2.236 Token). "
                            "Nur auf der RTX mit abgeschaltetem Denken brauchbar.")}}}
    zeile = markt_zeile("qwen3.8-27b-mlx", markt["modelle"]["qwen3.8-27b-mlx"],
                        aa_stand="2026-08-20")
    assert verify_market_claims(zeile, markt) == []


def test_bericht_haengt_die_fertige_zeile_an_jeden_eintrag():
    # Wie `evidence` je Agent in collect_ist_zustand.py: der Agent findet den
    # Satz fertig vor und muss ihn nicht formulieren.
    aa = {"status": "ok", "aa_stand": "2026-08-20", "quelle": "Artificial Analysis (Free API)",
          "modelle_roh": [_rec("gemma-4-31b", "Gemma 4 31B (Reasoning)", 29.69)]}
    web = {"status": "ok", "frage": "x", "abgerufen_am": "2026-08-20",
           "quellen": [], "hinweis": None}
    bericht = market_report(["gemma-4-31b-it-mlx"], aa, web)
    zeile = bericht["modelle"]["gemma-4-31b-it-mlx"]["zeile"]
    assert "Intelligence Index 29,69" in zeile
    assert "Stand 2026-08-20" in zeile
    assert verify_market_claims(zeile, bericht) == []


# --- Overrides ueber die Normalform (21.08.) -------------------------------
# Der erste echte AA-Abruf zeigte: die Override-Tabelle traf nur den rohen
# Schluessel. `mistral-small-3.2-24b-instruct-2506` stand drin, aber die real
# geladene `-mlx`-Variante lief daran vorbei und landete in `nicht_gelistet`.
# Dieselbe Luecke hatte die Ablehnungsliste schon einmal (qwen3.8-27b-mlx).

def test_override_greift_auch_fuer_die_quantisierungs_geschwister():
    slugs = {"mistral-small-3-2"}
    for variante in ("mistral-small-3.2-24b-instruct-2506",
                     "mistral-small-3.2-24b-instruct-2506-mlx",
                     "mistral-small-3.2-24b-instruct-2506@q4_k_m"):
        assert match_slug(variante, slugs) == "mistral-small-3-2", variante


def test_override_auf_none_gilt_auch_fuer_die_geschwister():
    # `openbiollm-llama3-8b.gguf` ist bewusst nicht gelistet -- eine
    # hypothetische `-mlx`-Variante darf nicht ploetzlich zu suchen anfangen.
    assert match_slug("openbiollm-llama3-8b.gguf", set()) is None
    assert match_slug("openbiollm-llama3-8b-mlx", set()) is None


def test_der_rohe_schluessel_hat_weiter_vorrang_vor_der_normalform():
    # Ein Eintrag auf den exakten Schluessel muss einen Normalform-Eintrag
    # ueberstimmen koennen -- sonst laesst sich eine einzelne Variante nicht
    # gezielt anders behandeln.
    overrides = {"foo-bar-mlx": "genau-diese", "foo-bar": "die-allgemeine"}
    assert match_slug("foo-bar-mlx", {"genau-diese"}, overrides) == "genau-diese"
    assert match_slug("foo-bar-qat", {"die-allgemeine"}, overrides) == "die-allgemeine"


def test_ohne_passenden_override_bleibt_es_beim_exakten_treffer():
    # Die Normalform-Erweiterung darf kein Fuzzy-Matching durch die Hintertuer
    # sein: ohne Eintrag entscheidet weiter nur die Slug-Menge.
    assert match_slug("voellig-unbekannt-mlx", {"etwas-anderes"}, {}) is None


# --- Nur die erste Zahl ist die Behauptung (21.08.) -------------------------
# Der Vorwaertspfad nahm ALLE Zahlen im Fenster. Was nach der ersten kommt,
# ist im Bericht aber praktisch immer Kontext: Kontextgroesse, RAM, Skala,
# Abstand zum Nachbarn, Vorwochenwert. Sechs natuerliche KORREKTE Saetze
# loesten damit Fehlalarm aus -- und ein Befund heisst laut Brief "nicht
# senden". Ein Waechter, der richtige Berichte blockiert, kostet genau die
# Iterationen, die dieser Umbau sparen sollte.

def _markt_gemma():
    return {"modelle": {"gemma-4-31b-it-mlx": {
        "aa_slug": "gemma-4-31b", "intelligence_index": 29.7,
        "coding_index": 43.4, "agentic_index": 14.4}},
        "nicht_gelistet": []}


def test_kontextzahlen_hinter_der_kennzahl_sind_kein_befund():
    m = _markt_gemma()
    for satz in [
        "gemma-4-31b-it-mlx: Intelligence Index 29,7 bei 262.144 Token Kontext.",
        "gemma-4-31b-it-mlx: Intelligence Index 29,7, belegt 18,5 GB.",
        "gemma-4-31b-it-mlx: Intelligence Index 29,7. Er kostet 18,5 GB.",
        "gemma-4-31b-it-mlx: Intelligence Index 29,7 (von 100).",
        "gemma-4-31b-it-mlx: Intelligence Index 29,7, also 2,44 unter qwen.",
        "gemma-4-31b-it-mlx: Intelligence Index 29,7 (Vorwoche 27,1).",
    ]:
        assert verify_market_claims(satz, m) == [], satz


def test_die_erste_zahl_wird_weiterhin_geprueft():
    # Die Verengung darf den Waechter nicht entschaerfen: die Behauptung
    # selbst bleibt pruefbar, auch mit Kontextzahlen dahinter.
    m = _markt_gemma()
    b = verify_market_claims(
        "gemma-4-31b-it-mlx: Intelligence Index 41,2 bei 262.144 Token.", m)
    assert len(b) == 1 and b[0]["claimed"] == 41.2 and b[0]["actual"] == 29.7


def test_ein_zweites_label_behaelt_seine_eigene_zahl():
    m = _markt_gemma()
    assert verify_market_claims(
        "gemma-4-31b-it-mlx: Intelligence Index 29,7, Coding Index 43,4.", m) == []
    b = verify_market_claims(
        "gemma-4-31b-it-mlx: Intelligence Index 29,7, Coding Index 99,9.", m)
    assert len(b) == 1 and b[0]["feld"] == "coding_index"


def test_satzgrenze_beendet_das_fenster():
    # Ohne Satzgrenze zieht ein Label ohne eigene Zahl die Zahl des naechsten
    # Satzes an sich.
    m = _markt_gemma()
    assert verify_market_claims(
        "gemma-4-31b-it-mlx: Der Intelligence Index ist unbekannt. "
        "Der Nachbar hat 55,0.", m) == []
