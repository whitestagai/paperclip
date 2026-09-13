"""Die Ernstfälle. Jeder Test hier ist ein Vorfall, der schon passiert ist.

Leitfall: Am 02.09.2026 um 20:57 wechselte der Watch-Tree den Branch und nahm
die interne Selbstheilung mit. Elf Tage lang holte niemand mehr Agenten aus
`error`; am 13.09. standen fünf Agenten zwischen 10 und 46 Stunden still.
Der Ausfall war lautlos — ein fehlender Wächter meldet nichts.
"""

from datetime import datetime, timedelta

from pruefung import (
    Agent,
    Lage,
    meldung_faellig,
    selbstheilung_schweigt,
    signatur,
    zu_holen,
)

JETZT = datetime(2026, 9, 13, 8, 0, 0)


def agent(name, minuten_in_error, agent_id=None):
    return Agent(
        name=name,
        agent_id=agent_id or f"id-{name}",
        company_id="c1",
        error_seit=JETZT - timedelta(minutes=minuten_in_error),
    )


# --- zu_holen: wen fasst der externe Wächter an? ------------------------------


def test_frischer_fehler_wird_in_ruhe_gelassen():
    """Unter der Schwelle gehört der Fall der internen Selbstheilung."""
    lage = Lage(agenten_in_error=[agent("CTO", 5)], letzter_ledger=JETZT, betreut={})
    assert zu_holen(lage, JETZT) == []


def test_agent_ueber_der_schwelle_wird_geholt():
    kandidaten = zu_holen(
        Lage(agenten_in_error=[agent("CEO", 25)], letzter_ledger=JETZT, betreut={}),
        JETZT,
    )
    assert [a.name for a in kandidaten] == ["CEO"]


def test_interne_selbstheilung_hat_vorrang():
    """Offener Ledger-Eintrag heißt: die interne kümmert sich, womöglich im
    60-Minuten-Backoff. Da darf der externe Wächter nicht dazwischenfunken —
    sonst entsteht die Weckschleife, die wir gerade vermeiden wollen."""
    a = agent("Buchhaltung", 90)
    lage = Lage(
        agenten_in_error=[a],
        letzter_ledger=JETZT - timedelta(minutes=2),
        betreut={a.agent_id: JETZT - timedelta(minutes=2)},
    )
    assert zu_holen(lage, JETZT) == []


def test_aufgegebener_fall_wird_trotz_offener_zeile_geholt():
    """Die interne gibt nach drei Versuchen je Fehlercode auf und lässt die
    Ledger-Zeile offen stehen. Eine offene, aber seit Stunden unberührte Zeile
    heißt also NICHT „kümmert sich" — sonst liegt der Agent ewig. Genau so
    standen am 13.09. fünf Agenten zwischen 10 und 46 Stunden."""
    a = agent("Buchhaltung", 2000)
    lage = Lage(
        agenten_in_error=[a],
        letzter_ledger=JETZT - timedelta(minutes=3),  # interne lebt, andere Faelle
        betreut={a.agent_id: JETZT - timedelta(hours=9)},  # aber dieser liegt brach
    )
    assert [x.name for x in zu_holen(lage, JETZT)] == ["Buchhaltung"]


def test_bei_stummer_selbstheilung_wird_trotz_ledger_eintrag_geholt():
    """Der 11-Tage-Fall: Ledger-Zeilen sind da, aber uralt — niemand arbeitet
    sie ab. Dann muss der externe Wächter ran, auch wenn eine Zeile offen ist."""
    a = agent("Redaktion & PR", 2700)
    lage = Lage(
        agenten_in_error=[a],
        letzter_ledger=JETZT - timedelta(days=11),
        betreut={a.agent_id: JETZT - timedelta(days=11)},
    )
    assert [x.name for x in zu_holen(lage, JETZT)] == ["Redaktion & PR"]


def test_schwelle_ist_einstellbar():
    lage = Lage(agenten_in_error=[agent("CRO", 12)], letzter_ledger=JETZT, betreut={})
    assert zu_holen(lage, JETZT, schwelle_min=10) != []
    assert zu_holen(lage, JETZT, schwelle_min=20) == []


# --- selbstheilung_schweigt: die Aufsicht über die Aufsicht -------------------


