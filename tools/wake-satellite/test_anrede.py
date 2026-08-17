import pytest

import anrede


# Wortlaute, die Whisper im Live-Log wirklich geliefert hat, wenn Walter nur
# das Wake-Wort gesagt und dann auf eine Reaktion gewartet hat.
@pytest.mark.parametrize("text", [
    "Hey Jarvis.",
    "Hey, Jarvis.",
    "Hey, Javis.",          # Live-Befund 17.08.
    "Hey Jervis",
    "Jarvis",
    "Jarvis?",
    "Hallo Jarvis",
    "  hey jarvis  ",
])
def test_bloße_anrede_wird_erkannt(text):
    assert anrede.ist_nur_anrede(text) is True


# Alles, was über die Anrede hinausgeht, ist eine echte Äußerung und muss ans
# Sprachmodell — auch wenn die Anrede vorne dransteht.
@pytest.mark.parametrize("text", [
    "Hey Jarvis, wie spät ist es?",
    "Jarvis, leg einen Task an",
    "Wie wird das Wetter?",
    "Hey Jarvis, Wetter",
])
def test_anrede_mit_inhalt_ist_keine_bloße_anrede(text):
    assert anrede.ist_nur_anrede(text) is False


def test_leerer_text_ist_keine_anrede():
    # Leer heißt "nichts verstanden", nicht "angesprochen" — der Aufrufer
    # behandelt das getrennt.
    assert anrede.ist_nur_anrede("") is False
    assert anrede.ist_nur_anrede(None) is False


def test_fremdes_wort_ohne_namen_ist_keine_anrede():
    assert anrede.ist_nur_anrede("Hey") is False
    assert anrede.ist_nur_anrede("Hallo") is False
