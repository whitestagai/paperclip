import pytest

import anrede


# Alle Wortlaute hier stammen aus echten Transkripten des Live-Logs: so
# unterschiedlich schreibt Whisper dasselbe gesprochene „Hey Jarvis".
@pytest.mark.parametrize("text", [
    "Hey Jarvis.",
    "Hey, Jarvis.",
    "Hey, Javis.",          # 17.08.
    "Nagehi Jarvis.",       # 17.08.
    "Chavez.",              # 17.08. — keine Silbe stimmt mehr
    "Jarvis",
    "Hallo Jarvis",
    "  hey jarvis  ",
    "* Musik *",            # Fehl-Wake durch Geräusch
])
def test_kurzes_transkript_ist_nur_das_wakeword(text):
    assert anrede.ist_nur_wakeword(text) is True


def test_leeres_transkript_zaehlt_als_wakeword():
    # Aufgenommen, aber nichts verstanden: auch dann hat Walter nur gerufen.
    assert anrede.ist_nur_wakeword("") is True
    assert anrede.ist_nur_wakeword(None) is True


# Eine echte Äußerung bringt Wörter mit, die über die Anrede hinausgehen.
@pytest.mark.parametrize("text", [
    "Hey Jarvis, wie spät ist es?",
    "Hey Jarvis, wie wird das Wetter?",
    "Jarvis, leg einen Task an",
    "Wie spät ist es?",
    "die George-Brüder beziehen.",
    "Filmsequenz, ein 3D-Modell eines Windkrafts.",
])
def test_echte_aeußerung_ist_kein_bloßes_wakeword(text):
    assert anrede.ist_nur_wakeword(text) is False


def test_grenze_liegt_bei_zwei_woertern():
    assert anrede.ist_nur_wakeword("eins zwei") is True
    assert anrede.ist_nur_wakeword("eins zwei drei") is False


def test_satzzeichen_zaehlen_nicht_als_wort():
    assert anrede.ist_nur_wakeword("Hey, Jarvis!!! ...") is True
