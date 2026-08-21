"""Beweisfuehrung: Zahlen im Vorschlag muessen aus der Telemetrie stammen (WHI-3389).

Das Approval vom 31.07. nannte fuer den Online-Rechercheur "5x llm_error +
5x adapter_failed". Die Telemetrie wies llm_error=0 und adapter_failed=14
aus. Beide Zahlen waren frei formuliert. Ein Vorschlag mit erfundenen
Zahlen ist wertlos, auch wenn die Richtung zufaellig stimmt.
"""
from advisor.evidence import evidence_line, verify_error_counts


def _tel(**kw):
    base = {"max_iterations": 0, "timeout": 0, "llm_unreachable": 0,
            "llm_error": 0, "adapter_failed": 0, "process_lost": 0,
            "fail_rate": 0.0, "avg_duration_s": 0.0, "total_runs": 50,
            "succeeded": 50}
    base.update(kw)
    return base


def test_the_fabricated_count_from_whi_3389_is_flagged():
    tel = _tel(adapter_failed=14, fail_rate=0.741, total_runs=54, succeeded=14)
    bad = verify_error_counts("Signal: 5x llm_error + 5x adapter_failed", tel)
    assert {b["code"] for b in bad} == {"llm_error", "adapter_failed"}
    assert {(b["claimed"], b["actual"]) for b in bad} == {(5, 0), (5, 14)}


def test_correct_counts_raise_no_objection():
    tel = _tel(adapter_failed=14, process_lost=9)
    assert verify_error_counts("adapter_failed=14x, process_lost=9x", tel) == []


def test_all_common_spellings_are_checked():
    tel = _tel(llm_error=7)
    for text in ("7x llm_error", "7× llm_error", "llm_error=7",
                 "llm_error: 7", "llm_error 7x"):
        assert verify_error_counts(text, tel) == [], text
        assert verify_error_counts(text.replace("7", "3"), tel), text


def test_prose_without_counts_is_left_alone():
    assert verify_error_counts("Der Agent laeuft in Timeouts.", _tel()) == []


def test_unrelated_numbers_are_not_mistaken_for_counts():
    tel = _tel(llm_error=7)
    assert verify_error_counts("qwen3-coder-30b braucht 18.5 GB", tel) == []


def test_evidence_line_states_counts_window_and_runs():
    tel = _tel(adapter_failed=4, process_lost=9, fail_rate=0.921,
               total_runs=76, succeeded=6)
    line = evidence_line(tel, window_days=7)
    assert "adapter_failed=4x" in line and "process_lost=9x" in line
    assert "76 Runs" in line and "6 erfolgreich" in line
    assert "7 Tage" in line


def test_evidence_line_reports_upstream_errors_too():
    # Sonst fehlt der dominante Fehler in der Beweiszeile: der
    # n8n-Betriebsingenieur hatte 57x claude_transient_upstream neben
    # 9x process_lost -- die Zeile haette nur die 9 genannt (WHI-3389).
    tel = _tel(claude_transient_upstream=57, process_lost=9, fail_rate=0.893,
               total_runs=75, succeeded=8)
    line = evidence_line(tel, window_days=7)
    assert "claude_transient_upstream=57x" in line
    assert line.index("claude_transient_upstream") < line.index("process_lost")


def test_the_code_list_does_not_drift_from_the_telemetry():
    from advisor.telemetry import _ERROR_CODES
    from advisor.evidence import CODES
    assert set(CODES) == set(_ERROR_CODES)


def test_evidence_line_says_so_when_there_is_nothing_to_report():
    line = evidence_line(_tel(), window_days=7)
    assert "keine codierten Fehler" in line


def test_evidence_line_survives_a_verification_of_itself():
    # Die gerenderte Zeile ist per Konstruktion widerspruchsfrei -- das ist
    # der Punkt: der Agent uebernimmt sie, statt Zahlen zu formulieren.
    tel = _tel(adapter_failed=14, fail_rate=0.741, total_runs=54, succeeded=14)
    assert verify_error_counts(evidence_line(tel, window_days=7), tel) == []
