"""Die Ernstfälle. Jeder Test hier ist ein Vorfall, der schon passiert ist."""

from pruefung import (
    Befund,
    Bestand,
    Referenz,
    bewerte,
    bewerte_drift,
    bewerte_laufzeit,
    meldung_faellig,
    signatur,
)


SOLL = {
    "abiray/qwen3.6-35b-a3b": {"contextLength": 98304, "parallel": 5},
    "gemma4-31b-it": {"contextLength": 98304, "parallel": 8},
}


def _bestand(vorhanden=("gemma4-31b-it", "abiray/qwen3.6-35b-a3b"), geladen=("gemma4-31b-it",)):
    return Bestand(vorhanden=frozenset(vorhanden), geladen=frozenset(geladen))


def test_bekanntes_geladenes_modell_ist_kein_befund():
    befunde = bewerte([Referenz("Agent CTO", "model", "gemma4-31b-it")], _bestand(), [])
    assert befunde == []


def test_tote_modell_id_ist_ein_harter_befund():
    """22.08.: Der RTX-Umzug machte `qwen3.6-35b-a3b-mlx` ungültig. Zwei
    Tagger-Templates und zwei Link-Detektor-Datenbanken zeigten weiter darauf;
    der Detektor lief damit 24/7 ins Leere — 233 Fehler an einem Tag."""
    befunde = bewerte(
        [Referenz("Link-Detektor link_detektor", "llm_model", "qwen3.6-35b-a3b-mlx")],
        _bestand(),
        [],
    )
    assert len(befunde) == 1
    assert befunde[0].art == "unbekannt"
    assert befunde[0].schwere == "hoch"
    assert "qwen3.6-35b-a3b-mlx" in befunde[0].text


def test_heruntergeladen_aber_nicht_geladen_ist_nur_ein_hinweis():
    """Kein Fehler — LM Studio lädt bei Bedarf nach. Kostet aber ~22 s
    Kaltstart, was für den Wake-Satelliten spürbar ist."""
    befunde = bewerte(
        [Referenz("Wake-Satellit", "CHAT_MODEL", "abiray/qwen3.6-35b-a3b")], _bestand(), []
    )
    assert len(befunde) == 1
    assert befunde[0].art == "nicht_geladen"
    assert befunde[0].schwere == "niedrig"


def test_unlesbare_quelle_ist_selbst_ein_befund():
    """Fail-closed: Wer nicht nachsehen kann, gibt keine Entwarnung."""
    befunde = bewerte([], _bestand(), ["n8n-Datenbank: database is locked"])
    assert len(befunde) == 1
    assert befunde[0].art == "quelle_unlesbar"
    assert befunde[0].schwere == "hoch"


def test_leerer_bestand_meldet_und_prueft_nicht_gegen_nichts():
    """Ist LM Studio unerreichbar, wäre jede Referenz plötzlich `unbekannt` —
    das wären 40 Fehlalarme statt einem Befund."""
    befunde = bewerte(
        [Referenz("Agent CTO", "model", "gemma4-31b-it")],
        Bestand(vorhanden=frozenset(), geladen=frozenset()),
        [],
    )
    assert len(befunde) == 1
    assert befunde[0].art == "quelle_unlesbar"


def test_cloud_modelle_werden_nicht_gegen_lm_studio_geprueft():
    """`claude-sonnet-5` läuft über die Anthropic-API und taucht in
    `/v1/models` niemals auf."""
    befunde = bewerte([Referenz("Agent VP Engineering", "model", "claude-sonnet-5")], _bestand(), [])
    assert befunde == []


