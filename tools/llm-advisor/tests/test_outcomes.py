"""Wirksamkeitsmessung: hat ein Befund je etwas verbessert? (WHI-3389)

102 Vorschlaege lagen im State, 20 als implemented markiert, und niemand
hatte je geprueft ob einer geholfen hat.
"""
from advisor.outcomes import (class_rate, classify_outcome, evaluate,
                              find_config_change, MIN_RUNS_FOR_VERDICT)


def _runs(n, **codes):
    """n Laeufe insgesamt, davon je Code die angegebene Anzahl."""
    out = []
    for code, count in codes.items():
        out += [{"error_code": code}] * count
    out += [{"error_code": None}] * (n - len(out))
    return out


def test_class_rate_is_the_share_of_runs_hit_by_the_class():
    rate = class_rate(_runs(100, llm_error=20, process_lost=5), ("llm_error",))
    assert rate == 0.2


def test_class_rate_counts_every_code_of_the_class():
    rate = class_rate(_runs(100, llm_error=20, process_lost=5),
                      ("llm_error", "process_lost"))
    assert rate == 0.25


def test_class_rate_is_unknown_below_the_minimum_run_count():
    # Absolute Zahlen sind wertlos, wenn die Laufzahl schwankt -- und eine
    # Rate aus 9 Laeufen ist keine Aussage.
    assert class_rate(_runs(9, llm_error=9), ("llm_error",)) is None
    assert MIN_RUNS_FOR_VERDICT == 10


def test_class_rate_is_zero_when_the_class_never_fired():
    assert class_rate(_runs(50, llm_error=10), ("process_lost",)) == 0.0


def test_change_and_halved_rate_is_fixed():
    assert classify_outcome(before=0.40, after=0.20, changed=True) == "behoben"


def test_the_halving_boundary_is_inclusive():
    # Die Grenze ist bewusst grob: Wirkung von Rauschen trennen, nicht
    # Feinheiten aufloesen.
    assert classify_outcome(before=0.40, after=0.20, changed=True) == "behoben"
    assert classify_outcome(before=0.40, after=0.21, changed=True) == "wirkungslos"


def test_change_without_improvement_means_the_diagnosis_was_wrong():
    assert classify_outcome(before=0.40, after=0.38, changed=True) == "wirkungslos"


def test_no_change_and_persisting_errors_means_ignored():
    assert classify_outcome(before=0.40, after=0.38, changed=False) == "ignoriert"


def test_no_change_but_errors_vanished_means_the_finding_was_noise():
    # Das wichtigste Lernsignal: der Befund haette nie kommen duerfen.
    assert classify_outcome(before=0.40, after=0.05, changed=False) == "rauschen"


def test_missing_data_on_either_side_is_unknown():
    assert classify_outcome(before=None, after=0.2, changed=True) == "unklar"
    assert classify_outcome(before=0.4, after=None, changed=True) == "unklar"


def test_a_zero_baseline_cannot_improve():
    # Ohne Fehler vorher gibt es nichts zu beheben -- sonst wuerde jede
    # 0->0-Messung als Erfolg gezaehlt.
    assert classify_outcome(before=0.0, after=0.0, changed=True) == "unklar"


def test_find_config_change_returns_the_first_change_after_the_finding():
    revs = [
        {"agent_id": "a1", "created_at": "2026-07-01T10:00:00+00:00",
         "after_config": {"model": "alt"}},
        {"agent_id": "a1", "created_at": "2026-07-20T10:00:00+00:00",
         "after_config": {"model": "neu"}},
        {"agent_id": "a1", "created_at": "2026-07-25T10:00:00+00:00",
         "after_config": {"model": "neuer"}},
    ]
    found = find_config_change(revs, "a1", since="2026-07-15")
    assert found["after_config"]["model"] == "neu"


def test_find_config_change_ignores_other_agents():
    revs = [{"agent_id": "a2", "created_at": "2026-07-20T10:00:00+00:00",
             "after_config": {}}]
    assert find_config_change(revs, "a1", since="2026-07-15") is None


def test_find_config_change_returns_none_when_nothing_changed_since():
    revs = [{"agent_id": "a1", "created_at": "2026-07-01T10:00:00+00:00",
             "after_config": {}}]
    assert find_config_change(revs, "a1", since="2026-07-15") is None


# --- Zusammenfuehrung -------------------------------------------------------

def test_evaluate_pairs_each_finding_with_its_outcome():
    findings = [{"agent_id": "a1", "agent_name": "CMO", "cause": "model",
                 "first_seen": "2026-07-01"}]
    runs_by_agent = {
        ("a1", "2026-07-01", "vorher"): [{"error_code": "llm_error"}] * 20 + [{"error_code": None}] * 30,
        ("a1", "2026-07-01", "nachher"): [{"error_code": "llm_error"}] * 2 + [{"error_code": None}] * 48,
    }
    revisions = [{"agent_id": "a1", "created_at": "2026-07-02T09:00:00+00:00",
                  "after_config": {"model": "neu"}}]
    out = evaluate(findings, runs_by_agent, revisions)
    assert out[0]["outcome"] == "behoben"
    assert out[0]["before"] == 0.4
    assert out[0]["changed_at"].startswith("2026-07-02")


