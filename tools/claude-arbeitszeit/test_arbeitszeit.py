import json
from datetime import date, datetime, timedelta, timezone

import arbeitszeit as az

T0 = datetime(2026, 10, 20, 8, 0, tzinfo=timezone.utc)  # 10:00 Berlin, Dienstag


def zeiten(*minuten):
    return [T0 + timedelta(minutes=m) for m in minuten]


def schreibe_sitzung(ordner, sid, cwd, minuten, entrypoint="claude-vscode"):
    ordner.mkdir(parents=True, exist_ok=True)
    zeilen = [{"type": "user", "timestamp": t.isoformat().replace("+00:00", "Z"),
               "cwd": cwd, "entrypoint": entrypoint} for t in zeiten(*minuten)]
    (ordner / f"{sid}.jsonl").write_text("\n".join(json.dumps(z) for z in zeilen))


def test_luecke_bis_zur_pause_zaehlt_mit():
    assert len(az.minuten_der_sitzung(zeiten(0, 15))) == 16


def test_laengere_luecke_ist_pause():
    assert len(az.minuten_der_sitzung(zeiten(0, 16))) == 2


def test_projekt_aus_cwd():
    mac = "/Users/w/Library/CloudStorage/SynologyDrive-Mac/Claude Code MAC"
    assert az.projekt_aus_cwd(mac + "/Paperclip") == "Paperclip"
    assert az.projekt_aus_cwd(mac + "/Paperclip/.worktrees/x") == "Paperclip"
    assert az.projekt_aus_cwd(mac + "/Apps/WHITESTAG Booker/backend") == "WHITESTAG Booker"
    assert az.projekt_aus_cwd("/Users/w/Developer/WHITESTAG.ACADEMY") == "WHITESTAG.ACADEMY"
    assert az.projekt_aus_cwd("/Volumes/TRANSPORT/Claude Code MAC/Mac Systemadministration") \
        == "Mac Systemadministration"
    assert az.projekt_aus_cwd("/Users/w/.paperclip/scripts/backup-waechter") == "Paperclip"
    assert az.projekt_aus_cwd("/private/tmp") == "Sonstiges"
    assert az.projekt_aus_cwd(None) == "Sonstiges"


def test_agentenlaeufe_werden_erkannt():
    assert az.ist_agentenlauf("sdk-cli", "/x")
    assert az.ist_agentenlauf(None, "/Users/w/.paperclip/instances/default/workspaces/a")
    assert not az.ist_agentenlauf("claude-vscode", "/Users/w/Developer/x")


def test_gleichzeitige_projekte_teilen_die_minute(tmp_path):
    q = tmp_path / "projects"
    schreibe_sitzung(q / "a", "s1", "/Users/w/Developer/A", [0, 9])
    schreibe_sitzung(q / "b", "s2", "/Users/w/Developer/B", [5, 9])
    schreibe_sitzung(q / "c", "agent", "/Users/w/Developer/C", [0, 9], entrypoint="sdk-cli")
    db = az.oeffne_register(str(tmp_path / "r.sqlite"))
    assert az.lies_ein(db, str(q)) == (2, 1)
    tag = az.minuten_je_tag_und_projekt(db, date(2026, 10, 20), date(2026, 10, 20))[date(2026, 10, 20)]
    assert tag["A"] == 5 + 5 * 0.5
    assert tag["B"] == 5 * 0.5
    assert sum(tag.values()) == 10


def test_kuerzere_fassung_ueberschreibt_nicht(tmp_path):
    db = az.oeffne_register(str(tmp_path / "r.sqlite"))
    lang = {"id": "s", "zeiten": zeiten(0, 5, 10), "entrypoint": None, "cwd": "/Users/w/Developer/A"}
    kurz = {"id": "s", "zeiten": zeiten(0), "entrypoint": None, "cwd": "/Users/w/Developer/A"}
    assert az.uebernimm(db, lang)
    assert not az.uebernimm(db, kurz)
    tag = az.minuten_je_tag_und_projekt(db, date(2026, 10, 20), date(2026, 10, 20))
    assert tag[date(2026, 10, 20)]["A"] == 11


def test_zeitraeume_woche_ab_montag():
    p = {k: (von, bis) for k, _, von, bis in az.zeitraeume(date(2026, 10, 25))}
    assert p["tag"] == (date(2026, 10, 25), date(2026, 10, 25))
    assert p["woche"] == (date(2026, 10, 19), date(2026, 10, 25))
    assert p["monat"][0] == date(2026, 10, 1)
    assert p["jahr"][0] == date(2026, 1, 1)


def test_tagesgrenze_berlin(tmp_path):
    # 22:30 UTC am 20.10. ist 00:30 Berliner Zeit am 21.10.
    db = az.oeffne_register(str(tmp_path / "r.sqlite"))
    t = datetime(2026, 10, 20, 22, 30, tzinfo=timezone.utc)
    az.uebernimm(db, {"id": "n", "zeiten": [t, t + timedelta(minutes=4)], "entrypoint": None,
                      "cwd": "/Users/w/Developer/A"})
    tage = az.minuten_je_tag_und_projekt(db, date(2026, 10, 20), date(2026, 10, 21))
    assert date(2026, 10, 20) not in tage
    assert tage[date(2026, 10, 21)]["A"] == 5


def test_vault_chats_nach_erstem_ordner(tmp_path):
    (tmp_path / "Paperclip" / "projekte" / "x").mkdir(parents=True)
    (tmp_path / "Paperclip" / "projekte" / "x" / "2026-10-20 Chatverlauf A.md").write_text("")
    (tmp_path / "Paperclip" / "Notiz.md").write_text("")
    assert az.chats_im_vault(str(tmp_path)) == [(date(2026, 10, 20), "Paperclip")]


def test_mail_rendert(tmp_path):
    db = az.oeffne_register(str(tmp_path / "r.sqlite"))
    az.uebernimm(db, {"id": "s", "zeiten": zeiten(0, 10), "entrypoint": None,
                      "cwd": "/Users/w/Developer/A"})
    a = az.auswerten(db, date(2026, 10, 20), [(date(2026, 10, 20), "A")])
    html = az.html_mail(a)
    assert "0:11 h" in html and "100 %" in html
    assert "gestern 0:11 h" in az.betreff(a)
