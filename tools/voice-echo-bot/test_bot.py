# tools/voice-echo-bot/test_bot.py
import os
import tempfile
import unittest
from unittest import mock
import bot
# `create_issue` wird nach der jarvis_brain-Herauslösung ausschliesslich dort
# aufgerufen (bot.py delegiert komplett) - Patches muessen daher auf
# bot.jarvis_brain.create_issue zielen, nicht mehr auf bot.create_issue.

TENANTS = {"8311805232": {"name": "Walter / WHITESTAG", "company_id": "comp-1", "ceo_agent_id": "ceo-1",
                          "vault": "whitestag"},
           "1220010628": {"name": "Clara / Clara Sound", "company_id": "comp-2", "ceo_agent_id": "ceo-2",
                          "vault": "clara"}}

def make_app(tg, reply_mode_path="/tmp/nope-reply-mode.json"):
    cfg = {"tenants": TENANTS, "paperclip_token": "tok", "whisper_model": "m.bin",
           "decision_label": "entscheidung-noetig", "poll_interval": 60, "state_path": "/tmp/nope.json",
           "reply_mode_path": reply_mode_path, "eleven_api_key": "xi-test-key",
           "chat_model": "gemma-test"}
    app = bot.BotApp(tg, cfg); app.seen = set(); app._seeded = True; return app

def msg(uid, mid=1, text=None, voice=False, reply_text=None):
    m = {"message_id": mid, "chat": {"id": uid}, "from": {"id": uid}}
    if voice: m["voice"] = {"file_id": "fid"}
    elif text is not None: m["text"] = text
    if reply_text is not None: m["reply_to_message"] = {"text": reply_text}
    return {"message": m}

class TestTenantRouting(unittest.TestCase):
    def test_foreign_user_ignored(self):
        tg = mock.MagicMock(); make_app(tg).handle_update(msg(999, text="hi"))
        tg.send_message.assert_not_called()

    def test_plain_message_goes_to_chat_no_auto_offer(self):
        # Ersetzt das alte _offer-Verhalten: eine normale Nachricht darf KEIN
        # Issue anlegen und keine Bestätigungs-Buttons schicken, sondern nur
        # die LLM-Chat-Antwort zurückspiegeln.
        tg = mock.MagicMock(); app = make_app(tg)
        with mock.patch.object(bot.llm, "chat", return_value="Hallo Clara, wie kann ich helfen?") as lc, \
             mock.patch.object(bot.jarvis_brain, "create_issue") as ci:
            app.handle_update(msg(1220010628, mid=5, text="Hi Jarvis"))
        lc.assert_called_once()
        ci.assert_not_called()
        # keine reply_markup/Buttons
        for c in tg.send_message.call_args_list:
            self.assertNotIn("reply_markup", c.kwargs)
        self.assertFalse(hasattr(app, "candidates"))
        # Systemprompt trägt den Vornamen des Mandanten
        sys_msg = lc.call_args.args[0][0]
        self.assertEqual(sys_msg["role"], "system")
        self.assertIn("Clara", sys_msg["content"])

    def test_issue_token_creates_issue_in_tenant_company(self):
        # Ersetzt den alten Callback-Bestätigungs-Flow: das LLM gibt das
        # ISSUE-Token aus, der Bot legt DIREKT beim CEO des Mandanten an.
        tg = mock.MagicMock(); app = make_app(tg)
        with mock.patch.object(bot.llm, "chat",
                               return_value="ISSUE: Song mischen :: Bitte den Song final mischen."), \
             mock.patch.object(bot.jarvis_brain, "create_issue", return_value={"identifier": "CLR-1"}) as ci:
            app.handle_update(msg(1220010628, mid=5, text="Leg mir einen Task an: Song mischen"))
        ci.assert_called_once_with("tok", "comp-2", "ceo-2",
                                   bot.derive_title("Song mischen"), "Bitte den Song final mischen.")
        acked = [c for c in tg.send_message.call_args_list if "Task angelegt: CLR-1" in c.args[1]]
        self.assertEqual(len(acked), 1)

    def test_lookup_token_calls_vault_and_answers(self):
        # Frage nach echten Daten -> LLM gibt LOOKUP-Token -> Vault-Aufruf ->
        # zweiter LLM-Call formuliert die finale Antwort aus den Treffern.
        tg = mock.MagicMock(); app = make_app(tg)
        with mock.patch.object(bot.llm, "chat",
                               side_effect=["LOOKUP kontakt: Jana Kostbar",
                                            "Janas Nummer ist 0170 1234567."]) as lc, \
             mock.patch.object(bot.vault_client, "lookup",
                               return_value={"mode": "kontakt", "query": "Jana Kostbar",
                                             "treffer": [{"inhalt": "Tel: 0170 1234567"}]}) as vl, \
             mock.patch.object(bot.jarvis_brain, "create_issue") as ci:
            app.handle_update(msg(8311805232, mid=7, text="Was ist Janas Telefonnummer?"))
        vl.assert_called_once_with("kontakt", "Jana Kostbar", vault="whitestag")
        ci.assert_not_called()
        self.assertEqual(lc.call_count, 2)  # genau eine Lookup-Runde
        texts = [c.args[1] for c in tg.send_message.call_args_list]
        self.assertTrue(any("0170 1234567" in t for t in texts))

    def test_lookup_passes_clara_vault(self):
        tg = mock.MagicMock(); app = make_app(tg)
        with mock.patch.object(bot.llm, "chat",
                               side_effect=["LOOKUP kontakt: Max", "Antwort."]), \
             mock.patch.object(bot.vault_client, "lookup",
                               return_value={"mode": "kontakt", "query": "Max", "treffer": []}) as vl, \
             mock.patch.object(bot.jarvis_brain, "create_issue"):
            app.handle_update(msg(1220010628, mid=9, text="Nummer von Max?"))
        vl.assert_called_once_with("kontakt", "Max", vault="clara")

    def test_web_key_is_passed_to_brain(self):
        # Tippfehler im Config-Schlüsselnamen dürfen nicht unbemerkt bleiben:
        # self.cfg.get("web_key") liefert sonst still None und das Werkzeug
        # wäre nie im System-Prompt (Pendant zu
        # test_web_key_is_passed_to_brain im Wake-Satelliten).
        tg = mock.MagicMock(); app = make_app(tg)
        app.cfg["web_key"] = "tvly-k"
        seen = {}
        with mock.patch.object(bot.jarvis_brain, "respond",
                               side_effect=lambda *a, **k: seen.update(k) or
                                   {"kind": "chat", "answer": "ok"}):
            app.handle_update(msg(8311805232, mid=9, text="wetter?"))
        self.assertEqual(seen.get("web_key"), "tvly-k")