def test_mehrere_quellen_derselben_toten_id_werden_einzeln_gemeldet():
    """Beim Vorfall am 22.08. steckte dieselbe ID in vier Quellen. Wer
    dedupliziert, repariert eine und hält das Problem für gelöst."""
    tot = "qwen3.6-35b-a3b-mlx"
    befunde = bewerte(
        [
            Referenz("Tagger WHITESTAG", "llm.modell", tot),
            Referenz("Tagger Clara", "llm.modell", tot),
            Referenz("Link-Detektor link_detektor", "llm_model", tot),
            Referenz("Link-Detektor link_detektor_clara", "llm_model", tot),
        ],
        _bestand(),
        [],
    )
    assert len(befunde) == 4
    assert {b.quelle for b in befunde} == {
        "Tagger WHITESTAG",
        "Tagger Clara",
        "Link-Detektor link_detektor",
        "Link-Detektor link_detektor_clara",
    }


# ---------------------------------------------------- Laufzeit (Fenster)


def test_zu_kleines_fenster_ist_ein_harter_befund():
    """26.08.: Beide RTX-Modelle standen von 10:00 bis 12:11 auf 65.536 statt
    98.304. Der lmstudio-Adapter kürzt unterhalb von
    BUDGET_LOOKUP_THRESHOLD_TOKENS = 32.000 gar nicht und schätzt Token mit
    chars/4 — bei JSON ein Faktor 2,19 zu niedrig. Folge: 109 Überläufe und
    ein Einbruch der Erfolgsquote auf 11 %."""
    befunde = bewerte_laufzeit({"gemma4-31b-it": (65536, 12)}, SOLL)
    assert len(befunde) == 1
    assert befunde[0].art == "fenster_zu_klein"
    assert befunde[0].schwere == "hoch"
    assert "65536" in befunde[0].text and "98304" in befunde[0].text


def test_groesseres_fenster_als_gefordert_ist_nur_ein_hinweis():
    """Kostet Speicher, verursacht aber keine Überläufe."""
    befunde = bewerte_laufzeit({"gemma4-31b-it": (131072, 8)}, SOLL)
    assert len(befunde) == 1
    assert befunde[0].schwere == "niedrig"


def test_abweichende_slotzahl_allein_ist_nur_ein_hinweis():
    """Slots bestimmen den Durchsatz, nicht die Korrektheit."""
    befunde = bewerte_laufzeit({"gemma4-31b-it": (98304, 12)}, SOLL)
    assert len(befunde) == 1
    assert befunde[0].art == "slots_abweichend"
    assert befunde[0].schwere == "niedrig"


def test_soll_erfuellt_ist_kein_befund():
    befunde = bewerte_laufzeit(
        {"gemma4-31b-it": (98304, 8), "abiray/qwen3.6-35b-a3b": (98304, 5)}, SOLL
    )
    assert befunde == []


def test_modell_ohne_sollwert_wird_nicht_bewertet():
    """openbiollm und die Einbettungsmodelle haben bewusst kleine Fenster."""
    assert bewerte_laufzeit({"text-embedding-bge-m3": (8192, None)}, SOLL) == []


def test_nicht_geladenes_sollmodell_erzeugt_hier_keine_dublette():
    """Dass ein Modell fehlt, meldet bereits die Referenzprüfung. Zweimal
    gemeldet verdoppelt jeden Bericht."""
    assert bewerte_laufzeit({}, SOLL) == []


# ------------------------------------------- Datei gegen laufenden Dienst


def test_drift_zwischen_datei_und_dienst_ist_ein_harter_befund():
    """26.08.: Die plist stand seit dem Vortag auf «google/gemma-4-12b», der
    laufende Job trug weiter «google/gemma-4-12b-qat». launchd liest eine
    geänderte plist nicht nach; `kickstart -k` startet nur den Prozess neu.
    822 Klassifikator-Aufrufe scheiterten an einem einzigen Tag."""
    befunde = bewerte_drift(
        [Referenz("PII-Proxy (Datei)", "CLASSIFIER_MODEL", "google/gemma-4-12b")],
        [Referenz("PII-Proxy (Dienst)", "CLASSIFIER_MODEL", "google/gemma-4-12b-qat")],
    )
    assert len(befunde) == 1
    assert befunde[0].art == "konfig_drift"
    assert befunde[0].schwere == "hoch"
    assert "google/gemma-4-12b-qat" in befunde[0].text


