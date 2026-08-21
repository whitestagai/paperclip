"""Trennt Config-Ursachen von Modell-Ursachen (WHI-3362).

Hintergrund WHI-3348: Der Advisor sah je Agent nur das zugewiesene Modell.
Auf `max_iterations`-Fehler konnte er deshalb nur mit einem Modellwechsel
antworten, obwohl die Ursache das Iterationslimit im adapterConfig war.
Diese Klassifizierung gehoert in Code, nicht in den Prompt: sie ist
deterministisch und darf nicht je nach Nacht anders ausfallen.
"""

# Fehler, die von der Agenten-Konfiguration verursacht werden. Ein
# Modellwechsel heilt sie nicht -- er verschiebt sie nur.
# `max_turns_exhausted` ist seit dem 01.08.2026 ueberhaupt erst erreichbar:
# vorher war bei allen claude_local-Agenten kein Turn-Limit gesetzt, und der
# Adapter uebergibt --max-turns nur bei einem Wert > 0.
CONFIG_CODES = ("max_iterations", "timeout", "max_turns_exhausted")

# Welchen Knopf liest welcher Adapter? Das ist keine Geschmacksfrage:
#   lmstudio_local -> maxIterations  (Fehlertext "Max iterations (N) reached")
#   claude_local   -> maxTurnsPerRun (packages/adapters/claude-local/src/server/
#                     execute.ts:360 liest NUR maxTurnsPerRun; :666 uebergibt
#                     --max-turns erst ab > 0. maxIterations landet dort im
#                     .catchall() des Schemas: gespeichert, nie gelesen.)
# Ein Rat "maxIterations anheben" ist bei claude_local also wirkungslos.
TURN_LIMIT_CODES = ("max_iterations", "max_turns_exhausted")
ITERATION_LIMIT_ADAPTER = "lmstudio_local"
TURN_LIMIT_ADAPTER = "claude_local"

# Fehler, die tatsaechlich am Modell, seiner Verfuegbarkeit oder am
# Adapter haengen. Nur diese rechtfertigen einen Modellwechsel.
MODEL_CODES = ("llm_unreachable", "llm_error", "adapter_failed", "process_lost")

# Fehler der Gegenstelle: Rate-Limit des Accounts, abgelaufene Anmeldung.
# Sie haengen weder am Modell noch an der Agenten-Config und werden von
# keinem Modellwechsel geheilt. `claude_transient_upstream` war mit 106
# Vorkommen im 7-Tage-Fenster der zweithaeufigste Code ueberhaupt und
# wurde bis WHI-3389 gar nicht gezaehlt -- wodurch ein zu 89% scheiternder
# Agent als unauffaellig galt.
UPSTREAM_CODES = ("claude_transient_upstream", "claude_auth_required")

# Nicht gelistete Codes (cancelled, issue_terminal_status,
# issue_dependencies_blocked, issue_reassigned) sind normaler Ablauf und
# ausdruecklich keine Stoerung.

# Der einzige Adapter, dessen Modell-Zuweisung der Advisor ueberhaupt
# stellen kann: apply_proposal.py prueft das Ziel gegen /v1/models (den
# LM-Studio-Katalog) und schreibt es nach adapterConfig.model. Bei jedem
# anderen Adapter ist ein Modellwechsel-Vorschlag wirkungslos (WHI-3389).
MODEL_ASSIGNABLE_ADAPTER = "lmstudio_local"

# Schmerzschwelle. Unterhalb davon ist ein Agent unauffaellig und bekommt
# keinen Vorschlag -- egal wie gut ein Alternativmodell aussieht. Beide
# Bedingungen muessen erfuellt sein: die Quote sichert Relevanz, die
# absolute Zahl sichert die Datenbasis. Der CMO wurde am 31.07. bei
# fail_rate=0.018 und 6 codierten Fehlern vorgeschlagen (WHI-3389).
MIN_FAIL_RATE = 0.10
MIN_CODED_ERRORS = 10