class TestReplyModeCommands(unittest.TestCase):
    def _app(self):
        fd, p = tempfile.mkstemp(suffix=".json"); os.close(fd); os.unlink(p)
        self.addCleanup(lambda: os.path.exists(p) and os.unlink(p))
        tg = mock.MagicMock()
        return tg, make_app(tg, reply_mode_path=p), p

    def test_voice_command_sets_mode_and_confirms_no_issue(self):
        tg, app, p = self._app()
        with mock.patch.object(bot.jarvis_brain, "create_issue") as ci, \
             mock.patch.object(bot.llm, "chat") as lc:
            app.handle_update(msg(8311805232, text="/voice"))
        ci.assert_not_called()
        lc.assert_not_called()  # Modus-Befehl geht nicht ans LLM
        self.assertEqual(bot.reply_mode.get_mode(p, 8311805232), "voice")
        tg.send_message.assert_called_once_with(8311805232, "🔊 Antworten jetzt als Sprache.")

    def test_text_command_sets_mode_and_confirms(self):
        tg, app, p = self._app()
        bot.reply_mode.set_mode(p, 8311805232, "voice")
        app.handle_update(msg(8311805232, text="/text"))
        self.assertEqual(bot.reply_mode.get_mode(p, 8311805232), "text")
        tg.send_message.assert_called_once_with(8311805232, "🔤 Antworten jetzt als Text.")

    def test_command_with_botname_suffix_recognized(self):
        tg, app, p = self._app()
        app.handle_update(msg(8311805232, text="/voice@JarvisBot"))
        self.assertEqual(bot.reply_mode.get_mode(p, 8311805232), "voice")

    def test_command_does_not_transcribe_or_chat(self):
        tg, app, p = self._app()
        with mock.patch.object(app, "_extract_text") as ex, mock.patch.object(app, "_handle_chat") as hc:
            app.handle_update(msg(8311805232, text="/text"))
        ex.assert_not_called()
        hc.assert_not_called()

    def test_voice_mode_routes_ack_via_send_voice(self):
        # _reply-Voice-Ausgabe jetzt über den Chat-/ISSUE-Pfad getrieben
        # (früher über den entfallenen Callback-Bestätigungs-Flow).
        tg, app, p = self._app()
        bot.reply_mode.set_mode(p, 1220010628, "voice")
        with mock.patch.object(bot.llm, "chat", return_value="ISSUE: Song :: Mische den Song"), \
             mock.patch.object(bot.jarvis_brain, "create_issue", return_value={"identifier": "CLR-1"}), \
             mock.patch.object(bot.tts, "synthesize", return_value="/tmp/reply.ogg") as syn:
            app.handle_update(msg(1220010628, mid=5, text="Leg einen Task an: Song mischen"))
        syn.assert_called_once()
        # Der Ack ging als Sprachnachricht raus, nicht als send_message
        tg.send_voice.assert_called_once()
        self.assertEqual(tg.send_voice.call_args.args[0], 1220010628)
        acked = [c for c in tg.send_message.call_args_list if "Task angelegt" in (c.args[1] if len(c.args) > 1 else "")]
        self.assertEqual(acked, [])

    def test_text_mode_ack_uses_send_message(self):
        tg, app, p = self._app()  # Default text
        with mock.patch.object(bot.llm, "chat", return_value="ISSUE: x :: x"), \
             mock.patch.object(bot.jarvis_brain, "create_issue", return_value={"identifier": "CLR-1"}):
            app.handle_update(msg(1220010628, mid=5, text="Leg einen Task an"))
        tg.send_voice.assert_not_called()
        acked = [c for c in tg.send_message.call_args_list if "Task angelegt" in c.args[1]]
        self.assertEqual(len(acked), 1)

    def test_tts_error_falls_back_to_text(self):
        tg, app, p = self._app()
        bot.reply_mode.set_mode(p, 1220010628, "voice")
        with mock.patch.object(bot.llm, "chat", return_value="ISSUE: x :: x"), \
             mock.patch.object(bot.jarvis_brain, "create_issue", return_value={"identifier": "CLR-1"}), \
             mock.patch.object(bot.tts, "synthesize", side_effect=bot.tts.TtsError("boom")):
            app.handle_update(msg(1220010628, mid=5, text="Leg einen Task an"))
        tg.send_voice.assert_not_called()
        texts = [c.args[1] for c in tg.send_message.call_args_list]
        self.assertTrue(any("Task angelegt" in t for t in texts))
        self.assertTrue(any("Sprachausgabe fehlgeschlagen" in t for t in texts))


