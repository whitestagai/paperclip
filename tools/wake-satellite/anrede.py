# tools/wake-satellite/anrede.py
"""Erkennt, ob eine Äußerung NUR aus der Anrede bestand.

Sagt Walter „Hey Jarvis", setzt ab und stellt erst danach seine Frage, endet
die Aufnahme in der Pause — beim Sprachmodell kommt dann bloss die Anrede an,
und es antwortet höflich „Hallo Walter". Der Satellit nutzt diese Erkennung,
um in dem Fall gar nicht erst zu fragen, sondern kurz zu quittieren und weiter
zuzuhören. Reine Textlogik, stdlib only."""
import re

# Whisper schreibt den Namen je nach Aussprache unterschiedlich; alle Varianten
# hier stammen aus echten Transkripten des Live-Logs bzw. sind naheliegende
# Nachbarn davon.
NAMEN = ("jarvis", "javis", "jervis", "jarves", "jarvis's")

# Was vor dem Namen stehen darf, ohne dass es eine inhaltliche Äußerung wird.
GRUESSE = ("hey", "hi", "hallo", "he", "ey", "na", "ok", "okay", "guten", "tag")

_NUR_BUCHSTABEN = re.compile(r"[^a-zäöüß ]+")


def ist_nur_anrede(text):
    """True, wenn `text` ausschliesslich die Anrede enthält.

    Leerer Text ist KEINE Anrede — „nichts verstanden" ist etwas anderes als
    „angesprochen", und der Aufrufer behandelt es getrennt.
    """
    woerter = _NUR_BUCHSTABEN.sub(" ", (text or "").lower()).split()
    if not woerter:
        return False
    if woerter[-1] not in NAMEN:
        return False
    return all(wort in GRUESSE for wort in woerter[:-1])
