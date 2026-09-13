"""Ablauf eines Wächter-Laufs: was wird geholt, was gemeldet, was verschwiegen.

Resume und Mailversand werden hineingereicht, damit der Ablauf ohne DB und
ohne Netz prüfbar ist.
"""

from datetime import datetime, timedelta

from melder import lauf
from pruefung import Agent, Lage

JETZT = datetime(2026, 9, 13, 8, 0, 0)


def agent(name, minuten_in_error, agent_id=None):
    return Agent(
        name=name,
        agent_id=agent_id or f"id-{name}",
        company_id="c1",
        error_seit=JETZT - timedelta(minutes=minuten_in_error),
    )


class Spion:
    """Merkt sich, was der Lauf getan hätte."""

    def __init__(self, resume_ergebnis=True):
        self.geholt = []
        self.mails = []
        self.resume_ergebnis = resume_ergebnis

    def resumen(self, a):
        self.geholt.append(a.name)
        return self.resume_ergebnis

    def mailen(self, betreff, text):
        self.mails.append(betreff)


def test_ruhiger_lauf_fasst_nichts_an_und_mailt_nicht():
    s = Spion()
    lage = Lage(agenten_in_error=[], letzter_ledger=JETZT, betreut={})
    bericht = lauf(lage, JETZT, s.resumen, s.mailen, letzte_sig=None)
    assert s.geholt == []
    assert s.mails == []
    assert bericht.gemeldet is False


def test_stehender_agent_wird_geholt_und_gemeldet():
    s = Spion()
    lage = Lage(agenten_in_error=[agent("CEO", 30)], letzter_ledger=None, betreut={})
    bericht = lauf(lage, JETZT, s.resumen, s.mailen, letzte_sig=None)
    assert s.geholt == ["CEO"]
    assert len(s.mails) == 1
    assert bericht.gemeldet is True


def test_unveraenderte_lage_wird_nicht_erneut_gemailt():
    """Sonst mailt der Wächter im 15-Minuten-Takt dieselbe Nachricht."""
    s = Spion()
    lage = Lage(agenten_in_error=[agent("CEO", 30)], letzter_ledger=None, betreut={})
    erster = lauf(lage, JETZT, s.resumen, s.mailen, letzte_sig=None)
    s2 = Spion()
    lauf(lage, JETZT, s2.resumen, s2.mailen, letzte_sig=erster.signatur)
    assert s2.mails == []


def test_erneuter_lauf_holt_trotzdem_wieder():
    """Keine Mail heißt nicht: nichts tun. Ein Agent, der wieder kippt, wird
    weiter geholt — nur eben still."""
    s = Spion()
    lage = Lage(agenten_in_error=[agent("CEO", 30)], letzter_ledger=None, betreut={})
    sig = lauf(lage, JETZT, s.resumen, s.mailen, letzte_sig=None).signatur
    s2 = Spion()
    lauf(lage, JETZT, s2.resumen, s2.mailen, letzte_sig=sig)
    assert s2.geholt == ["CEO"]


def test_gescheitertes_resume_steht_im_bericht():
    s = Spion(resume_ergebnis=False)
    lage = Lage(agenten_in_error=[agent("CEO", 30)], letzter_ledger=None, betreut={})
    bericht = lauf(lage, JETZT, s.resumen, s.mailen, letzte_sig=None)
    assert bericht.geholt == []
    assert bericht.fehlgeschlagen == ["CEO"]


def test_stumme_selbstheilung_steht_im_betreff():
    """Der eigentliche Zweck dieses Wächters — das hätte den 02.09. gemeldet."""
    s = Spion()
    lage = Lage(
        agenten_in_error=[agent("CEO", 600)],
        letzter_ledger=JETZT - timedelta(days=11),
        betreut={},
    )
    lauf(lage, JETZT, s.resumen, s.mailen, letzte_sig=None)
    assert "Selbstheilung" in s.mails[0]


def test_arbeitende_selbstheilung_wird_nicht_gestoert():
    """Weder anfassen noch melden: die interne hat den Fall, das ist
    Normalbetrieb."""
    s = Spion()
    a = agent("Buchhaltung", 90)
    lage = Lage(
        agenten_in_error=[a],
        letzter_ledger=JETZT - timedelta(minutes=2),
        betreut={a.agent_id: JETZT - timedelta(minutes=2)},
    )
    bericht = lauf(lage, JETZT, s.resumen, s.mailen, letzte_sig=None)
    assert s.geholt == []
    assert s.mails == []
    assert bericht.gemeldet is False


def test_ein_kaputtes_resume_stoppt_die_uebrigen_nicht():
    """Ein Agent, dessen resume wirft, darf die Runde nicht beenden."""

    geholt = []

    def resumen(a):
        if a.name == "CEO":
            raise RuntimeError("500 vom Server")
        geholt.append(a.name)
        return True

    lage = Lage(
        agenten_in_error=[agent("CEO", 30), agent("CTO", 30)],
        letzter_ledger=None,
        betreut={},
    )
    bericht = lauf(lage, JETZT, resumen, lambda b, t: None, letzte_sig=None)
    assert geholt == ["CTO"]
    assert bericht.fehlgeschlagen == ["CEO"]