class TestReply(unittest.TestCase):
    def test_reply_posts_comment_to_referenced_issue(self):
        tg = mock.MagicMock(); app = make_app(tg)
        with mock.patch.object(bot, "find_issue_by_identifier", return_value={"id": "iss-9", "identifier": "WHI-2857"}) as fi, \
             mock.patch.object(bot, "add_comment", return_value={"id": "c1"}) as ac:
            app.handle_update(msg(8311805232, text="Ja, mach DMARC so.", reply_text="🟠 Entscheidung benötigt — WHI-2857: DMARC"))
        fi.assert_called_once_with("tok", "comp-1", "WHI-2857", assignee_agent_id="ceo-1")
        ac.assert_called_once_with("tok", "iss-9", "Ja, mach DMARC so.", resume=True)

    def test_reply_unknown_identifier_no_comment(self):
        tg = mock.MagicMock(); app = make_app(tg)
        with mock.patch.object(bot, "find_issue_by_identifier", return_value=None), \
             mock.patch.object(bot, "add_comment") as ac:
            app.handle_update(msg(8311805232, text="egal", reply_text="WHI-9999: weg"))
        ac.assert_not_called()

class TestPoll(unittest.TestCase):
    def test_poll_pushes_new_events_per_tenant(self):
        tg = mock.MagicMock(); app = make_app(tg)
        with mock.patch.object(bot, "resolve_label_id", return_value="L"), \
             mock.patch.object(bot, "list_issues", return_value=[{"id": "a", "status": "done", "parentId": None, "labelIds": [], "identifier": "WHI-1", "title": "T"}]), \
             mock.patch.object(bot.state, "save_state"):
            app.poll_tenants()
        # zwei Mandanten, je ein done-Event -> zwei Pushes an die jeweiligen chat_ids
        pushed = {c.args[0] for c in tg.send_message.call_args_list}
        self.assertEqual(pushed, {8311805232, 1220010628})

    def test_first_run_suppresses_push(self):
        tg = mock.MagicMock(); app = make_app(tg); app._seeded = False
        with mock.patch.object(bot, "resolve_label_id", return_value="L"), \
             mock.patch.object(bot, "list_issues", return_value=[{"id": "a", "status": "done", "parentId": None, "labelIds": [], "identifier": "WHI-1", "title": "T"}]), \
             mock.patch.object(bot.state, "save_state"):
            app.poll_tenants()
        tg.send_message.assert_not_called()
        self.assertIn("a:done", app.seen)

    def test_readded_decision_label_renotifies(self):
        # Voller Re-Raise-Zyklus über zwei Polls: Issue war gelabelt+gesehen
        # (Push schon zugestellt); Label wird entfernt (Mensch hat
        # geantwortet) -> Poll 1 droppt den seen-Key, kein Push. Label wird
        # erneut gesetzt -> Poll 2 muss den Key wieder als neu behandeln und
        # erneut pushen.
        tg = mock.MagicMock(); app = make_app(tg)
        app.seen = {"a:decision"}
        unlabeled = [{"id": "a", "status": "in_progress", "parentId": None,
                     "labelIds": [], "identifier": "WHI-1", "title": "T"}]
        with mock.patch.object(bot, "resolve_label_id", return_value="L"), \
             mock.patch.object(bot, "list_issues", return_value=unlabeled), \
             mock.patch.object(bot.state, "save_state"):
            app.poll_tenants()
        tg.send_message.assert_not_called()
        self.assertNotIn("a:decision", app.seen)

        relabeled = [{"id": "a", "status": "in_progress", "parentId": None,
                     "labelIds": ["L"], "identifier": "WHI-1", "title": "T"}]
        with mock.patch.object(bot, "resolve_label_id", return_value="L"), \
             mock.patch.object(bot, "list_issues", return_value=relabeled), \
             mock.patch.object(bot.state, "save_state"):
            app.poll_tenants()
        pushed = {c.args[0] for c in tg.send_message.call_args_list}
        self.assertEqual(pushed, {8311805232, 1220010628})
        self.assertIn("a:decision", app.seen)

    def test_unlabeled_seen_decision_key_dropped_without_relabel(self):
        # Label wurde entfernt und (noch) nicht erneut gesetzt -> Key raus
        # aus seen, aber kein Push (kein aktuelles Event).
        tg = mock.MagicMock(); app = make_app(tg)
        app.seen = {"a:decision"}
        with mock.patch.object(bot, "resolve_label_id", return_value="L"), \
             mock.patch.object(bot, "list_issues",
                              return_value=[{"id": "a", "status": "in_progress", "parentId": None,
                                            "labelIds": [], "identifier": "WHI-1", "title": "T"}]), \
             mock.patch.object(bot.state, "save_state"):
            app.poll_tenants()
        tg.send_message.assert_not_called()
        self.assertNotIn("a:decision", app.seen)