def test_gleichstand_zwischen_datei_und_dienst_ist_kein_befund():
    gleich = [Referenz("PII-Proxy (Datei)", "CLASSIFIER_MODEL", "google/gemma-4-12b")]
    dienst = [Referenz("PII-Proxy (Dienst)", "CLASSIFIER_MODEL", "google/gemma-4-12b")]
    assert bewerte_drift(gleich, dienst) == []


def test_entladener_dienst_erzeugt_keinen_drift_befund():
    """Läuft der Job gar nicht, ist die Umgebung leer. Das als Drift zu melden
    wäre irreführend — die Nichtverfügbarkeit ist eine andere Meldung."""
    datei = [Referenz("PII-Proxy (Datei)", "CLASSIFIER_MODEL", "google/gemma-4-12b")]
    assert bewerte_drift(datei, []) == []


# ------------------------------------------------- Entprellung der Meldung


def _hoch(art="fenster_zu_klein", quelle="LM Studio «gemma4-31b-it»"):
    return Befund(art=art, schwere="hoch", quelle=quelle, feld="contextLength",
                  modell="gemma4-31b-it", text="egal")


def test_erster_befund_wird_gemeldet():
    assert meldung_faellig(signatur([_hoch()]), []) is True


def test_derselbe_befund_wird_nicht_erneut_gemeldet():
    """Der Wächter läuft alle 30 Minuten. Ein Zustand, der zwei Stunden
    anhält, darf nicht vier Issues erzeugen — sonst schaut niemand mehr hin."""
    sig = signatur([_hoch()])
    assert meldung_faellig(sig, sig) is False


def test_zusaetzlicher_befund_wird_gemeldet():
    alt = signatur([_hoch()])
    neu = signatur([_hoch(), _hoch(quelle="LM Studio «abiray/qwen3.6-35b-a3b»")])
    assert meldung_faellig(neu, alt) is True


def test_kein_befund_meldet_nicht():
    assert meldung_faellig(signatur([]), signatur([_hoch()])) is False


def test_wiederauftreten_nach_entwarnung_wird_erneut_gemeldet():
    """26.08.: Der Zustand kippte um 10:00 und war um 12:11 wieder in Ordnung.
    Kippt er erneut, ist das eine neue Meldung wert — sonst bliebe ein
    flappender Fehler nach dem ersten Mal für immer stumm."""
    sig = signatur([_hoch()])
    assert meldung_faellig(sig, []) is True


def test_niedrige_befunde_loesen_keine_meldung_aus():
    """Ein zu grosses Fenster oder eine abweichende Slotzahl gehören in den
    Bericht, sind aber kein Grund, jemanden zu wecken."""
    niedrig = Befund(art="slots_abweichend", schwere="niedrig", quelle="q",
                     feld="parallel", modell="m", text="egal")
    assert signatur([niedrig]) == []
    assert meldung_faellig(signatur([niedrig]), []) is False


def test_signatur_ignoriert_schwankende_zahlen_im_text():
    """Fenster 65.536 und 32.768 sind derselbe Fehler an derselben Stelle.
    Wer den Text mit in die Signatur nimmt, meldet ihn bei jedem Wackeln neu."""
    a = Befund(art="fenster_zu_klein", schwere="hoch", quelle="LM Studio «x»",
               feld="contextLength", modell="x", text="Fenster 65536 statt 98304")
    b = a._replace(text="Fenster 32768 statt 98304")
    assert signatur([a]) == signatur([b])


def test_befunde_stehen_schwerste_zuerst():
    befunde = bewerte(
        [
            Referenz("Wake-Satellit", "CHAT_MODEL", "abiray/qwen3.6-35b-a3b"),
            Referenz("Tagger WHITESTAG", "llm.modell", "gibts-nicht"),
        ],
        _bestand(),
        [],
    )
    assert [b.schwere for b in befunde] == ["hoch", "niedrig"]
