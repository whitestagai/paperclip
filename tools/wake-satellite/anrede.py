# tools/wake-satellite/anrede.py
"""Kam nach dem Wake-Wort nur die Anrede — oder schon eine Frage?

Sagt Walter „Hey Jarvis", setzt ab und stellt erst danach seine Frage, endet
die Aufnahme in der Pause; beim Sprachmodell käme dann bloss die Anrede an und
es antwortete höflich „Hallo Walter". Der Satellit erkennt diesen Fall, um
statt dessen kurz zu quittieren und weiter zuzuhören.

Entscheidend ist die ANZAHL der Wörter, nicht ihr Wortlaut. Der Grund ist eine
Eigenschaft der ersten Runde: dort steckt das Wake-Wort beweisbar mit im Audio
— sonst hätte der Detektor nicht ausgelöst. Bleiben davon höchstens zwei Wörter
übrig, war ausser der Anrede nichts da. Auf den Wortlaut ist dagegen kein
Verlass: dasselbe gesprochene „Hey Jarvis" kam im Log als „Hey Jarvis.", „Hey,
Javis.", „Nagehi Jarvis." und „Chavez." an. Gemessen (17.08.) liegt „Chavez"
in der Zeichenähnlichkeit zu „jarvis" bei 0,43 und damit UNTER echten Fragen
wie „Hey Jarvis, wie wird das Wetter?" (0,53) — eine Ähnlichkeitsschwelle kann
die beiden Fälle also gar nicht trennen.

Die Fehlerkosten sind bewusst asymmetrisch: eine fälschlich als Anrede gelesene
Kurzfrage kostet ein „Ja?" und eine Wiederholung; eine fälschlich beantwortete
Anrede kostet eine Fehlantwort und die halbe Kette. Deshalb im Zweifel
quittieren. stdlib only."""
import re

# Bis hierher gilt eine Äusserung als „nur gerufen". „Hey Jarvis" sind zwei
# Wörter; drei sind schon Inhalt („Hey Jarvis, Wetter").
MAX_WOERTER = 2

_NUR_BUCHSTABEN = re.compile(r"[^a-zäöüß ]+")


def woerter(text):
    """Zerlegt in reine Buchstabenwörter; Satzzeichen zählen nicht mit."""
    return _NUR_BUCHSTABEN.sub(" ", (text or "").lower()).split()


def ist_nur_wakeword(text):
    """True, wenn in der ERSTEN Runde nach dem Wake-Wort nichts ausser der
    Anrede gesagt wurde. Leerer Text zählt mit: aufgenommen, aber nichts
    verstanden heisst ebenfalls, dass die Frage noch aussteht.

    Nur für Runde 1 gültig — in späteren Runden fehlt das Wake-Wort im Audio,
    dort ist „Termine heute" eine vollständige Frage.
    """
    return len(woerter(text)) <= MAX_WOERTER