class TestRunPollGuard(unittest.TestCase):
    def test_poll_crash_does_not_propagate_out_of_run(self):
        # KeyboardInterrupt dient hier nur als Test-Sentinel, um die
        # Endlosschleife nach der zweiten Iteration kontrolliert zu beenden
        # (BaseException, nicht von run()s `except Exception` abgefangen) —
        # keine Aussage über echtes run()-Verhalten bei Interrupts.
        tg = mock.MagicMock()
        tg.get_updates.side_effect = [[], KeyboardInterrupt]
        app = make_app(tg)

        call_count = {"n": 0}

        def boom():
            call_count["n"] += 1
            raise RuntimeError("transient auth.json read failure")

        with mock.patch.object(app, "poll_tenants", side_effect=boom), \
             mock.patch.object(bot.time, "monotonic", side_effect=[100.0]), \
             mock.patch.object(app, "_drain", return_value=None):
            with self.assertRaises(KeyboardInterrupt):
                app.run()
        # poll_tenants wurde in der ersten Iteration aufgerufen und hat
        # geworfen, aber run() lief weiter (last_poll wurde trotzdem
        # vorgerückt) bis zur zweiten get_updates-Iteration (Test-Sentinel) —
        # der Poll-Fehler selbst hat run() NICHT beendet.
        self.assertEqual(call_count["n"], 1)


class TestBuildAppSeeding(unittest.TestCase):
    def test_missing_state_file_seeds_empty_and_marks_seeded_false(self):
        with mock.patch.object(bot.state, "load_state", return_value=None), \
             mock.patch.object(bot.config, "load_env", return_value={"WHISPER_MODEL": "m.bin",
                                                                      "TELEGRAM_BOT_TOKEN": "t"}), \
             mock.patch.object(bot.tenants_mod, "load_tenants", return_value=TENANTS), \
             mock.patch.object(bot, "Telegram", return_value=mock.MagicMock()):
            app = bot.build_app()
        self.assertEqual(app.seen, set())
        self.assertFalse(app._seeded)

    def test_corrupt_state_file_seeds_empty_and_marks_seeded_false(self):
        # Kernstück von Fix 1: eine korrupte (aber existierende) Datei darf
        # NICHT zu _seeded=True + leerem seen führen (sonst Push-Sturm).
        with mock.patch.object(bot.state, "load_state", return_value=None), \
             mock.patch.object(bot.config, "load_env", return_value={"WHISPER_MODEL": "m.bin",
                                                                      "TELEGRAM_BOT_TOKEN": "t"}), \
             mock.patch.object(bot.tenants_mod, "load_tenants", return_value=TENANTS), \
             mock.patch.object(bot, "Telegram", return_value=mock.MagicMock()):
            app = bot.build_app()
        self.assertEqual(app.seen, set())
        self.assertFalse(app._seeded)

    def test_valid_state_file_seeds_set_and_marks_seeded_true(self):
        with mock.patch.object(bot.state, "load_state", return_value={"a:done"}), \
             mock.patch.object(bot.config, "load_env", return_value={"WHISPER_MODEL": "m.bin",
                                                                      "TELEGRAM_BOT_TOKEN": "t"}), \
             mock.patch.object(bot.tenants_mod, "load_tenants", return_value=TENANTS), \
             mock.patch.object(bot, "Telegram", return_value=mock.MagicMock()):
            app = bot.build_app()
        self.assertEqual(app.seen, {"a:done"})
        self.assertTrue(app._seeded)