def test_kein_alarm_wenn_es_nichts_zu_heilen_gibt():
    """Ein stiller Ledger ohne error-Agenten ist der Normalfall, kein Befund."""
    lage = Lage(agenten_in_error=[], letzter_ledger=JETZT - timedelta(days=11), betreut={})
    assert selbstheilung_schweigt(lage, JETZT) is False


def test_alarm_wenn_agenten_stehen_und_der_ledger_schweigt():
    """Genau der Vorfall vom 02.09.—13.09."""
    lage = Lage(
        agenten_in_error=[agent("CEO", 600)],
        letzter_ledger=JETZT - timedelta(days=11),
        betreut={},
    )
    assert selbstheilung_schweigt(lage, JETZT) is True


def test_kein_alarm_solange_der_ledger_frisch_ist():
    lage = Lage(
        agenten_in_error=[agent("CTO", 30)],
        letzter_ledger=JETZT - timedelta(minutes=10),
        betreut={},
    )
    assert selbstheilung_schweigt(lage, JETZT) is False


def test_leerer_ledger_mit_stehenden_agenten_ist_alarm():
    """Frisch aufgesetzte Instanz oder gelöschte Tabelle — nie geschrieben."""
    lage = Lage(agenten_in_error=[agent("CEO", 120)], letzter_ledger=None, betreut={})
    assert selbstheilung_schweigt(lage, JETZT) is True


# --- Zustandswechsel: nur melden, wenn sich etwas geändert hat ----------------


def test_gleiche_lage_wird_nicht_zweimal_gemeldet():
    lage = Lage(agenten_in_error=[agent("CEO", 30)], letzter_ledger=None, betreut={})
    sig = signatur(lage, JETZT)
    assert meldung_faellig(sig, sig) is False


def test_neuer_agent_in_error_ist_eine_neue_lage():
    eine = Lage(agenten_in_error=[agent("CEO", 30)], letzter_ledger=None, betreut={})
    zwei = Lage(
        agenten_in_error=[agent("CEO", 30), agent("CTO", 25)],
        letzter_ledger=None,
        betreut={},
    )
    assert meldung_faellig(signatur(zwei, JETZT), signatur(eine, JETZT)) is True


def test_signatur_ignoriert_die_blosse_dauer():
    """Sonst gilt jeder Lauf als neue Lage und der Wächter mailt im Takt."""
    frueh = Lage(agenten_in_error=[agent("CEO", 30)], letzter_ledger=None, betreut={})
    spaet = Lage(agenten_in_error=[agent("CEO", 45)], letzter_ledger=None, betreut={})
    assert signatur(frueh, JETZT) == signatur(spaet, JETZT)


def test_ruhige_lage_erzeugt_keine_meldung():
    """Nichts in error, Ledger frisch: der Regelfall darf nie mailen."""
    lage = Lage(agenten_in_error=[], letzter_ledger=JETZT, betreut={})
    assert meldung_faellig(signatur(lage, JETZT), None) is False


def test_aktiv_betreuter_agent_ist_kein_befund():
    """Ein Agent kippt, die interne Selbstheilung nimmt ihn sofort auf — das
    ist Normalbetrieb und darf keine Mail erzeugen. Sonst meldet der Wächter
    jeden einzelnen Wackler und wird zu Rauschen, das niemand mehr liest."""
    a = agent("CTO", 2)
    lage = Lage(
        agenten_in_error=[a],
        letzter_ledger=JETZT - timedelta(minutes=1),
        betreut={a.agent_id: JETZT - timedelta(minutes=1)},
    )
    assert signatur(lage, JETZT) == "ruhig"
    assert meldung_faellig(signatur(lage, JETZT), None) is False


def test_unbetreuter_agent_neben_einem_betreuten_wird_gemeldet():
    """Der betreute faellt aus der Signatur, der liegengebliebene nicht."""
    betreut_a = agent("CTO", 2)
    liegt = agent("Buchhaltung", 600)
    lage = Lage(
        agenten_in_error=[betreut_a, liegt],
        letzter_ledger=JETZT - timedelta(minutes=1),
        betreut={betreut_a.agent_id: JETZT - timedelta(minutes=1)},
    )
    assert signatur(lage, JETZT) == "Buchhaltung"
