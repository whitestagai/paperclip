#!/usr/bin/env python3
"""Tests des Kontext-Berichts. Aufruf: python3 -m pytest test_ctx_report.py -q"""
import ctx_report


# --------------------------------------------------------------------------- #
# Overflow-Zaehlung
# --------------------------------------------------------------------------- #
# Echtes Fehlerbild: das Modell steht nur in der ERSTEN Zeile des Blocks,
# die eigentliche Ursache erst mehrere Zeilen spaeter in einem
# "- Caused By:"-Nachsatz. Wer nur nach dem Fehlertext greppt, kann ihn
# keinem Modell zuordnen — und wer nur die ERROR-Zeile liest, sieht die
# Ursache nicht.
LOG = """[2026-08-23 08:41:28][ERROR][gemma4-31b-it] Error: Channel Error
    at _0x403dc9.<computed> (index.js:1158:10550)
    at process.processTicksAndRejections (node:internal/process/task_queues:105:5)
- Caused By: Error: Channel Error
    at _0x15ff04.FacadeClientPort.createChannel (index.js:241:35165)
- Caused By: Error: Engine protocol predict stream returned an error: \
{"code":500,"message":"Context size has been exceeded.","type":"server_error"}
    at _0x30f530.<computed> (index.js:245:93126)
[2026-08-23 08:42:01][INFO][gemma4-31b-it] Generated prediction: {}
[2026-08-23 08:43:00][ERROR][google/gemma-4-12b] Error: Channel Error
- Caused By: Error: Engine protocol predict stream returned an error: \
{"code":500,"message":"Context size has been exceeded.","type":"server_error"}
[2026-08-23 08:44:00][ERROR][gemma4-31b-it] Error: something else entirely
- Caused By: Error: Model unloaded
"""


def test_overflow_wird_dem_richtigen_modell_zugeordnet():
    assert ctx_report.parse_overflows(LOG) == {
        "gemma4-31b-it": 1,
        "google/gemma-4-12b": 1,
    }


def test_andere_fehler_zaehlen_nicht_mit():
    """'Model unloaded' ist ein Reload, kein Overflow — die beiden Fehlerbilder
    unterscheiden die Phasen und duerfen nicht vermischt werden."""
    assert "Model unloaded" in LOG
    assert ctx_report.parse_overflows(LOG).get("gemma4-31b-it") == 1


def test_fehlertext_ohne_vorangehende_modellzeile_wird_verworfen():
    """Am Dateianfang kann der Block angeschnitten sein — dann ist das Modell
    unbekannt und darf nicht dem naechstbesten zugeschlagen werden."""
    text = ('- Caused By: Error: {"message":"Context size has been exceeded."}\n')
    assert ctx_report.parse_overflows(text) == {}


def test_ein_block_zaehlt_einmal():
    """LM Studio wiederholt die Ursache verschachtelt; doppelt zaehlen wuerde
    die Zahl aufblaehen."""
    text = ("[2026-08-23 09:00:00][ERROR][m] Error: Channel Error\n"
            '- Caused By: Error: {"message":"Context size has been exceeded."}\n'
            '- Caused By: Error: {"message":"Context size has been exceeded."}\n')
    assert ctx_report.parse_overflows(text) == {"m": 1}


# --------------------------------------------------------------------------- #
# Ampel
# --------------------------------------------------------------------------- #
def test_gemessener_overflow_schlaegt_die_schaetzung():
    """Der Kern: p99 und MAX stammen aus ERFOLGREICHEN Aufrufen — ein Prompt,
    der am Fenster scheitert, erzeugt nie eine usage-Zeile und faellt aus der
    Statistik. Deshalb stand 'GRUEN' im Bericht, waehrend 129 Aufrufe am Tag
    genau daran starben. Ein gezaehlter Overflow ist harter Beweis und muss
    die Schaetzung ueberstimmen."""
    farbe, _sym, text = ctx_report.ampel(98304, 57901, 83845, overflows=129)
    assert farbe == "#d93025"
    assert "ROT" in text and "129" in text


def test_ohne_overflow_bleibt_die_bisherige_bewertung():
    farbe, _sym, text = ctx_report.ampel(98304, 57901, 83845, overflows=0)
    assert farbe == "#188038"
    assert "GRÜN" in text


def test_overflow_zaehlt_auch_bei_nicht_ermitteltem_fenster():
    """JIT-geladen, kein Fenster in der Config — der Overflow ist trotzdem real."""
    farbe, _sym, text = ctx_report.ampel(None, 1000, 2000, overflows=7)
    assert farbe == "#d93025"
    assert "7" in text


def test_ampel_bleibt_ohne_das_neue_argument_aufrufbar():
    """send_ctx_mail.sh und aeltere Aufrufer sollen nicht brechen."""
    assert ctx_report.ampel(98304, 57901, 83845)[0] == "#188038"