class TestParseControl(unittest.TestCase):
    def test_lookup_token_case_insensitive(self):
        a = bot.parse_control("lookup TERMIN: heute")
        self.assertEqual(a, {"kind": "lookup", "mode": "termin", "query": "heute"})

    def test_issue_token_splits_title_and_description(self):
        a = bot.parse_control("ISSUE: Titel :: Lange Beschreibung")
        self.assertEqual(a["kind"], "issue")
        self.assertEqual(a["title"], "Titel")
        self.assertEqual(a["description"], "Lange Beschreibung")

    def test_issue_without_desc_reuses_title(self):
        a = bot.parse_control("ISSUE: Nur ein Titel")
        self.assertEqual(a["description"], "Nur ein Titel")

    def test_plain_text_is_chat(self):
        a = bot.parse_control("Hallo Walter, klar!")
        self.assertEqual(a, {"kind": "chat", "text": "Hallo Walter, klar!"})

    def test_token_only_recognized_at_line_start(self):
        # Steht das "Token" mitten im Fließtext, ist es KEIN Steuer-Token.
        a = bot.parse_control("Ich könnte ein LOOKUP kontakt: X machen, soll ich?")
        self.assertEqual(a["kind"], "chat")


class TestChatFallback(unittest.TestCase):
    def test_llm_unreachable_sends_hint_no_crash(self):
        tg = mock.MagicMock(); app = make_app(tg)
        with mock.patch.object(bot.llm, "chat", side_effect=bot.llm.LlmError("down")):
            app.handle_update(msg(8311805232, mid=3, text="Hi"))
        texts = [c.args[1] for c in tg.send_message.call_args_list]
        self.assertTrue(any("nicht erreichbar" in t for t in texts))

    def test_llm_unreachable_still_files_raw_issue_with_ceo(self):
        """Kein Auftragsverlust: fällt das LLM aus, geht der Rohtext trotzdem an den CEO."""
        tg = mock.MagicMock(); app = make_app(tg)
        with mock.patch.object(bot.llm, "chat", side_effect=bot.llm.LlmError("down")), \
             mock.patch.object(bot.jarvis_brain, "create_issue", return_value={"identifier": "WHI-42"}) as ci:
            app.handle_update(msg(8311805232, mid=3,
                                  text="Such mir die Vergabenummer vom Lausitz Science Park raus."))
        ci.assert_called_once()
        args = ci.call_args.args
        self.assertEqual(args[1], "comp-1")
        self.assertEqual(args[2], "ceo-1")
        self.assertIn("Lausitz Science Park", args[4])
        texts = [c.args[1] for c in tg.send_message.call_args_list]
        self.assertTrue(any("WHI-42" in t for t in texts))

    def test_raw_issue_marked_as_unparsed(self):
        """Der CEO muss erkennen, dass der Text ungeprüft durchgereicht wurde."""
        tg = mock.MagicMock(); app = make_app(tg)
        with mock.patch.object(bot.llm, "chat", side_effect=bot.llm.LlmError("down")), \
             mock.patch.object(bot.jarvis_brain, "create_issue", return_value={"identifier": "WHI-42"}) as ci:
            app.handle_update(msg(8311805232, mid=3, text="Bitte Angebot rausschicken"))
        self.assertIn("unausgewertet", ci.call_args.args[4].lower())

    def test_llm_and_issue_both_down_warns_user_explicitly(self):
        """Geht auch die Issue-Anlage nicht, muss der Nutzer das unmissverständlich hören."""
        tg = mock.MagicMock(); app = make_app(tg)
        with mock.patch.object(bot.llm, "chat", side_effect=bot.llm.LlmError("down")), \
             mock.patch.object(bot.jarvis_brain, "create_issue", side_effect=RuntimeError("api tot")):
            app.handle_update(msg(8311805232, mid=3, text="Wichtiger Auftrag"))
        texts = [c.args[1] for c in tg.send_message.call_args_list]
        self.assertTrue(any("nicht angekommen" in t.lower() for t in texts))

    def test_vault_unreachable_still_answers(self):
        tg = mock.MagicMock(); app = make_app(tg)
        with mock.patch.object(bot.llm, "chat",
                               side_effect=["LOOKUP kontakt: X", "Ich habe dazu leider nichts gefunden."]), \
             mock.patch.object(bot.vault_client, "lookup", side_effect=bot.vault_client.VaultError("down")):
            app.handle_update(msg(8311805232, mid=3, text="Nummer von X?"))
        texts = [c.args[1] for c in tg.send_message.call_args_list]
        self.assertTrue(any("nichts gefunden" in t for t in texts))

    def test_history_is_trimmed_to_max(self):
        tg = mock.MagicMock(); app = make_app(tg)
        with mock.patch.object(bot.llm, "chat", return_value="ok"):
            for i in range(10):
                app.handle_update(msg(8311805232, mid=i, text="Frage {}".format(i)))
        self.assertLessEqual(len(app.history[8311805232]), bot.MAX_HISTORY_MESSAGES)


class TestDoLookupUnknownVault(unittest.TestCase):
    def test_do_lookup_refuses_unknown_vault(self):
        # _do_lookup lebt jetzt in jarvis_brain (bot.py re-importiert das
        # Modul als bot.jarvis_brain); Aufrufweg umgezogen, Assertions unveraendert.
        tg = mock.MagicMock(); app = make_app(tg)
        with mock.patch.object(bot.vault_client, "lookup",
                               return_value={"mode": "kontakt", "query": "x",
                                             "treffer": [], "vault_unknown": True}), \
             mock.patch.object(bot.llm, "chat") as lc:
            out = bot.jarvis_brain._do_lookup([], "kontakt", "x", {"name": "X", "vault": "Clara"},
                                              app._chat_model())
        self.assertIn("nicht zugreifen", out)
        lc.assert_not_called()



