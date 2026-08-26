"""Bewertungslogik der Modell-Aufsicht — reine Funktionen, kein I/O.

Hier stehen die Regeln samt Begründung. Wer eine Schwelle ändert, ändert sie
hier und sieht sofort, warum sie so gewählt war.

Die Aufgabe: Jede Stelle im Haus, die einen LM-Studio-Modellnamen fest
verdrahtet hat, gegen den tatsächlichen Bestand halten. Ein Modellumzug macht
solche Namen still ungültig — und zwar unsichtbar, weil ein toter Name in der
Statistik „Aufrufe je Modell" gar nicht auftaucht. Er erscheint nur als
`[ERROR] Invalid model identifier` ohne Modell-Präfix im LM-Studio-Log.

Drei Prüfungen, drei Fehlerbilder — alle drei am 26.08. gleichzeitig aktiv:

- `bewerte`         — zeigt eine Stelle auf einen Namen, den es nicht gibt?
- `bewerte_laufzeit` — ist der Name richtig, das Modell aber falsch bedient
                      (Fenster zu klein, Slotzahl abweichend)?
- `bewerte_drift`   — steht in der Konfigurationsdatei etwas anderes als im
                      laufenden Dienst?
"""

from typing import Dict, Iterable, List, NamedTuple, Optional, Tuple

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
    # | "fenster_zu_klein" | "fenster_groesser" | "slots_abweichend"
    # | "konfig_drift"
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


def bewerte_laufzeit(zustaende: Dict[str, Tuple], soll: Dict[str, Dict]) -> List[Befund]:
    """Hält Fenstergröße und Slotzahl der geladenen Modelle gegen die Vorgabe.

    Ein Modellname kann gültig und trotzdem falsch bedient sein: Am 26.08.
    stand `gemma4-31b-it` von 10:00 bis 12:11 auf 65.536 statt 98.304. Die
    Referenzprüfung sah davon nichts — die ID war ja korrekt und das Modell
    geladen. Sichtbar wurde es nur an 109 Überläufen.

    Slots werden nur bewertet, wenn das Fenster stimmt. Beide Werte gehören
    zusammen (kleineres Fenster erlaubt mehr Slots im selben Speicher); bei
    falschem Fenster ist die abweichende Slotzahl dessen Folge, keine zweite
    Meldung.
    """
    befunde: List[Befund] = []
    for modell, vorgabe in sorted(soll.items()):
        ist = zustaende.get(modell)
        if ist is None:
            # Dass ein Modell fehlt, meldet bereits `bewerte()` über die
            # Referenzen. Hier nochmal wäre eine Dublette in jedem Bericht.
            continue
        ctx_ist, slots_ist = ist
        ctx_soll = vorgabe.get("contextLength")
        slots_soll = vorgabe.get("parallel")

        if ctx_soll is not None and ctx_ist is not None and ctx_ist != ctx_soll:
            zu_klein = ctx_ist < ctx_soll
            befunde.append(
                Befund(
                    art="fenster_zu_klein" if zu_klein else "fenster_groesser",
                    schwere="hoch" if zu_klein else "niedrig",
                    quelle="LM Studio «{}»".format(modell),
                    feld="contextLength",
                    modell=modell,
                    text=(
                        "«{}» läuft mit Fenster {} statt {}. Zu klein: der "
                        "lmstudio-Adapter kürzt unterhalb seiner Schätzschwelle "
                        "gar nicht, Überläufe sind die Folge.".format(
                            modell, ctx_ist, ctx_soll
                        )
                        if zu_klein
                        else "«{}» läuft mit Fenster {} statt {}. Größer als "
                        "gefordert — kostet Speicher, sonst harmlos.".format(
                            modell, ctx_ist, ctx_soll
                        )
                    ),
                )
            )
        elif slots_soll is not None and slots_ist != slots_soll:
            befunde.append(
                Befund(
                    art="slots_abweichend",
                    schwere="niedrig",
                    quelle="LM Studio «{}»".format(modell),
                    feld="parallel",
                    modell=modell,
                    text=(
                        "«{}» hat {} Bearbeitungsplätze statt {}. Betrifft den "
                        "Durchsatz, nicht die Korrektheit.".format(
                            modell, slots_ist, slots_soll
                        )
                    ),
                )
            )
    return _sortiert(befunde)


def bewerte_drift(datei: Iterable[Referenz], dienst: Iterable[Referenz]) -> List[Befund]:
    """Vergleicht die Konfigurationsdatei mit dem, was der Dienst wirklich hat.

    launchd liest eine geänderte plist nicht von selbst nach, und
    `kickstart -k` startet nur den Prozess neu — nicht den Job. Eine Korrektur
    kann deshalb tagelang „erledigt" aussehen und wirkungslos sein. Am 26.08.
    kostete genau das 822 gescheiterte Klassifikator-Aufrufe an einem Tag.
    Erst `bootout` + `bootstrap` übernimmt neue Werte.
    """
    laufend = {r.feld: r.modell for r in dienst}
    if not laufend:
        # Job entladen — die Nichtverfügbarkeit ist eine eigene Meldung, kein
        # Drift. Als Drift gemeldet würde sie in die falsche Richtung weisen.
        return []

    befunde: List[Befund] = []
    for ref in datei:
        ist = laufend.get(ref.feld)
        if ist is not None and ist != ref.modell:
            befunde.append(
                Befund(
                    art="konfig_drift",
                    schwere="hoch",
                    quelle=ref.quelle,
                    feld=ref.feld,
                    modell=ist,
                    text=(
                        "{} ({}): Datei sagt «{}», der laufende Dienst nutzt "
                        "«{}». Die Änderung wurde nie übernommen — launchd "
                        "braucht bootout + bootstrap, kickstart genügt nicht.".format(
                            ref.quelle, ref.feld, ref.modell, ist
                        )
                    ),
                )
            )
    return _sortiert(befunde)


def signatur(befunde: Iterable[Befund]) -> List[str]:
    """Stabile Kennung der harten Befunde — Grundlage der Entprellung.

    Bewusst OHNE den Meldetext: «Fenster 65.536 statt 98.304» und
    «Fenster 32.768 statt 98.304» sind derselbe Fehler an derselben Stelle.
    Stünde der Text darin, würde jedes Wackeln des Wertes als neuer Befund
    gelten und erneut melden.

    Niedrige Befunde gehören in den Bericht, wecken aber niemanden — sie
    tauchen hier nicht auf.
    """
    return sorted(
        "{}|{}|{}".format(b.art, b.quelle, b.feld)
        for b in befunde
        if b.schwere == "hoch"
    )


def meldung_faellig(jetzt: List[str], zuletzt: List[str]) -> bool:
    """Melden nur bei Zustandswechsel.

    Der Wächter läuft alle 30 Minuten. Ohne diese Bremse erzeugt ein Zustand,
    der zwei Stunden anhält, vier gleichlautende Issues — und danach schaut
    niemand mehr hin.

    Der Aufrufer muss den Zustand bei JEDEM Lauf fortschreiben, auch wenn nicht
    gemeldet wird. Sonst gilt ein behobener Fehler beim Wiederauftreten als
    „schon gemeldet" und bleibt stumm — genau der flappende Fall vom 26.08.
    """
    return bool(jetzt) and jetzt != zuletzt


def _sortiert(befunde: List[Befund]) -> List[Befund]:
    """Schwerste zuerst, sonst stabil in Fundreihenfolge."""
    return sorted(befunde, key=lambda b: SCHWERE_REIHENFOLGE[b.schwere])
