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
