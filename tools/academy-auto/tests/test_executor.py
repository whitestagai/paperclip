from types import SimpleNamespace
from academy_auto.intent import Intent
from academy_auto.pending import PendingRecord
from academy_auto.executor import process_intent


def _cfg():
    return SimpleNamespace(intent_path="i", pending_path="p", github_repo="o/r")


def _deps(intent, pending, notes, calls):
    return SimpleNamespace(
        read_intent=lambda p: intent,
        read_pending=lambda p: pending,
        clear_intent=lambda p: calls.append("clear"),
        open_pr=lambda cfg: (calls.append("pr"), "https://gh/pr/1")[1],
        reset_branch=lambda cfg: calls.append("reset"),
        create_issue=lambda cfg, text: (calls.append(f"issue:{text}"), 42)[1],
        notify=lambda text: notes.append(text),
    )


def _rec(run_ts="R"):
    return PendingRecord(run_ts, "committed", "T", "", "", "s", True, 5, [])


def test_no_intent():
    assert process_intent(_cfg(), _deps(None, _rec(), [], [])) == "none"


def test_approve_opens_pr():
    calls, notes = [], []
    it = Intent(ts="t", kind="approve", text="", ref_run_ts="R")
    assert process_intent(_cfg(), _deps(it, _rec("R"), notes, calls)) == "approved"
    assert "pr" in calls and "clear" in calls
    assert any("PR" in n for n in notes)


def test_stale_ref_no_action():
    calls, notes = [], []
    it = Intent(ts="t", kind="approve", text="", ref_run_ts="OLD")
    assert process_intent(_cfg(), _deps(it, _rec("NEW"), notes, calls)) == "stale"
    assert "pr" not in calls and "clear" in calls
    assert any("überholt" in n for n in notes)


def test_reject_resets():
    calls, notes = [], []
    it = Intent(ts="t", kind="reject", text="", ref_run_ts="R")
    assert process_intent(_cfg(), _deps(it, _rec("R"), notes, calls)) == "rejected"
    assert "reset" in calls


def test_direction_creates_issue():
    calls, notes = [], []
    it = Intent(ts="t", kind="direction", text="Login responsive", ref_run_ts="")
    assert process_intent(_cfg(), _deps(it, _rec("R"), notes, calls)) == "direction"
    assert "issue:Login responsive" in calls
    assert any("#42" in n for n in notes)
