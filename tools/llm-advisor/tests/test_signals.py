"""Regel-Kern: trennt Config-Ursachen von Modell-Ursachen (WHI-3362)."""
from advisor.signals import classify_signals, check_target, annotate_profiles


def _tel(**kw):
    base = {"max_iterations": 0, "timeout": 0, "llm_unreachable": 0,
            "llm_error": 0, "adapter_failed": 0, "process_lost": 0,
            "fail_rate": 0.0, "avg_duration_s": 0.0, "total_runs": 50}
    base.update(kw)
    return base


def test_max_iterations_is_a_config_signal_not_a_model_signal():
    # WHI-3348: CHO hatte 37x max_iterations bei maxIterations=12.
    verdict = classify_signals(_tel(max_iterations=37, fail_rate=0.41),
                               {"max_iterations": 12})
    assert verdict["cause"] == "config"
    assert verdict["model_change_allowed"] is False


def test_llm_unreachable_is_a_model_signal():
    verdict = classify_signals(_tel(llm_unreachable=9, llm_error=4, fail_rate=0.3),
                               {"adapter_type": "lmstudio_local"})
    assert verdict["cause"] == "model"
    assert verdict["model_change_allowed"] is True


def test_model_signals_on_a_claude_local_agent_do_not_justify_a_model_change():
    # WHI-3389: Der Advisor schlug fuer den Online-Rechercheur (claude_local)
    # claude-sonnet-4-6 -> qwen3.6-35b-a3b-mlx vor. apply_proposal.py prueft
    # das Ziel gegen /v1/models -- den LM-Studio-Katalog -- und schreibt es in
    # adapterConfig.model. Bei einem Claude-Adapter ist beides wirkungslos.
    verdict = classify_signals(_tel(adapter_failed=14, fail_rate=0.74),
                               {"adapter_type": "claude_local"})
    assert verdict["cause"] == "adapter"
    assert verdict["model_change_allowed"] is False


def test_adapter_cause_names_the_codes_instead_of_blaming_the_model():
    verdict = classify_signals(_tel(adapter_failed=4, process_lost=9),
                               {"adapter_type": "claude_local"})
    assert any("claude_local" in h for h in verdict["hints"])
    assert any("adapter_failed" in h and "process_lost" in h for h in verdict["hints"])


def test_config_cause_survives_on_a_foreign_adapter():
    # Eine Config-Aenderung ist auch bei claude_local ausfuehrbar --
    # nur der Modellwechsel ist es nicht.
    verdict = classify_signals(_tel(max_iterations=37),
                               {"adapter_type": "claude_local", "max_iterations": 12})
    assert verdict["cause"] == "config"
    assert verdict["model_change_allowed"] is False


def test_unknown_adapter_type_is_treated_as_foreign():
    # Fail-closed: nur wo apply_proposal.py nachweislich wirkt, darf ein
    # Modellwechsel vorgeschlagen werden.
    verdict = classify_signals(_tel(llm_error=7), {})
    assert verdict["model_change_allowed"] is False


def test_a_healthy_agent_stays_below_the_pain_threshold():
    # WHI-3389: Der CMO wurde bei 325 Runs, 319 Erfolgen und 6 codierten
    # Fehlern zum Modellwechsel vorgeschlagen. 1,8% ist Rauschen, kein Schmerz.
    verdict = classify_signals(
        _tel(process_lost=5, llm_unreachable=1, fail_rate=0.018, total_runs=325),
        {"adapter_type": "lmstudio_local"})
    assert verdict["actionable"] is False
    assert verdict["model_change_allowed"] is False


def test_threshold_needs_volume_not_only_a_bad_rate():
    # Drei Fehler bei fünf Runs sind eine hohe Quote auf duenner Datenbasis.
    verdict = classify_signals(_tel(llm_error=3, fail_rate=0.6, total_runs=5),
                               {"adapter_type": "lmstudio_local"})
    assert verdict["actionable"] is False


def test_threshold_needs_a_bad_rate_not_only_volume():
    # 12 Fehler auf 400 Runs sind 3% -- der Agent laeuft im Wesentlichen.
    verdict = classify_signals(_tel(llm_error=12, fail_rate=0.03, total_runs=400),
                               {"adapter_type": "lmstudio_local"})
    assert verdict["actionable"] is False


def test_a_genuinely_broken_agent_remains_actionable():
    verdict = classify_signals(_tel(llm_error=40, fail_rate=0.55, total_runs=80),
                               {"adapter_type": "lmstudio_local"})
    assert verdict["actionable"] is True
    assert verdict["model_change_allowed"] is True


def test_below_threshold_is_explained_in_the_hints():
    verdict = classify_signals(
        _tel(process_lost=5, llm_unreachable=1, fail_rate=0.018, total_runs=325),
        {"adapter_type": "lmstudio_local"})
    assert any("unauffaellig" in h or "Schwelle" in h for h in verdict["hints"])


