# tools/voice-echo-bot/test_academy_bridge.py
import academy_bridge as ab


def test_parse_callback_approve():
    assert ab.parse_callback("academy:approve:2026-07-25T02:00:03") == ("approve", "2026-07-25T02:00:03")


def test_parse_callback_reject():
    assert ab.parse_callback("academy:reject:R") == ("reject", "R")


def test_parse_callback_foreign_returns_none():
    assert ab.parse_callback("issue:confirm:WHI-1") is None
    assert ab.parse_callback("") is None


def test_is_academy_reply():
    assert ab.is_academy_reply("🎓 Academy-Auto — Tagesstand\n...") is True
    assert ab.is_academy_reply("irgendeine andere Nachricht") is False


def test_build_intent_dict():
    d = ab.build_intent_dict("direction", "Login responsive", "", "2026-07-25T08:00:00")
    assert d == {"ts": "2026-07-25T08:00:00", "kind": "direction",
                 "text": "Login responsive", "ref_run_ts": ""}


def test_write_intent_file(tmp_path):
    import json
    p = tmp_path / "intent.json"
    ab.write_intent_file(str(p), {"ts": "t", "kind": "approve", "text": "", "ref_run_ts": "R"})
    assert json.loads(p.read_text())["kind"] == "approve"


def test_write_intent_file_creates_missing_dirs(tmp_path):
    import json
    p = tmp_path / "nested" / "dir" / "intent.json"
    ab.write_intent_file(str(p), {"ts": "t", "kind": "reject", "text": "", "ref_run_ts": "R"})
    assert json.loads(p.read_text())["kind"] == "reject"


def test_trigger_executor_fails_soft_on_broken_dir():
    # kein Subprozess kann in einem nicht existenten cwd starten -> darf
    # trotzdem nicht werfen (fire-and-forget, fail-soft).
    ab.trigger_executor("/definitely/does/not/exist/academy-auto")
