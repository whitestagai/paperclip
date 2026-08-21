#!/usr/bin/env python3
"""Bewertung des Link-Detektor-Betriebs — reine Logik, kein I/O.

Getrennt vom Waechter, weil genau diese Entscheidung im Ernstfall zaehlt und
sich sonst nie pruefen liesse. Der Ernstfall ist belegt: der v11-Daemon
verarbeitete vom 21.06. bis zum 30.07.2026 **sechs Wochen lang keinen
einzigen Job** -- 45.000 Fehl-Jobs durch `spawn EBADF`, und niemand merkte
es. Beide LaunchAgents zeigten "running", und die Logs liest niemand.

Die Kette hat zwei Haelften, die unabhaengig ausfallen koennen: der
v11-Daemon (Watcher stellt ein, Worker arbeitet ab) und der n8n-Workflow
`Link-Detektor V10.2`, der taeglich um 01:00 die produktiven Vorschlaege
macht. Beide werden hier geprueft.

Python 3.9 -- launchd faehrt /usr/bin/python3, also kein `X | None`.
"""
from typing import List, NamedTuple

# Der Watcher stellt nur bei Vault-Aenderungen Jobs ein. Eine ruhige Woche
# ohne neue Notizen ist deshalb kein Defekt -- sechs Wochen sind einer.
STILLSTAND_TAGE = 7

# Bei EBADF scheiterten 100 Prozent der Jobs. Das normale Rauschen liegt bei
# 0,1 Prozent (19 von 19.595: Notizen, die vor ihrem Job umbenannt wurden).
# 20 Prozent laesst das Rauschen durch und faengt jeden echten Bruch.
FEHLERQUOTE_GRENZE = 0.20

# Unter dieser Menge ist die Quote Zufall: bei drei Jobs waere ein einzelner
# Fehler bereits ein Drittel.
MINDEST_JOBS = 20

# Ein Job dauert 70 bis 90 Sekunden (NER + LLM). Zwei Stunden sind das
# Achtzigfache -- alles darueber haengt.
RUNNING_GRENZE_H = 2

# V10.2 feuert taeglich um 01:00. 48 Stunden decken einen verschobenen Lauf
# ab, verschlucken aber keine ausgefallene Nacht.
N8N_GRENZE_H = 48


class Befund(NamedTuple):
    ok: bool
    probleme: List[str]
    zeilen: List[str]


def _stunden(jetzt, dann):
    return (jetzt - dann).total_seconds() / 3600.0


def bewerte(jetzt, letzter_done, jobs_7t, fehler_7t, laengster_running,
            letzter_n8n_erfolg):
    """Den Betriebszustand beider Haelften der Kette beurteilen.

    `zeilen` wird IMMER gefuellt, auch im gesunden Fall: der Agent uebernimmt
    sie woertlich, statt Zahlen selbst zu formulieren -- dieselbe
    Konstruktion, mit der `evidence_line` beim LLM-Advisor die erfundenen
    Zahlen abgestellt hat.
    """
    probleme = []
    zeilen = []

    # --- v11-Daemon: kommt ueberhaupt etwas durch? ---
    if letzter_done is None:
        probleme.append("Stillstand: kein einziger erledigter Job in der Datenbank.")
        zeilen.append("Erledigte Jobs: keine.")
    else:
        alter_h = _stunden(jetzt, letzter_done)
        zeilen.append("Letzter erledigter Job vor %.1f Stunden." % alter_h)
        if alter_h > STILLSTAND_TAGE * 24:
            probleme.append(
                "Stillstand: seit %.1f Tagen kein erledigter Job (Grenze %d Tage)."
                % (alter_h / 24, STILLSTAND_TAGE))

    zeilen.append("Jobs der letzten 7 Tage: %d, davon %d mit Fehler."
                  % (jobs_7t, fehler_7t))
    if jobs_7t >= MINDEST_JOBS:
        quote = fehler_7t / float(jobs_7t)
        if quote > FEHLERQUOTE_GRENZE:
            probleme.append(
                "Fehlerquote %.0f%% in 7 Tagen (%d von %d, Grenze %.0f%%)."
                % (quote * 100, fehler_7t, jobs_7t, FEHLERQUOTE_GRENZE * 100))

    # --- haengende Jobs ---
    if laengster_running is not None:
        steht_h = _stunden(jetzt, laengster_running)
        if steht_h > RUNNING_GRENZE_H:
            probleme.append(
                "Ein Job steht seit %.1f Stunden auf `running` (Grenze %d h; "
                "ein Job dauert normal 70-90 s)." % (steht_h, RUNNING_GRENZE_H))
        else:
            zeilen.append("Ein Job laeuft gerade (seit %.0f Minuten)." % (steht_h * 60))

    # --- n8n V10.2: die produktive Haelfte ---
    if letzter_n8n_erfolg is None:
        probleme.append("n8n `Link-Detektor V10.2`: kein erfolgreicher Lauf auffindbar.")
        zeilen.append("n8n V10.2: kein erfolgreicher Lauf auffindbar.")
    else:
        n8n_h = _stunden(jetzt, letzter_n8n_erfolg)
        zeilen.append("n8n V10.2: letzter Erfolg vor %.1f Stunden." % n8n_h)
        if n8n_h > N8N_GRENZE_H:
            probleme.append(
                "n8n `Link-Detektor V10.2`: seit %.1f Stunden kein erfolgreicher "
                "Lauf (Grenze %d h, laeuft taeglich 01:00)." % (n8n_h, N8N_GRENZE_H))

    return Befund(ok=not probleme, probleme=probleme, zeilen=zeilen)
