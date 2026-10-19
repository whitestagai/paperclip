import json, os
from cli import main

def _write_sites(tmp_path):
    p = tmp_path / "sites.json"
    p.write_text(json.dumps({"report_root": str(tmp_path/"r"), "sites": [{
        "name":"x","url":"https://x.de","wp_rest_base":"https://x.de/wp-json",
        "credential_ref":"X_WP","crawl_limit":10,"seo_plugin":"yoast"}]}))
    return str(p)

def test_approve_moves_pending_to_approved(tmp_path):
    root = tmp_path / "r" / "x"
    (root / "pending").mkdir(parents=True)
    cs = root / "pending" / "cs1.json"
    cs.write_text(json.dumps({"site":"x","changes":[]}))
    rc = main(["approve","--changeset",str(cs),"--root",str(tmp_path/"r")], {})
    assert rc == 0
    assert (root / "approved" / "cs1.json").exists()
    assert not cs.exists()

def test_apply_consumes_approved(tmp_path):
    sites = _write_sites(tmp_path)
    root = tmp_path / "r" / "x"
    (root / "approved").mkdir(parents=True)
    (root / "approved" / "cs1.json").write_text(json.dumps(
        {"site":"x","changes":[{"target":"post","id":1,"field":"seo_title","old":"a","new":"b"}]}))
    calls = []
    class C:
        def set_yoast_meta(self,*a): calls.append(a); return {}
    rc = main(["apply","--site","x","--sites",sites,"--root",str(tmp_path/"r")],
              {"X_WP_USER":"u","X_WP_PW":"p"}, client_factory=lambda site,auth: C())
    assert rc == 0
    assert calls == [(1,"seo_title","b")]
    assert (root / "applied" / "cs1.json").exists()

def test_apply_moves_failing_changeset_to_failed(tmp_path):
    sites = _write_sites(tmp_path)
    root = tmp_path / "r" / "x"
    (root / "approved").mkdir(parents=True)
    (root / "approved" / "cs1.json").write_text(json.dumps(
        {"site":"x","changes":[{"target":"post","id":1,"field":"seo_title","old":"a","new":"b"}]}))
    class C:
        def set_yoast_meta(self,*a): raise RuntimeError("boom")
    rc = main(["apply","--site","x","--sites",sites,"--root",str(tmp_path/"r")],
              {"X_WP_USER":"u","X_WP_PW":"p"}, client_factory=lambda site,auth: C())
    assert rc == 0
    assert not (root / "applied" / "cs1.json").exists()
    assert (root / "failed" / "cs1.json").exists()


def test_http_fetch_decodes_utf8_when_charset_missing():
    """Server ohne charset im Content-Type: requests raet ISO-8859-1 und macht aus
    einem UTF-8-BOM Mojibake. Wir muessen trotzdem korrekt als UTF-8 dekodieren."""
    import requests_mock
    from cli import _http_fetch
    body = "﻿# WHITESTAG\n> Beschreibung mit Umlaut: schön\n".encode("utf-8")
    with requests_mock.Mocker() as m:
        m.get("https://x.de/llms.txt", content=body,
              headers={"Content-Type": "text/plain"})   # KEIN charset
        text = _http_fetch("https://x.de/llms.txt")
    assert text.lstrip("﻿").startswith("#")
    assert "schön" in text

def test_http_fetch_respects_declared_charset():
    import requests_mock
    from cli import _http_fetch
    with requests_mock.Mocker() as m:
        m.get("https://x.de/p", content="<html>schön</html>".encode("utf-8"),
              headers={"Content-Type": "text/html; charset=UTF-8"})
        assert "schön" in _http_fetch("https://x.de/p")


def test_validate_reports_problems_and_exits_1(tmp_path, capsys):
    sites = _write_sites(tmp_path)
    cs = tmp_path / "bad.json"
    cs.write_text(json.dumps({"site":"x","changes":[
        {"target":"post","id":474,"field":"seo_title","old":None,"new":"z"*71},
        {"target":"post","id":1,"field":"body","old":None,"new":"boese"},
    ]}))
    rc = main(["validate","--site","x","--sites",sites,"--changeset",str(cs),"--no-live"], {})
    out = capsys.readouterr().out
    assert rc == 1
    assert "FEHLGESCHLAGEN" in out
    assert "Whitelist" in out and "474" in out