def classify_signals(telemetry, config):
    """Ordnet die Fehlerverteilung eines Agenten einer Ursache zu.

    `telemetry`: aggregierter Eintrag aus advisor.telemetry.aggregate_runs.
    `config`: Profil-Felder aus advisor.agents.agent_profiles
              (`max_iterations`, `timeout_ms`, ...).

    Gibt `cause` ("config" | "model" | "none"), die beteiligten Signale und
    `model_change_allowed` zurueck. `fail_rate` allein ist nie eine Ursache --
    es ist ein Aggregat und sagt nichts darueber, was gescheitert ist.
    """
    config_signals = {c: telemetry.get(c) or 0 for c in CONFIG_CODES}
    config_signals = {c: n for c, n in config_signals.items() if n}
    model_signals = {c: telemetry.get(c) or 0 for c in MODEL_CODES}
    model_signals = {c: n for c, n in model_signals.items() if n}
    upstream_signals = {c: telemetry.get(c) or 0 for c in UPSTREAM_CODES}
    upstream_signals = {c: n for c, n in upstream_signals.items() if n}

    config_weight = sum(config_signals.values())
    model_weight = sum(model_signals.values())
    upstream_weight = sum(upstream_signals.values())

    # Fail-closed: nur ein lmstudio_local-Agent ist ueberhaupt umzuweisen.
    # Bei jedem anderen Adapter bedeuten dieselben Fehlercodes etwas
    # anderes -- `adapter_failed` ist dort Timeout, Rate-Limit oder
    # Prompt-Ueberlauf des Fremdprozesses, kein Urteil ueber das Modell.
    adapter_type = config.get("adapter_type")
    model_assignable = adapter_type == MODEL_ASSIGNABLE_ADAPTER

    if not config_weight and not model_weight and not upstream_weight:
        cause = "none"
    elif config_weight >= max(model_weight, upstream_weight):
        cause = "config"
    elif upstream_weight >= model_weight:
        cause = "upstream"
    elif model_assignable:
        cause = "model"
    else:
        cause = "adapter"

    coded_errors = config_weight + model_weight + upstream_weight
    fail_rate = telemetry.get("fail_rate") or 0.0
    actionable = coded_errors >= MIN_CODED_ERRORS and fail_rate >= MIN_FAIL_RATE

    return {
        "cause": cause,
        "config_signals": config_signals,
        "model_signals": model_signals,
        "upstream_signals": upstream_signals,
        "actionable": actionable,
        "model_change_allowed": cause == "model" and actionable,
        "hints": _hints(cause, config_signals, model_signals, upstream_signals,
                        telemetry, config, actionable, coded_errors),
    }


def _hints(cause, config_signals, model_signals, upstream_signals, telemetry,
           config, actionable=True, coded_errors=0):
    hints = []
    limit = config.get("max_iterations")
    if cause == "upstream":
        codes = ", ".join(f"{c}={n}x" for c, n in sorted(upstream_signals.items()))
        hints.append(
            f"Gegenstelle, nicht Modell ({codes}). Rate-Limit des Accounts "
            "oder abgelaufene Anmeldung -- kein Modellwechsel und keine "
            "Config-Aenderung heilt das. Zustaendig ist das Konto bzw. die "
            "Aufrufrate der Routinen; der Klartext steht in top_errors."
        )
    if not actionable and coded_errors:
        hints.append(
            f"unauffaellig: {coded_errors} codierte Fehler bei fail_rate="
            f"{telemetry.get('fail_rate') or 0.0} "
            f"({telemetry.get('total_runs') or 0} Runs) -- unter der Schwelle "
            f"({MIN_CODED_ERRORS} Fehler UND fail_rate>={MIN_FAIL_RATE}). "
            "Kein Vorschlag. Ein laufender Agent wird nicht umgestellt, weil "
            "ein anderes Modell theoretisch besser waere."
        )
    if cause == "adapter":
        codes = ", ".join(f"{c}={n}x" for c, n in sorted(model_signals.items()))
        hints.append(
            f"adapter_type={config.get('adapter_type') or 'unbekannt'} -- kein "
            f"lmstudio_local-Agent. Die Fehler ({codes}) stammen aus dem "
            "Fremdprozess, nicht aus einer Modellwahl: dort steht dieselbe "
            "Codegruppe fuer Timeout, Rate-Limit, Prompt-Ueberlauf oder einen "
            "verlorenen Prozess. Ein Modellwechsel ist hier weder ausfuehrbar "
            "(apply_proposal.py schreibt adapterConfig.model gegen den "
            "LM-Studio-Katalog) noch wirksam. Naechster Schritt ist der "
            "Klartext in heartbeat_runs.error, nicht der Modellkatalog."
        )
    turn_signals = {c: n for c, n in config_signals.items() if c in TURN_LIMIT_CODES}
    if turn_signals:
        codes = ", ".join(f"{c}={n}x" for c, n in sorted(turn_signals.items()))
        if config.get("adapter_type") == TURN_LIMIT_ADAPTER:
            turns = config.get("max_turns_per_run")
            hint = (
                f"Lauf-Limit ({codes}) im Telemetrie-Fenster. Bei claude_local zaehlt "
                f"ausschliesslich maxTurnsPerRun="
                f"{turns if turns is not None else 'unbekannt (= kein Limit)'}; "
                "maxIterations liest dieser Adapter nicht."
            )
            if "max_iterations" in turn_signals:
                # Das Fenster ist 30 Tage breit -- ein umgestellter Agent
                # schleppt die Fehler seines frueheren Adapters mit.
                hint += (
                    " Die max_iterations-Fehler stammen aus einer frueheren "
                    "Adapter-Zuordnung und sagen nichts ueber die heutige Config."
                )
            hints.append(hint)
        else:
            hints.append(
                f"max_iterations={turn_signals.get('max_iterations', 0)}x im Telemetrie-Fenster; "
                f"aktuell gesetzt ist maxIterations={limit if limit is not None else 'unbekannt'} "
                "(im Fenster kann ein anderer Wert gegolten haben). Limit anheben, bevor ein "
                "Modellwechsel erwogen wird. Bleibt der Fehler nach der Anhebung bestehen, ist der "
                "naechste Schritt eine Aufgaben-/Prompt-Analyse -- eine Endlosschleife ist kein "
                "Beleg fuer ein zu schwaches Modell."
            )
    if "timeout" in config_signals:
        timeout_ms = config.get("timeout_ms")
        hints.append(
            f"timeout={config_signals['timeout']}x bei timeoutMs="
            f"{timeout_ms if timeout_ms is not None else 'unbekannt'} und avg_duration_s="
            f"{round(telemetry.get('avg_duration_s') or 0, 1)}. Achtung: avg_duration_s ist die "
            "Run-Dauer, nicht die Dauer eines einzelnen LLM-Calls."
        )
    if cause == "none" and (telemetry.get("fail_rate") or 0) > 0:
        hints.append(
            f"fail_rate={telemetry.get('fail_rate')} ohne zuordenbaren Fehlercode -- kein "
            "Vorschlag. fail_rate ist ein Aggregat, keine Ursache."
        )
    return hints


