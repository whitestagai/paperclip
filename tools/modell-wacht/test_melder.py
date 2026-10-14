"""Inhalt der Alarm-Mail. Rein — es wird nichts verschickt."""

from melder import alarm_mail, entwarnung_mail
from pruefung import Befund


def _b(art, schwere, text):
    return Befund(art, schwere, "q", "f", None, text)


def test_alarm_mail_nennt_harte_befunde_und_zaehlt_niedrige_nur():
    """Die Mail vom 10.10. hätte 30 Zeilen «nicht geladen» enthalten — der
    Geräteausfall wäre darin untergegangen. Niedrige Befunde stehen im Issue."""
    befunde = [
        _b("geraet_getrennt", "hoch", "Gerät «RTX Pro 6000» ist nicht verbunden."),
        _b("nicht_geladen", "niedrig", "nutzt «x», das gerade nicht geladen ist."),
        _b("nicht_geladen", "niedrig", "nutzt «y», das gerade nicht geladen ist."),
    ]
    betreff, text, html = alarm_mail(befunde, "Kopfzeile.", "WHI-1")
    assert "RTX Pro 6000" in betreff
    assert "RTX Pro 6000" in text and "RTX Pro 6000" in html
    assert "nicht geladen ist" not in text
    assert "2 niedrige" in text
    assert "WHI-1" in text


def test_alarm_mail_maskiert_html():
    befunde = [_b("unbekannt", "hoch", "zeigt auf <script>")]
    _, _, html = alarm_mail(befunde, "K", None)
    assert "<script>" not in html


def test_entwarnung_mail_sagt_dass_es_vorbei_ist():
    betreff, text, _ = entwarnung_mail("Kopfzeile.")
    assert "grün" in betreff
    assert "Kopfzeile." in text


def test_betreff_schneidet_modellnamen_mit_punkt_nicht_ab():
    befunde = [_b("modell_fehlt", "hoch", "«qwen3.6-35b-win» ist auf «WHITESTAG-AI» nicht geladen. Rest.")]
    betreff, _, _ = alarm_mail(befunde, "K", None)
    assert "qwen3.6-35b-win" in betreff
    assert "Rest" not in betreff


def test_geraeteausfall_steht_im_betreff_und_folgezeilen_werden_gebuendelt():
    """14.10.2026: WHITESTAG-AI fiel aus. Betreff der Mail war «Clara Sound/
    Akquise & Booking … zeigt auf «gemma-4-31b-win» (+48 weitere)» — der
    Geräteausfall stand als letzte von 49 Zeilen. Die 48 «unbekannt»-Zeilen
    waren nur seine Folge: die Fallback-IDs liegen auf dem fehlenden Gerät."""
    from pruefung import Befund as B
    befunde = [
        B("unbekannt", "hoch", "Agent {}".format(i), "fallbackModel", "gemma-4-31b-win",
          "Agent {} zeigt auf «gemma-4-31b-win» — ID unbekannt.".format(i))
        for i in range(30)
    ] + [
        B("unbekannt", "hoch", "PII-Proxy", "CLASSIFIER_MODEL", "anderes-modell",
          "PII-Proxy zeigt auf «anderes-modell» — ID unbekannt."),
        B("geraet_getrennt", "hoch", "LM Link «WHITESTAG-AI»", "status", None,
          "Gerät «WHITESTAG-AI» ist nicht verbunden. Betroffen: gemma-4-31b-win, qwen3.6-35b-win."),
    ]
    betreff, text, _ = alarm_mail(befunde, "K", None, geraete_modelle={"gemma-4-31b-win", "qwen3.6-35b-win"})
    assert "WHITESTAG-AI" in betreff
    assert text.index("WHITESTAG-AI") < text.index("anderes-modell")
    assert "Agent 7 zeigt" not in text, "Folgezeilen des Geräteausfalls einzeln aufgezählt"
    assert "30 Konfigurationen" in text
    assert "anderes-modell" in text, "unabhängiger Befund darf nicht verschwinden"


def test_betroffene_modelle_aus_getrenntem_geraet_und_fehlenden_modellen():
    """Beide Formen vom 14.10.: erst war der Node weg (getrennt), dann kam er
    mit falschen Kennungen zurück (verbunden, aber Soll-Modelle fehlen)."""
    from melder import betroffene_modelle
    from pruefung import Befund as B
    soll = {"a-win": {"geraet": "WHITESTAG-AI"}, "b-win": {"geraet": "WHITESTAG-AI"},
            "rtx-modell": {"geraet": "RTX Pro 6000"}}
    getrennt = [B("geraet_getrennt", "hoch", "LM Link «WHITESTAG-AI»", "status", None, "t")]
    assert betroffene_modelle(getrennt, soll) == {"a-win", "b-win"}
    fehlt = [B("modell_fehlt", "hoch", "LM Studio «RTX Pro 6000»", "geladen", "rtx-modell", "t")]
    assert betroffene_modelle(fehlt, soll) == {"rtx-modell"}