class TestSeoCfgWpEnv(unittest.TestCase):
    def test_seo_cfg_contains_wp_env_dict(self):
        app = make_app(mock.MagicMock())
        cfg = app._seo_cfg()
        self.assertIn("wp_env", cfg)
        self.assertIsInstance(cfg["wp_env"], dict)

    def test_seo_cfg_wp_env_loaded_from_whitestag_env_when_present(self):
        app = make_app(mock.MagicMock())
        with mock.patch("config.os.path.exists", return_value=True), \
             mock.patch("config.load_env", return_value={"WHITESTAG_DE_WP_USER": "u"}):
            cfg = app._seo_cfg()
        self.assertEqual(cfg["wp_env"], {"WHITESTAG_DE_WP_USER": "u"})

    def test_seo_cfg_wp_env_empty_when_file_missing(self):
        app = make_app(mock.MagicMock())
        with mock.patch("config.os.path.exists", return_value=False):
            cfg = app._seo_cfg()
        self.assertEqual(cfg["wp_env"], {})


class TestSeoCallback(unittest.TestCase):
    def test_seo_callback_only_walter(self):
        tg = mock.MagicMock(); app = make_app(tg)
        update = {"callback_query": {"id": "cq1", "data": "seo:ok:TOK",
                  "from": {"id": 999999}, "message": {"chat": {"id": 999999}}}}
        with mock.patch("seo_gate.load_token") as lt, mock.patch("seo_gate.apply_token") as at:
            app.handle_update(update)
        lt.assert_not_called()
        at.assert_not_called()
        texts = [c.args[1] if len(c.args) > 1 else c.kwargs.get("text")
                 for c in tg.answer_callback_query.call_args_list]
        self.assertTrue(any("nicht berechtigt" in (t or "") for t in texts))
        tg.send_message.assert_not_called()

    def test_seo_callback_walter_applies(self):
        tg = mock.MagicMock(); app = make_app(tg)
        with mock.patch("seo_gate.load_token",
                        return_value={"token": "TOK", "site": "s", "status": "pending",
                                     "changeset_path": "/c.json"}), \
             mock.patch("seo_gate.apply_token",
                        return_value="✅ s live — 3 angewendet, 0 Fehler") as at:
            update = {"callback_query": {"id": "cq2", "data": "seo:ok:TOK",
                      "from": {"id": 8311805232}, "message": {"chat": {"id": 8311805232}}}}
            app.handle_update(update)
        at.assert_called_once()
        texts = [c.args[1] for c in tg.send_message.call_args_list]
        self.assertTrue(any("live" in t for t in texts))
        tg.answer_callback_query.assert_called_once_with("cq2")

    def test_seo_callback_reject_calls_reject_token(self):
        tg = mock.MagicMock(); app = make_app(tg)
        with mock.patch("seo_gate.load_token",
                        return_value={"token": "TOK", "site": "s", "status": "pending",
                                     "changeset_path": "/c.json"}), \
             mock.patch("seo_gate.reject_token", return_value="❌ s abgelehnt.") as rt:
            update = {"callback_query": {"id": "cq3", "data": "seo:no:TOK",
                      "from": {"id": 8311805232}, "message": {"chat": {"id": 8311805232}}}}
            app.handle_update(update)
        rt.assert_called_once()
        texts = [c.args[1] for c in tg.send_message.call_args_list]
        self.assertTrue(any("abgelehnt" in t for t in texts))

    def test_seo_callback_unknown_token_reports_gone(self):
        tg = mock.MagicMock(); app = make_app(tg)
        with mock.patch("seo_gate.load_token", return_value=None):
            update = {"callback_query": {"id": "cq4", "data": "seo:ok:TOK",
                      "from": {"id": 8311805232}, "message": {"chat": {"id": 8311805232}}}}
            app.handle_update(update)
        texts = [c.args[1] for c in tg.send_message.call_args_list]
        self.assertTrue(any("nicht mehr gefunden" in t for t in texts))

    def test_seo_callback_non_seo_data_ignored(self):
        tg = mock.MagicMock(); app = make_app(tg)
        update = {"callback_query": {"id": "cq5", "data": "other:x",
                  "from": {"id": 8311805232}, "message": {"chat": {"id": 8311805232}}}}
        app.handle_update(update)
        tg.answer_callback_query.assert_not_called()
        tg.send_message.assert_not_called()

    def test_reply_with_token_stores_note(self):
        tg = mock.MagicMock(); app = make_app(tg)
        with mock.patch("seo_gate.note_token") as nt:
            app.handle_update(msg(8311805232, mid=5, text="nur die Startseite bitte",
                                  reply_text="🟢 SEO-Freigabe film …\n\n(Token ABC)"))
        nt.assert_called_once()
        args = nt.call_args.args
        self.assertEqual(args[1], "ABC")
        self.assertEqual(args[2], "nur die Startseite bitte")
        texts = [c.args[1] for c in tg.send_message.call_args_list]
        self.assertTrue(any("Notiz" in t and "ABC" in t for t in texts))

    def test_reply_with_token_from_non_walter_tenant_does_not_note(self):
        # Multi-Tenant-Guard: Der Freitext-Notiz-Pfad darf wie der Button-Callback
        # nur fuer Walter (config.WALTER_CHAT_ID) wirken. Ein anderer Tenant
        # (hier Clara) darf keine Notiz auf einen SEO-Freigabe-Token schreiben.
        tg = mock.MagicMock(); app = make_app(tg)
        with mock.patch("seo_gate.note_token") as nt:
            app.handle_update(msg(1220010628, mid=5, text="nur die Startseite bitte",
                                  reply_text="🟢 SEO-Freigabe film …\n\n(Token ABC)"))
        nt.assert_not_called()


