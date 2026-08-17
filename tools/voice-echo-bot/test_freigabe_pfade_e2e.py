# tools/voice-echo-bot/test_freigabe_pfade_e2e.py
"""End-to-End-Nachweis der beiden Freigabe-Ketten (academy-auto, SEO/GEO).

Warum getrennt von test_bot.py: dort sind `academy_bridge` und `seo_gate`
gemockt, geprueft wird also nur, DASS der Dispatcher sie ruft. Bricht etwas
INNERHALB der Bruecken oder passen die Aufruf-Signaturen nicht mehr zusammen,
bleiben jene Tests trotzdem gruen — und der Ausfall waere still: die Knoepfe in
Telegram antworten einfach nicht mehr, ohne Fehlermeldung.

Hier laeuft deshalb der echte Weg von `handle_update()` bis auf die Platte,
mit echtem academy_bridge und echtem seo_gate. Gestubbt wird nur, was das
System verlaesst: `trigger_executor` (wuerde den produktiven academy-auto
starten) und `subprocess.run` (wuerde die echte seo-geo-CLI gegen die
Live-WordPress-Sites fahren).
"""
import json
import os
import tempfile
import unittest
from unittest import mock

import bot
import config
import seo_gate

TENANTS = {"8311805232": {"name": "Walter / WHITESTAG", "company_id": "comp-1",
                          "ceo_agent_id": "ceo-1", "vault": "whitestag"}}
WALTER = 8311805232


def make_app(tg, **extra):
    cfg = {"tenants": TENANTS, "paperclip_token": "tok", "whisper_model": "m.bin",
           "decision_label": "entscheidung-noetig", "poll_interval": 60,
           "state_path": "/tmp/nope.json", "reply_mode_path": "/tmp/nope-reply-mode.json",
           "eleven_api_key": "xi-test-key", "chat_model": "gemma-test"}
    cfg.update(extra)
    app = bot.BotApp(tg, cfg)
    app.seen = set()
    app._seeded = True
    return app