def test_validate_live_check_catches_forbidden_page(tmp_path, capsys):
    sites = _write_sites(tmp_path)
    cs = tmp_path / "cs.json"
    cs.write_text(json.dumps({"site":"x","changes":[
        {"target":"page","id":290,"field":"meta_description","old":None,"new":"d"*140}]}))
    class C:
        def check_editable(self, target, oid):
            return "nicht editierbar (HTTP 403 rest_forbidden_context)"
    rc = main(["validate","--site","x","--sites",sites,"--changeset",str(cs)],
              {"X_WP_USER":"u","X_WP_PW":"p"}, client_factory=lambda s,a: C())
    out = capsys.readouterr().out
    assert rc == 1
    assert "403" in out and "290" in out

def test_validate_clean_exits_0(tmp_path, capsys):
    sites = _write_sites(tmp_path)
    cs = tmp_path / "ok.json"
    cs.write_text(json.dumps({"site":"x","changes":[
        {"target":"page","id":1,"field":"meta_description","old":None,"new":"d"*140}]}))
    class C:
        def check_editable(self, t, i): return None
    rc = main(["validate","--site","x","--sites",sites,"--changeset",str(cs)],
              {"X_WP_USER":"u","X_WP_PW":"p"}, client_factory=lambda s,a: C())
    assert rc == 0
    assert "VALIDIERUNG OK" in capsys.readouterr().out


def test_resolve_fills_ids_and_writes(tmp_path):
    sites = _write_sites(tmp_path)
    cs = tmp_path / "agent.json"
    cs.write_text(json.dumps({"target_site":"x","changes":[
        {"url":"https://x.de/start/","field":"seo_title","wordpress_id":None,
         "target":"page","current":"Alt","new":"Neu"}]}))
    out = tmp_path / "resolved.json"
    class C:
        def find_id_by_slug(self, ep, slug): return 845 if (ep=="pages" and slug=="start") else None
    rc = main(["resolve","--site","x","--sites",sites,"--changeset",str(cs),"--out",str(out)],
              {"X_WP_USER":"u","X_WP_PW":"p"}, client_factory=lambda s,a: C())
    assert rc == 0
    d = json.loads(out.read_text())
    assert d["changes"][0] == {"target":"page","id":845,"field":"seo_title","old":"Alt","new":"Neu"}

def test_resolve_reports_unresolved_exit1(tmp_path, capsys):
    sites = _write_sites(tmp_path)
    cs = tmp_path / "agent.json"
    cs.write_text(json.dumps({"target_site":"x","changes":[
        {"url":"https://x.de/weg/","field":"seo_title","wordpress_id":None,
         "target":"page","current":"A","new":"B"}]}))
    class C:
        def find_id_by_slug(self, ep, slug): return None
    rc = main(["resolve","--site","x","--sites",sites,"--changeset",str(cs),"--out",str(tmp_path/"o.json")],
              {"X_WP_USER":"u","X_WP_PW":"p"}, client_factory=lambda s,a: C())
    assert rc == 1
    assert "NICHT auflösbar" in capsys.readouterr().out


def test_notify_rejects_invalid_changeset(tmp_path, capsys):
    cs = {"site": "s", "changes": [{"url": "u", "field": "NICHT_WHITELIST",
                                    "id": 1, "target": "page", "new": "x"}]}
    csf = tmp_path / "cs.json"; csf.write_text(json.dumps(cs))
    rc = main(["notify", "--site", "s", "--changeset", str(csf),
               "--approvals-dir", str(tmp_path / "appr"),
               "--list-dir", str(tmp_path / "lists"),
               "--bot-env", str(tmp_path / "bot.env"), "--chat-id", "42"],
              os.environ, pusher=_no_push, token_maker=lambda: "T")
    assert rc == 1  # validate schlägt an -> kein Push

