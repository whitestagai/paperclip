"""Beweisfuehrung: Fehlerzahlen werden gerendert, nicht formuliert (WHI-3389).

Das Approval vom 31.07. nannte "5x llm_error + 5x adapter_failed", waehrend
die Telemetrie llm_error=0 und adapter_failed=14 auswies. Beide Zahlen kamen
aus dem Fliesstext des Modells. Solange das moeglich ist, ist jeder Vorschlag
unpruefbar -- auch der zufaellig richtige.

`evidence_line` rendert die Zahlen deterministisch, damit der Agent sie
uebernehmen statt tippen kann. `verify_error_counts` ist das Netz darunter:
es liest jede im Text behauptete Fehlerzahl und haelt sie gegen die Telemetrie.
"""
import re

from advisor.telemetry import _ERROR_CODES

# Bewusst dieselbe Liste wie die Telemetrie: eine eigene Kopie hier waere
# genau der Weg, auf dem `claude_transient_upstream` erneut unsichtbar wird.
CODES = _ERROR_CODES

# "5x llm_error", "5× llm_error"
_COUNT_BEFORE = re.compile(
    r"(?<![\d.,])(\d+)\s*[x×]\s+(" + "|".join(CODES) + r")\b", re.IGNORECASE)
# "llm_error=5", "llm_error: 5", "llm_error 5x"
_COUNT_AFTER = re.compile(
    r"\b(" + "|".join(CODES) + r")\b\s*(?:[=:]|\s)\s*(\d+)(?![\d.,])", re.IGNORECASE)


def _claims(text):
    """Alle im Text behaupteten (code, zahl)-Paare, Reihenfolge egal."""
    found = []
    for m in _COUNT_BEFORE.finditer(text or ""):
        found.append((m.group(2).lower(), int(m.group(1))))
    for m in _COUNT_AFTER.finditer(text or ""):
        found.append((m.group(1).lower(), int(m.group(2))))
    return found


def verify_error_counts(text, telemetry):
    """Gibt die Abweichungen zwischen behaupteten und echten Fehlerzahlen.

    Leere Liste heisst: jede im Text genannte Zahl deckt sich mit der
    Telemetrie. Zahlen ohne Fehlercode-Bezug werden nicht angefasst --
    Modellgroessen und GB-Angaben sind keine Behauptungen ueber Fehler.
    """
    bad = []
    seen = set()
    for code, claimed in _claims(text):
        actual = telemetry.get(code) or 0
        if claimed != actual and (code, claimed) not in seen:
            seen.add((code, claimed))
            bad.append({"code": code, "claimed": claimed, "actual": actual})
    return bad


def evidence_line(telemetry, window_days):
    """Die Fehlerlage eines Agenten als uebernehmbarer Satz."""
    counts = [(c, telemetry.get(c) or 0) for c in CODES]
    counts = [(c, n) for c, n in counts if n]
    runs = telemetry.get("total_runs") or 0
    ok = telemetry.get("succeeded") or 0
    tail = (f"{runs} Runs, {ok} erfolgreich, fail_rate="
            f"{telemetry.get('fail_rate') or 0.0}, Fenster {window_days} Tage")
    if not counts:
        return f"keine codierten Fehler ({tail})"
    codes = ", ".join(f"{c}={n}x" for c, n in sorted(counts, key=lambda x: -x[1]))
    return f"{codes} ({tail})"
