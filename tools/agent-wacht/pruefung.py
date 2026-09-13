"""Reine Entscheidungslogik der Agenten-Aufsicht — ohne DB, ohne Netz.

Arbeitsteilung mit der internen Selbstheilung (server/src/services/recovery/
agent-self-heal.ts): Die interne ist zuständig und kennt Backoff-Stufen von
5/15/60 Minuten. Dieser Wächter greift ihr NICHT vor die Füße — er wird nur
tätig, wo sie erkennbar nicht arbeitet. Sonst entsteht genau die Weckschleife,
die wir vermeiden wollen.

System-Python 3.9: keine `x | None`-Annotationen, sonst scheitert der Import
erst nachts im launchd-Lauf.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional

# Signatur einer Lage, in der nichts zu tun ist. Wird nie gemeldet.
RUHIG = "ruhig"

SCHWELLE_MIN = 20
MAX_STILLE_MIN = 60
# Wie frisch eine offene Ledger-Zeile sein muss, damit sie als aktive Betreuung
# gilt. Die längste Backoff-Stufe der internen Selbstheilung sind 60 Minuten;
# was länger unberührt liegt, ist aufgegeben (sie gibt nach drei Versuchen je
# Fehlercode auf und lässt die Zeile offen stehen).
BETREUUNG_FRISCH_MIN = 75


@dataclass
class Agent:
    name: str
    agent_id: str
    company_id: str
    error_seit: datetime


@dataclass
class Lage:
    """Momentaufnahme: wer steht, und arbeitet die interne Selbstheilung noch?"""

    agenten_in_error: List[Agent] = field(default_factory=list)
    letzter_ledger: Optional[datetime] = None
    # agent_id -> updated_at der offenen Ledger-Zeile. Nur ein frischer
    # Zeitstempel bedeutet, dass die interne Selbstheilung den Fall gerade
    # bearbeitet; eine alte offene Zeile ist ein aufgegebener Fall.
    betreut: Dict[str, datetime] = field(default_factory=dict)


def selbstheilung_schweigt(lage: Lage, jetzt: datetime, max_stille_min: int = MAX_STILLE_MIN) -> bool:
    """Stehen Agenten still, ohne dass der Ledger sich rührt?

    Das ist die Aufsicht über die Aufsicht. Ein stiller Ledger allein ist kein
    Befund — ohne Vorfälle gibt es nichts zu schreiben. Erst die Kombination
    „Agenten in error UND niemand schreibt" heißt, dass der Wächter fehlt.
    """
    if not lage.agenten_in_error:
        return False
    if lage.letzter_ledger is None:
        return True
    return (jetzt - lage.letzter_ledger) > timedelta(minutes=max_stille_min)


def zu_holen(
    lage: Lage,
    jetzt: datetime,
    schwelle_min: int = SCHWELLE_MIN,
    max_stille_min: int = MAX_STILLE_MIN,
) -> List[Agent]:
    """Welche Agenten holt dieser Wächter selbst zurück?

    Zwei Bedingungen: lange genug gestanden, und die interne Selbstheilung
    kümmert sich nicht schon darum. „Kümmert sich" verlangt eine offene
    Ledger-Zeile MIT frischem Zeitstempel — eine uralte offene Zeile wäre
    sonst ein Freibrief, den Agenten ewig liegen zu lassen.
    """
    stumm = selbstheilung_schweigt(lage, jetzt, max_stille_min)
    treffer = []
    for a in lage.agenten_in_error:
        if (jetzt - a.error_seit) < timedelta(minutes=schwelle_min):
            continue
        if not stumm and _wird_betreut(lage, a, jetzt):
            continue
        treffer.append(a)
    return treffer


def _wird_betreut(lage: Lage, a: Agent, jetzt: datetime) -> bool:
    beruehrt = lage.betreut.get(a.agent_id)
    if beruehrt is None:
        return False
    return (jetzt - beruehrt) <= timedelta(minutes=BETREUUNG_FRISCH_MIN)


def signatur(
    lage: Lage,
    jetzt: datetime,
    max_stille_min: int = MAX_STILLE_MIN,
) -> str:
    """Kennzeichen der Lage für die Wechselerkennung.

    Bewusst ohne Dauer und ohne Zahlenwerte: sonst gilt jeder Lauf als neue
    Lage und der Wächter mailt im 15-Minuten-Takt.

    Aktiv betreute Agenten zählen nicht mit. Ein Agent, der kippt und von der
    internen Selbstheilung sofort aufgenommen wird, ist Normalbetrieb — würde
    er gemeldet, wäre der Wächter nach wenigen Tagen Rauschen, das niemand
    mehr liest. Gemeldet wird, was liegen bleibt.
    """
    stumm = selbstheilung_schweigt(lage, jetzt, max_stille_min)
    namen = sorted(
        a.name for a in lage.agenten_in_error if stumm or not _wird_betreut(lage, a, jetzt)
    )
    if not namen and not stumm:
        return RUHIG
    return "|".join(namen) + ("#stumm" if stumm else "")


def meldung_faellig(sig: str, letzte_sig: Optional[str]) -> bool:
    """Nur bei echtem Zustandswechsel melden — und nie den Normalfall."""
    if sig == RUHIG:
        return False
    return sig != letzte_sig