def test_notify_valid_creates_token_and_pushes(tmp_path):
    (tmp_path / "bot.env").write_text('TELEGRAM_BOT_TOKEN="1:A"\n')
    cs = {"site": "whitestag.film", "changes": [
        {"url": "u", "field": "meta_description", "id": 1, "target": "page",
         "new": "x" * 130}]}
    csf = tmp_path / "cs.json"; csf.write_text(json.dumps(cs))
    sent = []
    rc = main(["notify", "--site", "whitestag.film", "--changeset", str(csf),
               "--approvals-dir", str(tmp_path / "appr"),
               "--list-dir", str(tmp_path / "lists"),
               "--bot-env", str(tmp_path / "bot.env"), "--chat-id", "42"],
              os.environ,
              pusher=lambda *a, **k: sent.append((a, k)), token_maker=lambda: "TOK")
    assert rc == 0
    import seo_approvals as sa
    rec = sa.load(str(tmp_path / "appr"), "TOK")
    assert rec["site"] == "whitestag.film" and rec["status"] == "pending"
    assert sent  # Push wurde ausgelöst

def _no_push(*a, **k):
    raise AssertionError("darf bei unsauberem Changeset nicht pushen")


def test_reping_pings_only_stale_once(tmp_path):
    (tmp_path / "bot.env").write_text('TELEGRAM_BOT_TOKEN="1:A"\n')
    import seo_approvals as sa
    ad = str(tmp_path / "appr")
    sa.create(ad, "film", "/c.json", "/l.txt", 5, 0, 42, token="OLD", now=0.0)
    pings = []
    rc = main(["reping", "--approvals-dir", ad, "--bot-env", str(tmp_path / "bot.env"),
               "--older-than-hours", "24"], os.environ,
              pusher=lambda *a, **k: pings.append(a), now=100000.0)
    assert rc == 0 and len(pings) == 1
    # zweiter Lauf: last_reping gesetzt -> kein zweiter Ping
    rc2 = main(["reping", "--approvals-dir", ad, "--bot-env", str(tmp_path / "bot.env"),
                "--older-than-hours", "24"], os.environ,
               pusher=lambda *a, **k: pings.append(a), now=100050.0)
    assert len(pings) == 1


def test_reping_does_not_clobber_concurrently_applied_token(tmp_path):
    """Wird der Token zwischen list_pending() und dem reping-Write vom Bot auf
    applied/rejected gesetzt (Race), darf reping den Status NICHT auf pending
    zurückdrehen und darf 'last_reping' nicht auf den bereits erledigten
    Datensatz schreiben."""
    (tmp_path / "bot.env").write_text('TELEGRAM_BOT_TOKEN="1:A"\n')
    import seo_approvals as sa
    ad = str(tmp_path / "appr")
    sa.create(ad, "film", "/c.json", "/l.txt", 5, 0, 42, token="RACE", now=0.0)

    def _pusher_flips_status(*a, **k):
        # simuliert den Bot, der den Token im Fenster zwischen Laden und
        # Zurückschreiben bereits auf 'applied' setzt
        sa.set_status(ad, "RACE", "applied")

    rc = main(["reping", "--approvals-dir", ad, "--bot-env", str(tmp_path / "bot.env"),
               "--older-than-hours", "24"], os.environ,
              pusher=_pusher_flips_status, now=100000.0)
    assert rc == 0
    rec = sa.load(ad, "RACE")
    assert rec["status"] == "applied"
    assert not rec.get("last_reping")  # reping darf den applied-Datensatz nicht anfassen


def test_resolve_corrects_target_from_where_id_found(tmp_path):
    sites = _write_sites(tmp_path)
    cs = tmp_path / "agent.json"
    # Agent labelt als 'page', Objekt ist aber ein POST
    cs.write_text(json.dumps({"target_site":"x","changes":[
        {"url":"https://x.de/news/","field":"meta_description","wordpress_id":None,
         "target":"page","current":"A","new":"d"*140}]}))
    out = tmp_path / "r.json"
    class C:
        def find_id_by_slug(self, ep, slug):
            return 4184 if ep=="posts" else None   # nur in posts
    rc = main(["resolve","--site","x","--sites",sites,"--changeset",str(cs),"--out",str(out)],
              {"X_WP_USER":"u","X_WP_PW":"p"}, client_factory=lambda s,a: C())
    assert rc == 0
    ch = json.loads(out.read_text())["changes"][0]
    assert ch["target"] == "post" and ch["id"] == 4184   # target korrigiert!
