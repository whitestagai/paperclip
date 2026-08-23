"""Die Ernstfälle. Jeder Test hier ist ein Vorfall, der schon passiert ist."""

from pruefung import Bestand, Referenz, bewerte


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