def annotate_profiles(profiles, telemetry_by_agent, loaded_by_key):
    """Haengt Ursachen-Urteil und Fakten zum laufenden Modell an jedes Profil.

    `loaded_by_key`: model_key -> Eintrag aus advisor.resources.parse_models
    (nur geladene Modelle, also inkl. Geraet und Kontextlaenge).
    """
    for p in profiles:
        telemetry = telemetry_by_agent.get(p.get("agent_id")) or {}
        p["signals"] = classify_signals(telemetry, p)
        p["running_model"] = loaded_by_key.get(p.get("model")) or None
        p["fallback_model_info"] = loaded_by_key.get(p.get("fallback_model")) or None
    return profiles


def check_target(target, source, fallback=None):
    """Prueft ein Ziel-Modell gegen das Ist-Modell auf harte Nachteile.

    `target`/`source`/`fallback` sind Eintraege aus advisor.resources.parse_models.
    Eine `blocking`-Warnung bedeutet: der Vorschlag darf so nicht gestellt werden.
    """
    warnings = []

    if target.get("always_on") is False:
        # Der lmstudio-Adapter klassifiziert ein nicht ladbares Modell als
        # kind="model" und schaltet dann auf fallbackModel um (llm-client.ts
        # classifyHttpError -> execute.ts maybeSwitchToFallback). Liegt der
        # Fallback auf einem 24/7-Geraet, degradiert der Agent nachts, statt
        # auszufallen -- dann ist das Geraet ein Hinweis, kein Ausschluss.
        rescued = bool(fallback) and fallback.get("always_on") is True
        detail = (
            f"{target.get('model_key')} liegt auf {target.get('device')} -- "
            "nicht durchgaengig verfuegbar."
        )
        if rescued:
            detail += (
                f" Abgesichert: Fallback {fallback.get('model_key')} auf "
                f"{fallback.get('device')}. Der Agent degradiert nachts auf den Fallback. "
                "Voraussetzung ist ein gesetztes fallbackUrl -- ohne das greift der "
                "Failover im Adapter nicht."
            )
        else:
            detail += (
                " Kein Fallback auf einem durchgaengig verfuegbaren Geraet -- Agenten mit "
                "Nacht-Last wuerden in llm_unreachable laufen."
            )
        warnings.append({
            "kind": "device_not_always_on",
            "blocking": not rescued,
            "detail": detail,
        })

    src_ctx, tgt_ctx = source.get("context_length"), target.get("context_length")
    if src_ctx and tgt_ctx and tgt_ctx < src_ctx:
        warnings.append({
            "kind": "context_shrink",
            "blocking": False,
            "detail": (
                f"Geladene Kontextlaenge sinkt von {src_ctx} auf {tgt_ctx}. "
                "Auf Fremdgeraeten ist ctx von hier aus nicht setzbar -- der Load muss "
                "am Zielgeraet laufen."
            ),
        })

    return warnings