def test_evaluate_marks_a_finding_without_telemetry_as_unknown():
    findings = [{"agent_id": "a9", "agent_name": "Weg", "cause": "model",
                 "first_seen": "2026-07-01"}]
    out = evaluate(findings, {}, [])
    assert out[0]["outcome"] == "unklar"


def test_evaluate_uses_only_the_codes_of_the_findings_cause():
    # Ein config-Befund darf nicht durch Modellfehler "geheilt" aussehen.
    findings = [{"agent_id": "a1", "agent_name": "CHO", "cause": "config",
                 "first_seen": "2026-07-01"}]
    runs_by_agent = {
        ("a1", "2026-07-01", "vorher"): [{"error_code": "max_iterations"}] * 20 + [{"error_code": None}] * 30,
        ("a1", "2026-07-01", "nachher"): [{"error_code": "max_iterations"}] * 20 + [{"error_code": None}] * 30,
    }
    out = evaluate(findings, runs_by_agent, [])
    assert out[0]["before"] == 0.4 and out[0]["after"] == 0.4
    assert out[0]["outcome"] == "ignoriert"


def test_evaluate_falls_back_to_all_codes_when_the_cause_is_unknown():
    # Altvorschlaege tragen kein `cause` -- fuer sie zaehlt jeder Fehlercode.
    findings = [{"agent_id": "a1", "agent_name": "Alt", "cause": None,
                 "first_seen": "2026-06-14"}]
    runs_by_agent = {
        ("a1", "2026-06-14", "vorher"): [{"error_code": "max_iterations"}] * 10
                          + [{"error_code": "llm_error"}] * 10 + [{"error_code": None}] * 30,
        ("a1", "2026-06-14", "nachher"): [{"error_code": None}] * 50,
    }
    out = evaluate(findings, runs_by_agent, [])
    assert out[0]["before"] == 0.4
    assert out[0]["outcome"] == "rauschen"


def test_two_findings_for_the_same_agent_use_their_own_windows():
    # WHI-3389: Der erste rueckwirkende Lauf zeigte fuer VP Engineering
    # zehn Befunde mit verschiedenen Stichtagen, aber identischen Raten --
    # der Fensterschluessel war nur (agent_id, phase) und wurde von jedem
    # weiteren Befund desselben Agenten ueberschrieben.
    findings = [
        {"agent_id": "a1", "agent_name": "VP", "cause": "model", "first_seen": "2026-06-14"},
        {"agent_id": "a1", "agent_name": "VP", "cause": "model", "first_seen": "2026-07-14"},
    ]
    runs_by_agent = {
        ("a1", "2026-06-14", "vorher"): [{"error_code": "llm_error"}] * 40 + [{"error_code": None}] * 10,
        ("a1", "2026-06-14", "nachher"): [{"error_code": "llm_error"}] * 2 + [{"error_code": None}] * 48,
        ("a1", "2026-07-14", "vorher"): [{"error_code": "llm_error"}] * 5 + [{"error_code": None}] * 45,
        ("a1", "2026-07-14", "nachher"): [{"error_code": "llm_error"}] * 25 + [{"error_code": None}] * 25,
    }
    out = evaluate(findings, runs_by_agent, [])
    assert out[0]["before"] == 0.8 and out[0]["after"] == 0.04
    assert out[1]["before"] == 0.1 and out[1]["after"] == 0.5


def test_a_rate_that_climbs_after_the_change_is_its_own_verdict():
    # Der rueckwirkende Lauf zeigte CEO 0.14 -> 0.88 und VP Engineering
    # 0.88 -> 0.62 beide als "wirkungslos". Das eine ist eine
    # Verschlechterung um das Sechsfache, das andere eine Verbesserung --
    # eine gemeinsame Klasse verschleiert genau die Faelle, die zaehlen.
    assert classify_outcome(before=0.14, after=0.88, changed=True) == "verschlechtert"
    assert classify_outcome(before=0.40, after=0.62, changed=True) == "verschlechtert"


def test_a_slight_rise_is_still_only_ineffective():
    # Rauschen soll nicht als Verschlechterung durchgehen.
    assert classify_outcome(before=0.40, after=0.44, changed=True) == "wirkungslos"


def test_deterioration_without_a_change_stays_ignored():
    # Ohne Eingriff gibt es nichts, dem man die Verschlechterung zuschreibt.
    assert classify_outcome(before=0.14, after=0.88, changed=False) == "ignoriert"


def test_resolving_an_ambiguous_agent_name_yields_nothing():
    # "Vault-Maintainer" gibt es in zwei Companies -- ein Namens-Join
    # wuerde stillschweigend den falschen Agenten treffen und die Messung
    # einem Unbeteiligten zuschreiben.
    from advisor.outcomes import resolve_agent_id
    profiles = [
        {"name": "Vault-Maintainer", "agent_id": "a1"},
        {"name": "Vault-Maintainer", "agent_id": "a2"},
        {"name": "CMO", "agent_id": "a3"},
    ]
    assert resolve_agent_id(profiles, "Vault-Maintainer") is None
    assert resolve_agent_id(profiles, "CMO") == "a3"
    assert resolve_agent_id(profiles, "Unbekannt") is None