class TestAcademyFreigabeE2E(unittest.TestCase):
    """`academy:approve|reject:<ts>` — der Knopf unter dem Academy-Tagesstand."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.intent = os.path.join(self.tmp, "academy-auto", "intent.json")

    def _druecke(self, data, sender=WALTER):
        tg = mock.MagicMock()
        app = make_app(tg, academy_intent_path=self.intent,
                       academy_auto_dir=os.path.join(self.tmp, "academy-auto-dir"))
        with mock.patch.object(bot.academy_bridge, "trigger_executor") as te:
            app.handle_update({"callback_query": {"id": "cq", "data": data,
                                                  "from": {"id": sender}}})
        return tg, te

    def test_approve_schreibt_echte_intent_datei(self):
        tg, te = self._druecke("academy:approve:2026-08-17T02:00:03")
        self.assertTrue(os.path.isfile(self.intent), "intent.json wurde nicht geschrieben")
        with open(self.intent, encoding="utf-8") as fh:
            d = json.load(fh)
        self.assertEqual(d["kind"], "approve")
        self.assertEqual(d["ref_run_ts"], "2026-08-17T02:00:03")
        self.assertTrue(d["ts"], "Zeitstempel fehlt — Executor kann nicht deduplizieren")
        te.assert_called_once()
        tg.answer_callback_query.assert_called_once_with("cq", text="Verstanden — läuft.")

    def test_reject_schreibt_echte_intent_datei(self):
        self._druecke("academy:reject:2026-08-17T02:00:03")
        with open(self.intent, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["kind"], "reject")

    def test_fremder_absender_schreibt_nichts(self):
        tg, te = self._druecke("academy:approve:2026-08-17T02:00:03", sender=999)
        self.assertFalse(os.path.exists(self.intent))
        te.assert_not_called()
        tg.answer_callback_query.assert_not_called()

    def test_freitext_antwort_auf_den_tagesstand_wird_zur_nachtaufgabe(self):
        tg = mock.MagicMock()
        app = make_app(tg, academy_intent_path=self.intent,
                       academy_auto_dir=os.path.join(self.tmp, "academy-auto-dir"))
        with mock.patch.object(bot.academy_bridge, "trigger_executor"):
            app.handle_update({"message": {
                "message_id": 1, "chat": {"id": WALTER}, "from": {"id": WALTER},
                "text": "Login-Seite responsiver machen.",
                "reply_to_message": {"text": "🎓 Academy-Auto — Tagesstand\nWHI-1: Login"}}})
        with open(self.intent, encoding="utf-8") as fh:
            d = json.load(fh)
        self.assertEqual(d["kind"], "direction")
        self.assertEqual(d["text"], "Login-Seite responsiver machen.")


class TestSeoFreigabeE2E(unittest.TestCase):
    """`seo:ok/no:<token>` — die Knoepfe unter einem SEO/GEO-Changeset."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.approvals = os.path.join(self.tmp, "seo-approvals")
        self.root = os.path.join(self.tmp, "seo-geo")
        os.makedirs(self.approvals)
        self.pending = os.path.join(self.root, "whitestag.de", "pending")
        os.makedirs(self.pending)
        self.changeset = os.path.join(self.pending, "cs-2026-08-17.json")
        with open(self.changeset, "w", encoding="utf-8") as fh:
            json.dump({"aenderungen": []}, fh)
        self.token = "TOK123"
        with open(os.path.join(self.approvals, self.token + ".json"), "w", encoding="utf-8") as fh:
            json.dump({"token": self.token, "site": "whitestag.de", "status": "pending",
                       "changeset_path": self.changeset}, fh)
        # Die Config-Konstanten sind der Weg, den der Bot geht (_seo_cfg liest
        # sie direkt) — fuer den Test auf die Sandbox umbiegen.
        for name, wert in (("SEO_APPROVALS_DIR", self.approvals),
                           ("SEO_GEO_ROOT", self.root),
                           ("SEO_GEO_VENV", "/nicht/echt/python"),
                           ("SEO_GEO_CLI", "/nicht/echt/cli.py"),
                           ("SEO_GEO_SITES", "/nicht/echt/sites.json")):
            p = mock.patch.object(config, name, wert)
            p.start()
            self.addCleanup(p.stop)

    def _status(self):
        with open(os.path.join(self.approvals, self.token + ".json"), encoding="utf-8") as fh:
            return json.load(fh)

    def _druecke(self, data, sender=WALTER):
        tg = mock.MagicMock()
        make_app(tg).handle_update({"callback_query": {
            "id": "cq", "data": data, "from": {"id": sender},
            "message": {"chat": {"id": sender}}}})
        return tg

    def test_ok_ruft_approve_und_apply_und_schreibt_status(self):
        # Der Apply-Log ist die Bruecke zur echten CLI: seo_gate liest daraus
        # die Zahlen fuer die Telegram-Rueckmeldung.
        applied_dir = os.path.join(self.root, "whitestag.de", "applied")
        os.makedirs(applied_dir)
        with open(os.path.join(applied_dir, "apply-log.cs-2026-08-17.json.json"),
                  "w", encoding="utf-8") as fh:
            json.dump({"applied": ["a", "b", "c"], "failed": []}, fh)
        aufrufe = []

        def fake_run(argv, env=None):
            aufrufe.append(argv)
            return mock.Mock(returncode=0)

        with mock.patch.object(seo_gate.subprocess, "run", side_effect=fake_run):
            tg = self._druecke("seo:ok:" + self.token)

        self.assertEqual([a[2] for a in aufrufe], ["approve", "apply"],
                         "approve MUSS vor apply laufen")
        self.assertIn("--changeset", aufrufe[0])
        self.assertIn(self.changeset, aufrufe[0])
        self.assertIn("whitestag.de", aufrufe[1])
        self.assertEqual(self._status()["status"], "applied")
        texte = [c.args[1] for c in tg.send_message.call_args_list]
        self.assertTrue(any("3 angewendet" in t for t in texte), texte)
        self.assertTrue(any(self.token in t for t in texte), "Token fehlt in der Rueckmeldung")

    def test_gescheitertes_approve_bricht_ab_statt_auszurollen(self):
        # Der gefaehrlichste Fall: approve schlaegt fehl, apply liefe trotzdem
        # — dann ginge ein NICHT freigegebenes Changeset live auf die Site.
        aufrufe = []

        def fake_run(argv, env=None):
            aufrufe.append(argv)
            return mock.Mock(returncode=1)

        with mock.patch.object(seo_gate.subprocess, "run", side_effect=fake_run):
            tg = self._druecke("seo:ok:" + self.token)

        self.assertEqual([a[2] for a in aufrufe], ["approve"],
                         "nach gescheitertem approve darf apply NICHT laufen")
        self.assertEqual(self._status()["status"], "failed")
        texte = [c.args[1] for c in tg.send_message.call_args_list]
        self.assertTrue(any("approve fehlgeschlagen" in t for t in texte), texte)

    def test_no_lehnt_ab_und_verschiebt_das_changeset(self):
        # Reiner Dateipfad, ohne jede CLI — hier laeuft die Kette vollstaendig
        # echt durch, inklusive Verschieben nach rejected/.
        tg = self._druecke("seo:no:" + self.token)
        self.assertEqual(self._status()["status"], "rejected")
        self.assertFalse(os.path.exists(self.changeset), "Changeset blieb in pending/")
        self.assertTrue(os.path.isfile(
            os.path.join(self.root, "whitestag.de", "rejected", "cs-2026-08-17.json")))
        texte = [c.args[1] for c in tg.send_message.call_args_list]
        self.assertTrue(any("abgelehnt" in t for t in texte), texte)

    def test_fremder_absender_aendert_nichts(self):
        tg = self._druecke("seo:ok:" + self.token, sender=999)
        self.assertEqual(self._status()["status"], "pending")
        self.assertTrue(os.path.isfile(self.changeset))
        tg.send_message.assert_not_called()

    def test_zweiter_druck_wendet_nicht_erneut_an(self):
        # Doppelklick in Telegram darf ein Changeset nicht zweimal ausrollen.
        self._druecke("seo:no:" + self.token)
        with mock.patch.object(seo_gate.subprocess, "run") as sr:
            tg = self._druecke("seo:ok:" + self.token)
        sr.assert_not_called()
        self.assertEqual(self._status()["status"], "rejected")
        texte = [c.args[1] for c in tg.send_message.call_args_list]
        self.assertTrue(any("bereits bearbeitet" in t.lower() for t in texte), texte)

    def test_unbekanntes_token_meldet_sich_statt_still_zu_scheitern(self):
        tg = self._druecke("seo:ok:GIBTESNICHT")
        texte = [c.args[1] for c in tg.send_message.call_args_list]
        self.assertTrue(any("nicht mehr gefunden" in t for t in texte), texte)

    def test_path_traversal_token_wird_abgewiesen(self):
        tg = self._druecke("seo:ok:../../etc/passwd")
        tg.send_message.assert_not_called()
        tg.answer_callback_query.assert_not_called()


if __name__ == "__main__":
    unittest.main()
