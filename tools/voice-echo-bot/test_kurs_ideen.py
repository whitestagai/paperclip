# tools/voice-echo-bot/test_kurs_ideen.py
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime
from unittest import mock

import bot
import kurs_ideen

WALTER = 8311805232
CLARA = 1220010628


class Basis(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.datei = os.path.join(self.tmp, "Workshops", "_ideen-eingang.md")
        self.mdir = os.path.join(self.tmp, "Workshops", "_ideen")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def lesen(self, pfad=None):
        with open(pfad or self.datei, encoding="utf-8") as fh:
            return fh.read()


class TestParse(unittest.TestCase):
    def test_link_und_notiz(self):
        self.assertEqual(kurs_ideen.parse_befehl("https://youtu.be/abc?si=x tolles Thema"),
                         ("https://youtu.be/abc?si=x", "tolles Thema"))

    def test_notiz_vor_dem_link(self):
        self.assertEqual(kurs_ideen.parse_befehl("Agenten bauen https://example.com/a."),
                         ("https://example.com/a", "Agenten bauen"))

    def test_nur_thema(self):
        self.assertEqual(kurs_ideen.parse_befehl("  KI für   Zahnarztpraxen "),
                         (None, "KI für Zahnarztpraxen"))

    def test_youtube_erkennung(self):
        for u in ("https://www.youtube.com/watch?v=x", "https://youtu.be/x",
                  "https://m.youtube.com/shorts/x"):
            self.assertTrue(kurs_ideen.ist_youtube(u), u)
        self.assertFalse(kurs_ideen.ist_youtube("https://heise.de/news/youtube.com/x"))


class TestListe(Basis):
    def test_erste_idee_legt_datei_mit_kopf_an(self):
        idee = kurs_ideen.neue_idee("https://youtu.be/a", "gut | wichtig", self.datei, self.mdir,
                                    jetzt=datetime(2026, 10, 18, 7, 30, 5))
        inhalt = self.lesen()
        self.assertIn("## Ideen", inhalt)
        self.assertIn("| K-20261018-073005 | 2026-10-18 | offen | https://youtu.be/a | ⏳ | "
                      "gut \\| wichtig | _ideen/K-20261018-073005.md |", inhalt)
        self.assertEqual(idee["platz"], 1)
        self.assertEqual(idee["material_pfad"], os.path.join(self.mdir, "K-20261018-073005.md"))

    def test_platz_zaehlt_nur_offene(self):
        kurs_ideen.neue_idee(None, "A", self.datei, self.mdir, jetzt=datetime(2026, 1, 1, 1, 1, 1))
        with open(self.datei, encoding="utf-8") as fh:
            s = fh.read().replace("| offen |", "| gebaut (ki-a) |")
        with open(self.datei, "w", encoding="utf-8") as fh:
            fh.write(s)
        kurs_ideen.neue_idee(None, "B", self.datei, self.mdir, jetzt=datetime(2026, 1, 1, 1, 1, 2))
        idee = kurs_ideen.neue_idee(None, "C", self.datei, self.mdir,
                                    jetzt=datetime(2026, 1, 1, 1, 1, 3))
        self.assertEqual(idee["platz"], 2)

    def test_idee_ohne_link_hat_kein_material(self):
        idee = kurs_ideen.neue_idee(None, "KI im Ehrenamt", self.datei, self.mdir,
                                    jetzt=datetime(2026, 1, 1))
        self.assertIsNone(idee["material_pfad"])
        self.assertIn("| — | KI im Ehrenamt | KI im Ehrenamt | — |", self.lesen())

    def test_titel_eintragen_ersetzt_nur_eigenen_platzhalter(self):
        a = kurs_ideen.neue_idee("https://x.de/a", "", self.datei, self.mdir,
                                 jetzt=datetime(2026, 1, 1, 0, 0, 1))
        kurs_ideen.neue_idee("https://x.de/b", "", self.datei, self.mdir,
                             jetzt=datetime(2026, 1, 1, 0, 0, 2))
        kurs_ideen.titel_eintragen(self.datei, a["id"], "Agenten | Praxis")
        inhalt = self.lesen()
        self.assertIn("| https://x.de/a | Agenten \\| Praxis |", inhalt)
        self.assertIn("| https://x.de/b | ⏳ |", inhalt)


class TestText(unittest.TestCase):
    def test_vtt_rollende_dubletten_und_tags(self):
        vtt = ("WEBVTT\nKind: captions\nLanguage: en\n\n"
               "00:00:00.000 --> 00:00:02.000\nHello <c>world</c>\n\n"
               "00:00:02.000 --> 00:00:04.000\nHello world\nthis is &amp; that\n")
        self.assertEqual(kurs_ideen.vtt_zu_text(vtt), "Hello world this is & that")

    def test_html_zu_text(self):
        roh = ("<html><head><title>Fallback</title><meta property='og:title' content='Echter Titel'>"
               "<script>var x=1;</script></head><body><nav>Home Blog Kontakt</nav>"
               "<p>Das ist ein langer Absatz mit genug Wörtern für den Filter.</p>"
               "<footer>Impressum Datenschutz Cookies Einstellungen ändern bitte</footer></body></html>")
        titel, text = kurs_ideen.html_zu_text(roh)
        self.assertEqual(titel, "Echter Titel")
        self.assertEqual(text, "Das ist ein langer Absatz mit genug Wörtern für den Filter.")


class TestSpur(unittest.TestCase):
    def test_manuelle_untertitel_in_originalsprache_zuerst(self):
        info = {"language": "en", "subtitles": {"en-US": [], "de": []},
                "automatic_captions": {"en-orig": []}}
        self.assertEqual(kurs_ideen.waehle_spur(info), ("subs", "en-US"))

    def test_auto_orig_statt_uebersetzung(self):
        info = {"language": "en", "subtitles": {"live_chat": []},
                "automatic_captions": {"de": [], "en-orig": [], "en": []}}
        self.assertEqual(kurs_ideen.waehle_spur(info), ("auto", "en-orig"))

    def test_keine_spur(self):
        self.assertIsNone(kurs_ideen.waehle_spur({"language": "en"}))


class FakeYtDlp:
    """Simuliert yt-dlp: -J liefert Metadaten, Untertitel-/Audio-Aufrufe legen Dateien an."""

    def __init__(self, info, vtt=None, sub_fehler=False):
        self.info, self.vtt, self.sub_fehler, self.aufrufe = info, vtt, sub_fehler, []

    def __call__(self, args, timeout):
        self.aufrufe.append(args)
        if "-J" in args:
            return mock.Mock(stdout=json.dumps(self.info))
        ziel = os.path.dirname(args[args.index("-o") + 1])
        if "--skip-download" in args:
            if self.sub_fehler:
                raise subprocess.CalledProcessError(1, args)
            with open(os.path.join(ziel, "sub.en.vtt"), "w", encoding="utf-8") as fh:
                fh.write(self.vtt)
        else:
            open(os.path.join(ziel, "audio.webm"), "wb").close()
        return mock.Mock(stdout="")


class TestYoutube(unittest.TestCase):
    INFO = {"title": "Agents explained", "channel": "AI Kanal", "duration": 1260,
            "language": "en", "description": "Beschreibung",
            "automatic_captions": {"en-orig": []}}

    def test_untertitel_genau_eine_spur(self):
        fake = FakeYtDlp(self.INFO, vtt="WEBVTT\n\n00:00.000 --> 00:01.000\nHi there\n")
        with mock.patch.object(kurs_ideen.transcribe, "_resolve_binary", return_value="yt-dlp"):
            erg = kurs_ideen.youtube_holen("https://youtu.be/a", "m.bin", run=fake)
        self.assertEqual(erg["text"], "Hi there")
        self.assertEqual(erg["transkript"], "untertitel (automatisch, en-orig)")
        self.assertEqual(erg["dauer_min"], 21)
        sub = fake.aufrufe[1]
        self.assertEqual(sub[sub.index("--sub-langs") + 1], "en-orig")

    def test_whisper_wenn_untertitel_scheitern(self):
        fake = FakeYtDlp(self.INFO, sub_fehler=True)
        tr = mock.Mock(return_value="gesprochener Text")
        with mock.patch.object(kurs_ideen.transcribe, "_resolve_binary", return_value="yt-dlp"):
            erg = kurs_ideen.youtube_holen("https://youtu.be/a", "m.bin", run=fake, transcriber=tr)
        self.assertEqual(erg["text"], "gesprochener Text")
        self.assertEqual(erg["transkript"], "whisper (lokal)")
        self.assertEqual(tr.call_args.kwargs["language"], "auto")

    def test_zu_lang_ohne_untertitel(self):
        info = dict(self.INFO, duration=4 * 3600, automatic_captions={})
        with mock.patch.object(kurs_ideen.transcribe, "_resolve_binary", return_value="yt-dlp"):
            with self.assertRaises(RuntimeError):
                kurs_ideen.youtube_holen("https://youtu.be/a", "m.bin", run=FakeYtDlp(info))


class TestMaterial(Basis):
    def test_material_und_titel(self):
        idee = kurs_ideen.neue_idee("https://youtu.be/a", "Notiz", self.datei, self.mdir,
                                    jetzt=datetime(2026, 10, 18, 7, 0, 0))
        erg = kurs_ideen.material_holen(
            idee, "m.bin",
            youtube=lambda u, m: {"art": "youtube", "titel": "Agents explained", "kanal": "K",
                                  "dauer_min": 21, "text": "eins zwei drei",
                                  "transkript": "untertitel (automatisch, en-orig)"})
        self.assertEqual(erg["woerter"], 3)
        mat = self.lesen(idee["material_pfad"])
        self.assertIn('title: "Agents explained"', mat)
        self.assertIn("quelle: https://youtu.be/a", mat)
        self.assertIn("**Walters Notiz:** Notiz", mat)
        self.assertIn("keine Vorlage", mat)
        self.assertIn("## Transkript\n\neins zwei drei", mat)
        self.assertIn("| Agents explained |", self.lesen())

    def test_fehler_hinterlaesst_material_und_wirft(self):
        idee = kurs_ideen.neue_idee("https://x.de/a", "Thema X", self.datei, self.mdir,
                                    jetzt=datetime(2026, 10, 18, 7, 0, 0))

        def kaputt(u):
            raise OSError("HTTP 403")
        with self.assertRaises(OSError):
            kurs_ideen.material_holen(idee, "m.bin", artikel=kaputt)
        mat = self.lesen(idee["material_pfad"])
        self.assertIn("## Abruf fehlgeschlagen", mat)
        self.assertIn("HTTP 403", mat)
        self.assertIn("| Thema X | Thema X |", self.lesen())


def make_app(tg, tmp):
    cfg = {"tenants": {str(WALTER): {"name": "Walter", "company_id": "c1", "ceo_agent_id": "a1",
                                     "vault": "whitestag"},
                       str(CLARA): {"name": "Clara", "company_id": "c2", "ceo_agent_id": "a2",
                                    "vault": "clara"}},
           "paperclip_token": "tok", "whisper_model": "m.bin", "decision_label": "x",
           "poll_interval": 60, "state_path": "/tmp/nope.json",
           "reply_mode_path": os.path.join(tmp, "rm.json"), "eleven_api_key": None,
           "chat_model": "m", "kurs_ideen_datei": os.path.join(tmp, "_ideen-eingang.md"),
           "kurs_material_dir": os.path.join(tmp, "_ideen")}
    app = bot.BotApp(tg, cfg)
    app.seen = set()
    app._seeded = True
    return app


def nachricht(uid, text):
    return {"message": {"message_id": 3, "chat": {"id": uid}, "from": {"id": uid}, "text": text}}


class TestBot(Basis):
    def test_kurs_mit_link_traegt_ein_und_holt_material(self):
        tg = mock.MagicMock()
        app = make_app(tg, self.tmp)
        gestartet = []
        app._spawn = lambda fn, *a: gestartet.append((fn, a))
        with mock.patch.object(bot.llm, "chat") as lc:
            app.handle_update(nachricht(WALTER, "/kurs https://youtu.be/abc geiles Thema"))
        lc.assert_not_called()
        self.assertIn("| offen | https://youtu.be/abc | ⏳ | geiles Thema |",
                      self.lesen(app.cfg["kurs_ideen_datei"]))
        self.assertIn("Platz 1", tg.send_message.call_args_list[0].args[1])
        self.assertEqual(len(gestartet), 1)
        fn, args = gestartet[0]
        with mock.patch.object(bot.kurs_ideen, "material_holen",
                               return_value={"titel": "T", "woerter": 1200,
                                             "transkript": "whisper (lokal)"}):
            fn(*args)
        self.assertIn("„T“ — 1200 Wörter", tg.send_message.call_args_list[-1].args[1])

    def test_material_fehler_meldet_und_bleibt_in_liste(self):
        tg = mock.MagicMock()
        app = make_app(tg, self.tmp)
        idee = {"id": "K-1", "url": "https://x.de"}
        with mock.patch.object(bot.kurs_ideen, "material_holen", side_effect=OSError("403")):
            app._kurs_material(WALTER, idee)
        self.assertIn("nicht abrufbar (403)", tg.send_message.call_args.args[1])

    def test_kurs_ohne_argument_erklaert(self):
        tg = mock.MagicMock()
        app = make_app(tg, self.tmp)
        app.handle_update(nachricht(WALTER, "/kurs"))
        self.assertIn("/kurs <Link>", tg.send_message.call_args.args[1])
        self.assertFalse(os.path.exists(app.cfg["kurs_ideen_datei"]))

    def test_nur_thema_ohne_hintergrundjob(self):
        tg = mock.MagicMock()
        app = make_app(tg, self.tmp)
        app._spawn = mock.Mock()
        app.handle_update(nachricht(WALTER, "/kurs@whitestag_jarvis_bot KI für Vereine"))
        app._spawn.assert_not_called()
        self.assertIn("| KI für Vereine |", self.lesen(app.cfg["kurs_ideen_datei"]))

    def test_clara_kann_keine_kursideen_einreichen(self):
        tg = mock.MagicMock()
        app = make_app(tg, self.tmp)
        app.handle_update(nachricht(CLARA, "/kurs https://youtu.be/abc"))
        self.assertIn("nur für die WHITESTAG.ACADEMY", tg.send_message.call_args.args[1])
        self.assertFalse(os.path.exists(app.cfg["kurs_ideen_datei"]))


if __name__ == "__main__":
    unittest.main()
