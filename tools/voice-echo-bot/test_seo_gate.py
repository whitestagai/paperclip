import json, os
from unittest import mock
import seo_gate

def test_parse_callback():
    assert seo_gate.parse_callback("seo:ok:ABC") == ("ok", "ABC")
    assert seo_gate.parse_callback("seo:no:XY") == ("no", "XY")
    assert seo_gate.parse_callback("other:stuff") is None
    assert seo_gate.parse_callback("") is None

def _cfg(tmp_path):
    # seo_geo_root MUSS auf tmp zeigen — sonst schreibt der Test in echte Verzeichnisse.
    return {"approvals_dir": str(tmp_path / "appr"),
            "seo_geo_venv": "/v/python", "seo_geo_cli": "/c/cli.py",
            "seo_geo_root": str(tmp_path / "sgroot"), "seo_geo_sites": "/s/sites.json"}

def test_apply_token_runs_approve_then_apply(tmp_path):
    cfg = _cfg(tmp_path)
    rec = {"token": "T", "site": "whitestag.film", "status": "pending",
           "changeset_path": "/p/cs.json", "count": 79}
    ran = []
    def runner(argv):
        ran.append(argv); return 0
    # applied/failed-Verzeichnisse simulieren — Log-Name muss zum changeset_path passen.
    sdir = os.path.expanduser(os.path.join(cfg["seo_geo_root"], "whitestag.film"))
    os.makedirs(os.path.join(sdir, "applied"), exist_ok=True)
    with open(os.path.join(sdir, "applied", "apply-log.cs.json.json"), "w") as fh:
        json.dump({"applied": [1]*79, "skipped": [], "failed": []}, fh)
    msg = seo_gate.apply_token(cfg, rec, runner=runner)
    assert any("approve" in a for a in ran[0])
    assert any("apply" in a for a in ran[1])
    assert "79" in msg and "0" in msg  # "79 angewendet, 0 Fehler"


def test_summarize_last_apply_is_scoped_to_this_changeset(tmp_path):
    sdir = tmp_path / "sdir"
    os.makedirs(sdir / "applied", exist_ok=True)
    os.makedirs(sdir / "failed", exist_ok=True)
    # Stale erfolgreicher Log eines FRÜHEREN Changesets in applied/ — darf NICHT gewinnen.
    with open(sdir / "applied" / "apply-log.OTHER.json", "w") as fh:
        json.dump({"applied": [1] * 500, "failed": []}, fh)
    # Aktueller Changeset ist in Wirklichkeit fehlgeschlagen -> Log liegt in failed/.
    with open(sdir / "failed" / "apply-log.this-changeset.json.json", "w") as fh:
        json.dump({"applied": [1] * 3, "failed": [1]}, fh)
    applied, failed = seo_gate.summarize_last_apply(str(sdir), "this-changeset.json")
    assert (applied, failed) == (3, 1)


def test_apply_token_reports_failure_not_stale_success(tmp_path):
    cfg = _cfg(tmp_path)
    rec = {"token": "T", "site": "whitestag.film", "status": "pending",
           "changeset_path": "/p/this-changeset.json", "count": 3}
    sdir = os.path.expanduser(os.path.join(cfg["seo_geo_root"], "whitestag.film"))
    os.makedirs(os.path.join(sdir, "applied"), exist_ok=True)
    os.makedirs(os.path.join(sdir, "failed"), exist_ok=True)
    # Stale erfolgreicher Log eines früheren Laufs.
    with open(os.path.join(sdir, "applied", "apply-log.OTHER.json"), "w") as fh:
        json.dump({"applied": [1] * 500, "failed": []}, fh)
    # Dieser Lauf ist fehlgeschlagen.
    with open(os.path.join(sdir, "failed", "apply-log.this-changeset.json.json"), "w") as fh:
        json.dump({"applied": [1] * 3, "failed": [1]}, fh)
    msg = seo_gate.apply_token(cfg, rec, runner=lambda a: 0)
    assert "500" not in msg
    assert "1" in msg  # 1 Fehler
    assert "⚠️" in msg or "fehlgeschlagen" in msg.lower()