class TestAcademyBridgeIntegration(unittest.TestCase):
    def test_academy_callback_writes_intent_and_triggers_executor(self):
        tg = mock.MagicMock(); app = make_app(tg)
        update = {"callback_query": {"id": "cbq1", "from": {"id": 8311805232},
                                     "data": "academy:approve:2026-07-25T02:00:03"}}
        with mock.patch.object(bot.academy_bridge, "write_intent_file") as wf, \
             mock.patch.object(bot.academy_bridge, "trigger_executor") as te:
            app.handle_update(update)
        wf.assert_called_once()
        path_arg, dict_arg = wf.call_args.args
        self.assertEqual(path_arg, bot.DEFAULT_ACADEMY_INTENT_PATH)
        self.assertEqual(dict_arg["kind"], "approve")
        self.assertEqual(dict_arg["ref_run_ts"], "2026-07-25T02:00:03")
        te.assert_called_once_with(bot.DEFAULT_ACADEMY_AUTO_DIR)
        tg.answer_callback_query.assert_called_once_with("cbq1", text="Verstanden — läuft.")

    def test_academy_callback_uses_configured_paths_when_present(self):
        tg = mock.MagicMock(); app = make_app(tg)
        app.cfg["academy_intent_path"] = "/tmp/custom-intent.json"
        app.cfg["academy_auto_dir"] = "/tmp/custom-academy-auto"
        update = {"callback_query": {"id": "cbq2", "from": {"id": 1220010628},
                                     "data": "academy:reject:R1"}}
        with mock.patch.object(bot.academy_bridge, "write_intent_file") as wf, \
             mock.patch.object(bot.academy_bridge, "trigger_executor") as te:
            app.handle_update(update)
        self.assertEqual(wf.call_args.args[0], "/tmp/custom-intent.json")
        te.assert_called_once_with("/tmp/custom-academy-auto")

    def test_academy_callback_foreign_data_goes_to_seo_not_academy(self):
        tg = mock.MagicMock(); app = make_app(tg)
        update = {"callback_query": {"id": "cbq3", "from": {"id": 8311805232},
                                     "data": "issue:confirm:WHI-1", "message": {"chat": {"id": 8311805232}}}}
        with mock.patch.object(bot.academy_bridge, "write_intent_file") as wf, \
             mock.patch("seo_gate.load_token") as lt:
            app.handle_update(update)
        wf.assert_not_called()
        lt.assert_not_called()  # seo_gate.parse_callback lehnt Fremd-Daten ab

    def test_academy_callback_unknown_sender_is_dropped(self):
        tg = mock.MagicMock(); app = make_app(tg)
        update = {"callback_query": {"id": "cbq-unknown", "from": {"id": 999},
                                     "data": "academy:approve:2026-07-25T02:00:03"}}
        with mock.patch.object(bot.academy_bridge, "write_intent_file") as wf, \
             mock.patch.object(bot.academy_bridge, "trigger_executor") as te:
            app.handle_update(update)
        wf.assert_not_called()
        te.assert_not_called()
        tg.answer_callback_query.assert_not_called()

    def test_academy_reply_writes_intent_and_does_not_hit_issue_path(self):
        tg = mock.MagicMock(); app = make_app(tg)
        with mock.patch.object(bot.academy_bridge, "write_intent_file") as wf, \
             mock.patch.object(bot.academy_bridge, "trigger_executor") as te, \
             mock.patch.object(bot, "find_issue_by_identifier") as fi:
            app.handle_update(msg(8311805232, text="Login-Seite responsiver machen.",
                                  reply_text="🎓 Academy-Auto — Tagesstand\nWHI-1: Login"))
        fi.assert_not_called()
        wf.assert_called_once()
        dict_arg = wf.call_args.args[1]
        self.assertEqual(dict_arg["kind"], "direction")
        self.assertEqual(dict_arg["text"], "Login-Seite responsiver machen.")
        te.assert_called_once()
        tg.send_message.assert_called_once_with(8311805232, "✍️ Als Nachtaufgabe notiert.")

    def test_academy_reply_empty_text_skips_write(self):
        tg = mock.MagicMock(); app = make_app(tg)
        with mock.patch.object(bot.academy_bridge, "write_intent_file") as wf:
            app.handle_update(msg(8311805232, text="",
                                  reply_text="🎓 Academy-Auto — Tagesstand\nWHI-1: Login"))
        wf.assert_not_called()

    def test_non_academy_reply_still_uses_ident_path(self):
        # Regressions-Schutz: normale WHI-Reply-Erkennung bleibt unverändert.
        tg = mock.MagicMock(); app = make_app(tg)
        with mock.patch.object(bot, "find_issue_by_identifier", return_value={"id": "iss-9", "identifier": "WHI-2857"}) as fi, \
             mock.patch.object(bot, "add_comment", return_value={"id": "c1"}), \
             mock.patch.object(bot.academy_bridge, "write_intent_file") as wf:
            app.handle_update(msg(8311805232, text="Ja, mach DMARC so.", reply_text="🟠 Entscheidung benötigt — WHI-2857: DMARC"))
        fi.assert_called_once()
        wf.assert_not_called()


