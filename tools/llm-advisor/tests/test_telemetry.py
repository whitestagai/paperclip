from advisor.telemetry import aggregate_runs

ROWS = [
    # (company_id, agent_id, agent_name, error_code, status, duration_s, error)
    ("c1", "a1", "VP Engineering", "max_iterations", "failed", 880.0,
     "Max iterations (20) reached without final answer"),
    ("c1", "a1", "VP Engineering", "max_iterations", "failed", 870.0,
     "Max iterations (12) reached without final answer"),
    ("c1", "a1", "VP Engineering", None, "succeeded", 30.0, None),
    ("c1", "a2", "Sekretärin", "llm_unreachable", "failed", 5.0,
     "LM Studio nicht erreichbar: primary = http://localhost:1234"),
]


def test_aggregate_counts_per_agent():
    out = aggregate_runs(ROWS)
    a1 = next(a for a in out if a["agent_id"] == "a1")
    assert a1["max_iterations"] == 2
    assert a1["total_runs"] == 3
    assert a1["succeeded"] == 1
    assert round(a1["avg_duration_s"]) == 593


def test_aggregate_llm_unreachable():
    out = aggregate_runs(ROWS)
    a2 = next(a for a in out if a["agent_id"] == "a2")
    assert a2["llm_unreachable"] == 1
    assert a2["fail_rate"] == 1.0


# --- Klartext-Cluster (WHI-3389) -------------------------------------------
# `adapter_failed` deckte am 31.07. vier verschiedene Baustellen ab: Timeout,
# Rate-Limit, Prompt-Ueberlauf und Auth. Der Zaehler allein fuehrte in die
# Fehldiagnose "falsches Modell". Die Unterscheidung steht im Klartext.

def _row(agent, code, error):
    return ("c1", agent, "Agent", code, "failed", 1.0, error)


def test_the_dominant_plaintext_error_is_reported():
    rows = [_row("a1", "adapter_failed", "Claude run failed: Prompt is too long")
            for _ in range(3)]
    rows.append(_row("a1", "adapter_failed", "Claude run failed: Request timed out"))
    top = aggregate_runs(rows)[0]["top_errors"]
    assert top[0]["count"] == 3
    assert "Prompt is too long" in top[0]["sample"]
    assert top[0]["code"] == "adapter_failed"


def test_variable_parts_do_not_split_one_cluster():
    # Dieselbe Ursache, unterschiedliche Zahlen/IDs im Text.
    rows = [
        _row("a1", "llm_error", "LM Studio API error 500: run 3f2a-11 after 8000ms"),
        _row("a1", "llm_error", "LM Studio API error 500: run 9c1b-77 after 4500ms"),
        _row("a1", "llm_error", "LM Studio API error 500: run 0ab3-92 after 200ms"),
    ]
    top = aggregate_runs(rows)[0]["top_errors"]
    assert len(top) == 1
    assert top[0]["count"] == 3


def test_distinct_failures_stay_distinct():
    rows = [
        _row("a1", "adapter_failed", "Claude run failed: Prompt is too long"),
        _row("a1", "adapter_failed", "Claude run failed: Request timed out"),
    ]
    top = aggregate_runs(rows)[0]["top_errors"]
    assert len(top) == 2


def test_clusters_are_reported_per_error_code():
    # Derselbe Text unter zwei Codes bleibt getrennt -- sonst verschwindet,
    # welcher Code welche Bedeutung hatte.
    rows = [
        _row("a1", "adapter_failed", "Server is temporarily limiting requests"),
        _row("a1", "process_lost", "Server is temporarily limiting requests"),
    ]
    top = aggregate_runs(rows)[0]["top_errors"]
    assert {t["code"] for t in top} == {"adapter_failed", "process_lost"}


def test_runs_without_an_error_text_are_not_clustered():
    rows = [_row("a1", "process_lost", None), _row("a1", "process_lost", "")]
    assert aggregate_runs(rows)[0]["top_errors"] == []


def test_successful_runs_never_enter_the_clusters():
    rows = [("c1", "a1", "Agent", None, "succeeded", 1.0, "irrelevant noise")]
    assert aggregate_runs(rows)[0]["top_errors"] == []
