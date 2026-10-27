# tools/voice-echo-bot/test_llm.py
import io
import json
import unittest
import urllib.error
from unittest import mock

import llm


class _Resp:
    def __init__(self, payload):
        self._data = json.dumps(payload).encode("utf-8")
    def read(self):
        return self._data
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


class _NoSleep(unittest.TestCase):
    """Retry-Pausen wegpatchen — Tests sollen nicht real 5 s warten."""

    def setUp(self):
        patcher = mock.patch.object(llm.time, "sleep")
        self.sleep = patcher.start()
        self.addCleanup(patcher.stop)


class TestChat(_NoSleep):
    def test_reasoning_effort_goes_into_the_request_when_set(self):
        # Die Studio-gemma denkt sonst vor jeder Antwort: 259 von 302 Tokens
        # Reasoning, 31 s statt 3 s für zwei gesprochene Sätze (26.10.).
        captured = {}
        def fake_urlopen(req, timeout=None):
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return _Resp({"choices": [{"message": {"content": "ok"}}]})
        with mock.patch.object(llm.urllib.request, "urlopen", side_effect=fake_urlopen):
            llm.chat([{"role": "user", "content": "hi"}], model="gemma-x",
                     reasoning_effort="none")
        self.assertEqual(captured["body"]["reasoning_effort"], "none")

    def test_reasoning_effort_absent_by_default(self):
        # Der Telegram-Jarvis schickt weiter genau den Request wie bisher.
        captured = {}
        def fake_urlopen(req, timeout=None):
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return _Resp({"choices": [{"message": {"content": "ok"}}]})
        with mock.patch.object(llm.urllib.request, "urlopen", side_effect=fake_urlopen):
            llm.chat([{"role": "user", "content": "hi"}], model="gemma-x")
        self.assertNotIn("reasoning_effort", captured["body"])

    def test_returns_stripped_content(self):
        payload = {"choices": [{"message": {"content": "  Hallo Walter  "}}]}
        with mock.patch.object(llm.urllib.request, "urlopen", return_value=_Resp(payload)):
            self.assertEqual(llm.chat([{"role": "user", "content": "hi"}]), "Hallo Walter")

    def test_sends_model_and_messages(self):
        captured = {}
        def fake_urlopen(req, timeout=None):
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return _Resp({"choices": [{"message": {"content": "ok"}}]})
        with mock.patch.object(llm.urllib.request, "urlopen", side_effect=fake_urlopen):
            llm.chat([{"role": "user", "content": "hi"}], model="gemma-x", temperature=0.7)
        self.assertEqual(captured["body"]["model"], "gemma-x")
        self.assertEqual(captured["body"]["temperature"], 0.7)
        self.assertEqual(captured["body"]["messages"][0]["content"], "hi")

    def test_http_error_raises_llmerror(self):
        err = urllib.error.HTTPError("u", 500, "boom", {}, io.BytesIO(b""))
        with mock.patch.object(llm.urllib.request, "urlopen", side_effect=err):
            with self.assertRaises(llm.LlmError):
                llm.chat([{"role": "user", "content": "hi"}])

    def test_urlerror_raises_llmerror(self):
        with mock.patch.object(llm.urllib.request, "urlopen",
                               side_effect=urllib.error.URLError("refused")):
            with self.assertRaises(llm.LlmError):
                llm.chat([{"role": "user", "content": "hi"}])

    def test_empty_content_raises(self):
        with mock.patch.object(llm.urllib.request, "urlopen",
                               return_value=_Resp({"choices": [{"message": {"content": "   "}}]})):
            with self.assertRaises(llm.LlmError):
                llm.chat([{"role": "user", "content": "hi"}])

    def test_malformed_payload_raises(self):
        with mock.patch.object(llm.urllib.request, "urlopen",
                               return_value=_Resp({"nope": True})):
            with self.assertRaises(llm.LlmError):
                llm.chat([{"role": "user", "content": "hi"}])