def test_reject_token_moves_changeset_and_sets_status(tmp_path):
    cfg = _cfg(tmp_path)
    os.makedirs(cfg["approvals_dir"], exist_ok=True)
    sdir = tmp_path / "sgroot" / "whitestag.film"
    os.makedirs(sdir / "pending", exist_ok=True)
    cs_path = sdir / "pending" / "cs.json"
    cs_path.write_text("{}")
    token_path = os.path.join(cfg["approvals_dir"], "T.json")
    with open(token_path, "w") as fh:
        json.dump({"token": "T", "site": "whitestag.film", "status": "pending",
                    "changeset_path": str(cs_path), "count": 1}, fh)
    rec = {"token": "T", "site": "whitestag.film", "status": "pending",
           "changeset_path": str(cs_path), "count": 1}
    msg = seo_gate.reject_token(cfg, rec)
    assert (sdir / "rejected" / "cs.json").is_file()
    assert not cs_path.exists()
    with open(token_path) as fh:
        assert json.load(fh)["status"] == "rejected"
    assert "abgelehnt" in msg


def test_apply_token_stops_if_approve_fails(tmp_path):
    cfg = _cfg(tmp_path)
    rec = {"token": "T", "site": "whitestag.film", "status": "pending",
           "changeset_path": "/p/cs.json", "count": 79}
    ran = []
    def runner(argv):
        ran.append(argv)
        if "approve" in argv:
            return 2
        return 0
    msg = seo_gate.apply_token(cfg, rec, runner=runner)
    assert len(ran) == 1  # apply darf NICHT aufgerufen werden
    assert "approve" in msg.lower()
    assert "fehlgeschlagen" in msg.lower() or "2" in msg

def test_apply_token_idempotent(tmp_path):
    cfg = _cfg(tmp_path)
    rec = {"token": "T", "site": "s", "status": "applied", "count": 1}
    msg = seo_gate.apply_token(cfg, rec, runner=lambda a: 0)
    assert "bereits" in msg.lower()


def test_load_token_rejects_path_traversal(tmp_path):
    cfg = _cfg(tmp_path)
    os.makedirs(cfg["approvals_dir"], exist_ok=True)
    # Datei außerhalb von approvals_dir anlegen, die ein Traversal-Token treffen würde.
    outside = tmp_path / "evil.json"
    outside.write_text(json.dumps({"token": "evil"}))
    assert seo_gate.load_token(cfg["approvals_dir"], "../evil") is None


def test_load_token_rejects_invalid_characters(tmp_path):
    cfg = _cfg(tmp_path)
    assert seo_gate.load_token(cfg["approvals_dir"], "foo/bar") is None
    assert seo_gate.load_token(cfg["approvals_dir"], "") is None
    assert seo_gate.load_token(cfg["approvals_dir"], None) is None


def test_note_token_rejects_path_traversal(tmp_path):
    cfg = _cfg(tmp_path)
    os.makedirs(cfg["approvals_dir"], exist_ok=True)
    outside = tmp_path / "evil.json"
    outside.write_text(json.dumps({"token": "evil"}))
    seo_gate.note_token(cfg, "../evil", "hacked")
    # Datei außerhalb approvals_dir darf unangetastet bleiben.
    assert json.loads(outside.read_text()) == {"token": "evil"}


def test_parse_callback_rejects_invalid_token_chars():
    assert seo_gate.parse_callback("seo:ok:../evil") is None


def test_run_with_real_subprocess_passes_merged_env_with_wp_credentials():
    cfg = {"seo_geo_venv": "/v", "seo_geo_cli": "/c",
           "wp_env": {"WHITESTAG_DE_WP_USER": "u"}}
    captured = {}

    class FakeResult:
        returncode = 0

    def fake_run(argv, env=None, **kwargs):
        captured["argv"] = argv
        captured["env"] = env
        return FakeResult()

    with mock.patch("seo_gate.subprocess.run", side_effect=fake_run):
        rc = seo_gate._run(cfg, None, ["apply"])
    assert rc == 0
    assert captured["env"]["WHITESTAG_DE_WP_USER"] == "u"
    assert "PATH" in captured["env"]