def test_a_rate_limit_is_an_upstream_cause_not_a_model_cause():
    # 106x claude_transient_upstream im 7-Tage-Fenster -- der zweithaeufigste
    # Fehlercode ueberhaupt, und bis WHI-3389 fuer den Advisor unsichtbar.
    verdict = classify_signals(
        _tel(claude_transient_upstream=57, process_lost=9, fail_rate=0.893,
             total_runs=75),
        {"adapter_type": "claude_local"})
    assert verdict["cause"] == "upstream"
    assert verdict["model_change_allowed"] is False


def test_upstream_errors_count_towards_the_threshold():
    # Sonst gilt ein Agent, der zu 89% scheitert, als unauffaellig -- weil
    # der dominante Code nicht mitgezaehlt wird. Schweigen waere hier
    # schlimmer als ein falscher Vorschlag.
    verdict = classify_signals(
        _tel(claude_transient_upstream=57, process_lost=9, fail_rate=0.893,
             total_runs=75),
        {"adapter_type": "claude_local"})
    assert verdict["actionable"] is True


def test_upstream_hint_points_at_the_account_not_at_the_model():
    verdict = classify_signals(
        _tel(claude_transient_upstream=57, fail_rate=0.893, total_runs=75),
        {"adapter_type": "claude_local"})
    assert any("claude_transient_upstream" in h for h in verdict["hints"])
    assert not any("Modellwechsel ist hier" in h for h in verdict["hints"])


def test_lifecycle_codes_are_not_failures():
    # cancelled / issue_terminal_status sind normaler Ablauf, keine Stoerung.
    verdict = classify_signals(
        _tel(cancelled=12, issue_terminal_status=12, fail_rate=0.4), {})
    assert verdict["cause"] == "none"
    assert verdict["actionable"] is False


def test_high_fail_rate_alone_justifies_nothing():
    verdict = classify_signals(_tel(fail_rate=0.9), {})
    assert verdict["cause"] == "none"
    assert verdict["model_change_allowed"] is False


def test_config_hint_names_the_actual_limit():
    verdict = classify_signals(_tel(max_iterations=23), {"max_iterations": 10})
    assert any("maxIterations=10" in h for h in verdict["hints"])


def test_mixed_signals_report_both_and_config_wins_when_dominant():
    verdict = classify_signals(_tel(max_iterations=37, timeout=8, llm_error=5),
                               {"max_iterations": 12})
    assert verdict["cause"] == "config"
    assert verdict["config_signals"] == {"max_iterations": 37, "timeout": 8}
    assert verdict["model_signals"] == {"llm_error": 5}


def test_target_on_a_device_that_is_not_always_on_is_blocked_without_fallback():
    # WHI-3348: google/gemma-4-31b-qat liegt auf der RTX, die nachts aus ist.
    warnings = check_target(
        target={"model_key": "google/gemma-4-31b-qat", "device": "RTX Pro 6000",
                "always_on": False, "context_length": 65024},
        source={"model_key": "qwen3.6-35b-a3b-mlx", "device": "Local",
                "always_on": True, "context_length": 98304},
    )
    assert any(w["kind"] == "device_not_always_on" for w in warnings)
    assert any(w["blocking"] for w in warnings)


def test_fallback_on_an_always_on_device_downgrades_the_block_to_a_note():
    # Der lmstudio-Adapter schaltet bei kind="model" auf fallbackModel um
    # (llm-client.ts classifyHttpError, execute.ts maybeSwitchToFallback).
    # Liegt der Fallback auf einem 24/7-Geraet, degradiert der Agent nachts
    # statt auszufallen -- das ist kein Ausschlussgrund.
    warnings = check_target(
        target={"model_key": "qwen/qwen3-coder-next", "device": "RTX Pro 6000",
                "always_on": False, "context_length": 131328},
        source={"model_key": "qwen/qwen3-coder-30b", "device": "Local",
                "always_on": True, "context_length": 65536},
        fallback={"model_key": "qwen/qwen3-coder-30b", "device": "Local",
                  "always_on": True, "context_length": 65536},
    )
    dev = next(w for w in warnings if w["kind"] == "device_not_always_on")
    assert dev["blocking"] is False
    assert "qwen/qwen3-coder-30b" in dev["detail"]


def test_fallback_on_the_same_dark_device_does_not_rescue_the_target():
    warnings = check_target(
        target={"model_key": "a", "device": "RTX Pro 6000", "always_on": False},
        source={"model_key": "b", "device": "Local", "always_on": True},
        fallback={"model_key": "c", "device": "RTX Pro 6000", "always_on": False},
    )
    assert next(w for w in warnings if w["kind"] == "device_not_always_on")["blocking"] is True