class TestRetryAndFallback(_NoSleep):
    """Ein Kaltstart von LM Studio darf keine Nachricht kosten (Timeout → 2. Versuch)."""

    def test_retries_same_model_after_timeout(self):
        calls = []
        def fake_urlopen(req, timeout=None):
            calls.append(json.loads(req.data.decode("utf-8"))["model"])
            if len(calls) == 1:
                raise TimeoutError("timed out")
            return _Resp({"choices": [{"message": {"content": "spät, aber da"}}]})
        with mock.patch.object(llm.urllib.request, "urlopen", side_effect=fake_urlopen):
            answer = llm.chat([{"role": "user", "content": "hi"}], model="gemma-x")
        self.assertEqual(answer, "spät, aber da")
        self.assertEqual(calls, ["gemma-x", "gemma-x"])

    def test_waits_between_retries(self):
        def fake_urlopen(req, timeout=None):
            raise TimeoutError("timed out")
        with mock.patch.object(llm.urllib.request, "urlopen", side_effect=fake_urlopen):
            with self.assertRaises(llm.LlmError):
                llm.chat([{"role": "user", "content": "hi"}], model="gemma-x")
        self.sleep.assert_called()

    def test_switches_to_fallback_model_when_primary_keeps_failing(self):
        calls = []
        def fake_urlopen(req, timeout=None):
            model = json.loads(req.data.decode("utf-8"))["model"]
            calls.append(model)
            if model == "gross":
                raise urllib.error.HTTPError("u", 400, "no ram", {}, io.BytesIO(b""))
            return _Resp({"choices": [{"message": {"content": "klein hilft aus"}}]})
        with mock.patch.object(llm.urllib.request, "urlopen", side_effect=fake_urlopen):
            answer = llm.chat([{"role": "user", "content": "hi"}],
                              model="gross", fallback_model="klein")
        self.assertEqual(answer, "klein hilft aus")
        self.assertEqual(calls, ["gross", "gross", "klein"])

    def test_raises_when_fallback_also_fails(self):
        with mock.patch.object(llm.urllib.request, "urlopen",
                               side_effect=TimeoutError("timed out")):
            with self.assertRaises(llm.LlmError):
                llm.chat([{"role": "user", "content": "hi"}],
                         model="gross", fallback_model="klein")

    def test_does_not_call_fallback_when_primary_succeeds(self):
        calls = []
        def fake_urlopen(req, timeout=None):
            calls.append(json.loads(req.data.decode("utf-8"))["model"])
            return _Resp({"choices": [{"message": {"content": "ok"}}]})
        with mock.patch.object(llm.urllib.request, "urlopen", side_effect=fake_urlopen):
            llm.chat([{"role": "user", "content": "hi"}], model="gross", fallback_model="klein")
        self.assertEqual(calls, ["gross"])

    def test_identical_fallback_does_not_add_a_third_attempt(self):
        """Ist der Fallback dasselbe Modell, waere ein dritter Versuch sinnlose Wartezeit."""
        calls = []
        def fake_urlopen(req, timeout=None):
            calls.append(json.loads(req.data.decode("utf-8"))["model"])
            raise TimeoutError("timed out")
        with mock.patch.object(llm.urllib.request, "urlopen", side_effect=fake_urlopen):
            with self.assertRaises(llm.LlmError):
                llm.chat([{"role": "user", "content": "hi"}],
                         model="gleich", fallback_model="gleich")
        self.assertEqual(calls, ["gleich", "gleich"])

    def test_module_default_fallback_avoids_the_primary_model(self):
        """Ist das Primaermodell selbst FALLBACK_MODEL, weicht der Default aus.

        Sonst haette ausgerechnet der Aufrufer keinen Fallback, der das
        staerkste Modell direkt fuehrt — `chat()` ueberspringt den dritten
        Versuch ja, wenn er auf dasselbe Modell zeigt. Betrifft den
        Wake-Satelliten, sobald `sat_config.CHAT_MODEL` auf FALLBACK_MODEL
        steht: dessen Modell liegt auf einem ANDEREN Geraet (LM Link), und
        genau dann braucht es ein lokales Netz darunter.

        Mit eigenen Modellnamen: seit FALLBACK_MODEL und DEFAULT_MODEL in
        llm.py beide `google/gemma-4-12b` sind, gibt es mit den echten Werten
        gar nichts auszuweichen, und der Test war rot, ohne dass die Regel
        kaputt war.
        """
        calls = []
        def fake_urlopen(req, timeout=None):
            calls.append(json.loads(req.data.decode("utf-8"))["model"])
            raise TimeoutError("timed out")
        with mock.patch.object(llm, "FALLBACK_MODEL", "fern-gross"), \
                mock.patch.object(llm, "DEFAULT_MODEL", "lokal-klein"), \
                mock.patch.object(llm.urllib.request, "urlopen", side_effect=fake_urlopen):
            with self.assertRaises(llm.LlmError):
                llm.chat([{"role": "user", "content": "hi"}], model="fern-gross")
        self.assertEqual(calls, ["fern-gross", "fern-gross", "lokal-klein"])

    def test_explicit_identical_fallback_is_still_honoured(self):
        """Ein ausdruecklich uebergebener Fallback bleibt das Wort des Aufrufers.

        Nur der Modul-Default weicht aus (siehe Test darueber) — wer explizit
        dasselbe Modell nennt, bekommt keinen dritten Versuch untergeschoben.
        """
        calls = []
        def fake_urlopen(req, timeout=None):
            calls.append(json.loads(req.data.decode("utf-8"))["model"])
            raise TimeoutError("timed out")
        with mock.patch.object(llm.urllib.request, "urlopen", side_effect=fake_urlopen):
            with self.assertRaises(llm.LlmError):
                llm.chat([{"role": "user", "content": "hi"}],
                         model=llm.FALLBACK_MODEL, fallback_model=llm.FALLBACK_MODEL)
        self.assertEqual(calls, [llm.FALLBACK_MODEL, llm.FALLBACK_MODEL])

    def test_uses_configured_fallback_by_default(self):
        """Ohne explizites Argument greift FALLBACK_MODEL aus dem Modul."""
        calls = []
        def fake_urlopen(req, timeout=None):
            model = json.loads(req.data.decode("utf-8"))["model"]
            calls.append(model)
            if model != llm.FALLBACK_MODEL:
                raise TimeoutError("timed out")
            return _Resp({"choices": [{"message": {"content": "ok"}}]})
        with mock.patch.object(llm.urllib.request, "urlopen", side_effect=fake_urlopen):
            llm.chat([{"role": "user", "content": "hi"}], model="gross")
        self.assertEqual(calls[-1], llm.FALLBACK_MODEL)


if __name__ == "__main__":
    unittest.main()
