"""Bewertungslogik der Modell-Aufsicht — reine Funktionen, kein I/O.

Hier stehen die Regeln samt Begründung. Wer eine Schwelle ändert, ändert sie
hier und sieht sofort, warum sie so gewählt war.

Die Aufgabe: Jede Stelle im Haus, die einen LM-Studio-Modellnamen fest
verdrahtet hat, gegen den tatsächlichen Bestand halten. Ein Modellumzug macht
solche Namen still ungültig — und zwar unsichtbar, weil ein toter Name in der
Statistik „Aufrufe je Modell" gar nicht auftaucht. Er erscheint nur als
`[ERROR] Invalid model identifier` ohne Modell-Präfix im LM-Studio-Log.
"""

from typing import Iterable, List, NamedTuple, Optional

# Hinweis: launchd startet hier mit dem System-Python 3.9. Deshalb `Optional[x]`
# statt `x | None` und `List[x]` statt `list[x]` — sonst scheitert der Import
# erst nachts im Dienst, nicht beim Entwickeln.

# Modelle, die nicht über LM Studio laufen und deshalb nie in `/v1/models`
# stehen. Sie gegen den lokalen Bestand zu prüfen erzeugt nur Fehlalarme.
FREMDE_ANBIETER = ("claude-", "gpt-", "o1-", "o3-", "gemini-", "grok-")

SCHWERE_REIHENFOLGE = {"hoch": 0, "niedrig": 1}


class Bestand(NamedTuple):
    """Was LM Studio kennt.

    `vorhanden` = alle heruntergeladenen Modell-IDs (geladen oder nicht).
    `geladen`   = die davon gerade im Speicher liegenden.
    """

    vorhanden: frozenset
    geladen: frozenset


class Referenz(NamedTuple):
    """Eine Stelle, die einen Modellnamen fest verdrahtet hat."""

    quelle: str  # menschenlesbar, z. B. "Link-Detektor link_detektor_clara"
    feld: str  # wo genau, z. B. "llm_model" oder "runtimeConfig.cheap.model"
    modell: str


class Befund(NamedTuple):
    art: str  # "unbekannt" | "nicht_geladen" | "quelle_unlesbar"
    schwere: str  # "hoch" | "niedrig"
    quelle: str
    feld: str
    modell: Optional[str]
    text: str


def _ist_fremd(modell: str) -> bool:
    return modell.startswith(FREMDE_ANBIETER)


def bewerte(
    referenzen: Iterable[Referenz],
    bestand: Bestand,
    unlesbare_quellen: Iterable[str],
) -> List[Befund]:
    """Vergleicht alle Referenzen mit dem Bestand.

    Fail-closed an zwei Stellen: eine Quelle, die sich nicht lesen ließ, ist
    selbst ein Befund — und ein leerer Bestand bedeutet, dass LM Studio nicht
    antwortete. Dann darf NICHT geprüft werden, sonst wären auf einen Schlag
    alle Referenzen „unbekannt" und der Bericht ertränkt den echten Befund in
    vierzig Fehlalarmen.
    """
    befunde: List[Befund] = []

    for quelle in unlesbare_quellen:
        befunde.append(
            Befund(
                art="quelle_unlesbar",
                schwere="hoch",
                quelle=quelle,
                feld="",
                modell=None,
                text=f"Quelle nicht lesbar, keine Aussage möglich: {quelle}",
            )
        )

    if not bestand.vorhanden:
        befunde.append(
            Befund(
                art="quelle_unlesbar",
                schwere="hoch",
                quelle="LM Studio",
                feld="",
                modell=None,
                text=(
                    "LM Studio lieferte keinen Modellbestand — die Referenzen "
                    "wurden NICHT geprüft (sonst wäre jede davon ein Fehlalarm)."
                ),
            )
        )
        return _sortiert(befunde)

    for ref in referenzen:
        if not ref.modell or _ist_fremd(ref.modell):
            continue
        if ref.modell not in bestand.vorhanden:
            befunde.append(
                Befund(
                    art="unbekannt",
                    schwere="hoch",
                    quelle=ref.quelle,
                    feld=ref.feld,
                    modell=ref.modell,
                    text=(
                        f"{ref.quelle} ({ref.feld}) zeigt auf «{ref.modell}» — "
                        "diese ID kennt LM Studio nicht. Jeder Aufruf scheitert "
                        "mit «Invalid model identifier»."
                    ),
                )
            )
        elif ref.modell not in bestand.geladen:
            befunde.append(
                Befund(
                    art="nicht_geladen",
                    schwere="niedrig",
                    quelle=ref.quelle,
                    feld=ref.feld,
                    modell=ref.modell,
                    text=(
                        f"{ref.quelle} ({ref.feld}) nutzt «{ref.modell}», das gerade "
                        "nicht geladen ist. Funktioniert (LM Studio lädt nach), "
                        "kostet aber den Kaltstart."
                    ),
                )
            )

    return _sortiert(befunde)


def _sortiert(befunde: List[Befund]) -> List[Befund]:
    """Schwerste zuerst, sonst stabil in Fundreihenfolge."""
    return sorted(befunde, key=lambda b: SCHWERE_REIHENFOLGE[b.schwere])