def test_context_shrink_is_reported():
    warnings = check_target(
        target={"model_key": "b", "device": "Local", "always_on": True,
                "context_length": 65024},
        source={"model_key": "a", "device": "Local", "always_on": True,
                "context_length": 262144},
    )
    ctx = next(w for w in warnings if w["kind"] == "context_shrink")
    assert "262144" in ctx["detail"] and "65024" in ctx["detail"]


def test_equivalent_target_produces_no_warnings():
    same = {"model_key": "a", "device": "Local", "always_on": True,
            "context_length": 262144}
    assert check_target(target=dict(same, model_key="b"), source=same) == []


PROFILE = {"agent_id": "a1", "name": "CHO", "model": "qwen3.6-35b-a3b-mlx",
           "max_iterations": 12, "timeout_ms": 300000}
LOADED = {"qwen3.6-35b-a3b-mlx": {"model_key": "qwen3.6-35b-a3b-mlx",
                                  "device": "Local", "always_on": True,
                                  "context_length": 98304}}


def test_annotated_profile_resolves_the_fallback_model_too():
    profs = annotate_profiles(
        [dict(PROFILE, fallback_model="gemma-4-31b-it-mlx")],
        {},
        dict(LOADED, **{"gemma-4-31b-it-mlx": {"model_key": "gemma-4-31b-it-mlx",
                                               "device": "MacbookM5Mx128",
                                               "always_on": True,
                                               "context_length": 262144}}),
    )
    assert profs[0]["fallback_model_info"]["device"] == "MacbookM5Mx128"


def test_annotated_profile_gets_signals_and_running_model_facts():
    profs = annotate_profiles(
        [dict(PROFILE)],
        {"a1": _tel(max_iterations=37, timeout=8, fail_rate=0.41)},
        LOADED,
    )
    p = profs[0]
    assert p["signals"]["cause"] == "config"
    assert p["running_model"]["device"] == "Local"
    assert p["running_model"]["context_length"] == 98304


def test_agent_without_telemetry_is_annotated_as_no_cause():
    p = annotate_profiles([dict(PROFILE)], {}, LOADED)[0]
    assert p["signals"]["cause"] == "none"


def test_model_that_is_not_loaded_leaves_running_model_empty():
    p = annotate_profiles([dict(PROFILE, model="nicht-geladen")], {}, LOADED)[0]
    assert p["running_model"] is None

# --- Turn-/Iterationsgrenze ist adapterabhaengig (01.08.2026) -----------------
# Belegt: der claude-local-Adapter liest ausschliesslich `maxTurnsPerRun`
# (packages/adapters/claude-local/src/server/execute.ts:360 + :666 -- Default 0,
# dann wird --max-turns gar nicht uebergeben). `maxIterations` liest nur der
# lmstudio-Adapter; dessen Fehlertext lautet "Max iterations (N) reached".
# Ein Hinweis "maxIterations anheben" ist bei claude_local also wirkungslos.

def test_max_turns_exhausted_is_a_config_signal():
    """Seit maxTurnsPerRun gesetzt ist, koennen claude_local-Agenten das
    Turn-Limit ueberhaupt erst erreichen. Vorher war der Code unerreichbar."""
    verdict = classify_signals(_tel(max_turns_exhausted=14, fail_rate=0.3),
                               {"adapter_type": "claude_local",
                                "max_turns_per_run": 80})
    assert verdict["cause"] == "config"
    assert verdict["model_change_allowed"] is False


def test_turn_limit_hint_names_the_knob_that_claude_local_actually_reads():
    verdict = classify_signals(_tel(max_turns_exhausted=14, fail_rate=0.3),
                               {"adapter_type": "claude_local",
                                "max_turns_per_run": 80})
    hint = " ".join(verdict["hints"])
    assert "maxTurnsPerRun" in hint
    assert "80" in hint


def test_iteration_hint_on_claude_local_does_not_advise_raising_a_dead_field():
    """Der Advisor liest ein 30-Tage-Fenster. Ein Agent, der von lmstudio_local
    auf claude_local umgestellt wurde, schleppt seine alten max_iterations-
    Fehler mit -- der Rat 'maxIterations anheben' geht dann ins Leere."""
    verdict = classify_signals(_tel(max_iterations=6, fail_rate=0.3),
                               {"adapter_type": "claude_local",
                                "max_iterations": 40})
    hint = " ".join(verdict["hints"])
    assert "Limit anheben" not in hint
    assert "maxTurnsPerRun" in hint


def test_iteration_hint_stays_unchanged_for_lmstudio_local():
    verdict = classify_signals(_tel(max_iterations=37, fail_rate=0.41),
                               {"adapter_type": "lmstudio_local",
                                "max_iterations": 12})
    hint = " ".join(verdict["hints"])
    assert "maxIterations=12" in hint
    assert "Limit anheben" in hint