class TestWebSperreNachVaultTreffer(unittest.TestCase):
    """Der PII-Notaus im Telegram-Pfad.

    `web_erlaubt=False` sperrt die Websuche, nachdem Vault-Daten geflossen
    sind — sonst koennte das Modell aus dem Kontext einen WEB:-Suchbegriff
    bilden und private Daten (Adresse, Telefonnummer) nach draussen tragen.

    Anders als beim Wake-Satelliten laesst sich die Sperre hier nicht an die
    Gespraechskette haengen: der Satellit startet jede Kette ohne History, der
    Telegram-Chat traegt seine History ueber die gesamte Bot-Laufzeit. Die
    Sperre haengt deshalb genau am History-FENSTER — sie gilt, solange die
    Vault-Runde noch in den behaltenen Turns steht, und faellt, sobald sie
    herausgerutscht ist. Dauerhaft sperren waere kein Schutz, sondern ein
    Verlust: nach der ersten Kontaktabfrage haette der Chat nie wieder
    Websuche.
    """

    def _lauf(self, app, uid, kinds):
        """Schickt je eine Nachricht pro `kind` und protokolliert web_erlaubt."""
        gesehen = []

        def fake_respond(*a, **k):
            gesehen.append(k.get("web_erlaubt"))
            return {"kind": fake_respond.kind, "answer": "Antwort"}

        with mock.patch.object(bot.jarvis_brain, "respond", side_effect=fake_respond):
            for i, kind in enumerate(kinds):
                fake_respond.kind = kind
                app.handle_update(msg(uid, mid=i + 1, text="Frage {}".format(i)))
        return gesehen

    def test_lookup_sperrt_die_folgerunde(self):
        app = make_app(mock.MagicMock())
        gesehen = self._lauf(app, 8311805232, ["lookup", "chat"])
        self.assertTrue(gesehen[0])    # Runde 1: noch frei
        self.assertFalse(gesehen[1])   # Runde 2: Vault-Daten im Kontext -> zu

    def test_ohne_lookup_bleibt_die_suche_frei(self):
        app = make_app(mock.MagicMock())
        gesehen = self._lauf(app, 8311805232, ["chat", "web", "issue", "chat"])
        self.assertTrue(all(gesehen), gesehen)

    def test_sperre_faellt_wenn_der_treffer_aus_der_history_rutscht(self):
        # MAX_HISTORY_MESSAGES/2 Turns nach dem Lookup ist die Vault-Runde aus
        # dem behaltenen Fenster gefallen — ab da darf wieder gesucht werden.
        app = make_app(mock.MagicMock())
        turns = bot.MAX_HISTORY_MESSAGES // 2
        gesehen = self._lauf(app, 8311805232, ["lookup"] + ["chat"] * (turns + 1))
        self.assertTrue(gesehen[0])
        self.assertFalse(gesehen[1], "direkt nach dem Lookup muss zu sein")
        self.assertFalse(gesehen[turns], "innerhalb des Fensters noch zu")
        self.assertTrue(gesehen[turns + 1], "Treffer ist herausgerutscht -> wieder frei")

    def test_sperre_gilt_nur_fuer_den_eigenen_chat(self):
        # Mehrmandanten-Bot: Walters Vault-Treffer darf Claras Chat nicht
        # die Websuche nehmen (und umgekehrt).
        app = make_app(mock.MagicMock())
        self._lauf(app, 8311805232, ["lookup"])
        gesehen = self._lauf(app, 1220010628, ["chat"])
        self.assertTrue(gesehen[0])

    def test_history_und_merker_bleiben_gleich_lang(self):
        # Laufen die beiden Listen auseinander, zeigt die Sperre auf die
        # falsche Runde — der Fehler waere still.
        app = make_app(mock.MagicMock())
        self._lauf(app, 8311805232, ["lookup"] + ["chat"] * 12)
        self.assertEqual(len(app.vault_flags[8311805232]),
                         len(app.history[8311805232]) // 2)


if __name__ == "__main__": unittest.main()
