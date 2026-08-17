# tools/voice-echo-bot/bot.py
"""Jarvis-Bot: Chat-Agent mit Vault-Lookup, Websuche + CEO-Task-Anlage (stdlib only).

Jede Nachricht ist ein normaler Chat: das Denken steckt in `jarvis_brain`, das
sich der Bot mit dem Wake-Satelliten teilt — Vault-Nachschlagen, Websuche und
Issue-Anlage kommen damit aus derselben Quelle, und Aenderungen am Gehirn
erreichen beide Wege.

Der Bot selbst bleibt die Telegram-Seite: Transkription, Antwort-Modus
(Text/Voice), Reply->Kommentar, der CEO-Event-Poll und die beiden
Freigabe-Rueckkanaele (academy-auto, SEO/GEO).
"""
import os
import re
import shutil
import sys
import tempfile
import time
import traceback

from datetime import datetime, timezone

import academy_bridge
import config
import state
import tenants as tenants_mod
import transcribe
import tts
import reply_mode
import notifier
import llm
import vault_client
from telegram_api import Telegram
from paperclip_client import (create_issue, derive_title, add_comment,
                              find_issue_by_identifier, list_issues, resolve_label_id)
import jarvis_brain
from jarvis_brain import LOOKUP_RE, ISSUE_RE, parse_control

IDENT_RE = re.compile(r"([A-Z]{2,5}-\d+)")
SEO_TOKEN_RE = re.compile(r"Token (\w+)")

# Defaults, falls die Config die Academy-Pfade noch nicht setzt.
DEFAULT_ACADEMY_INTENT_PATH = os.path.expanduser("~/.paperclip/academy-auto/intent.json")
DEFAULT_ACADEMY_AUTO_DIR = os.path.expanduser("~/.paperclip/scripts/academy-auto")

# Konversations-Historie pro Chat: max. 8 Turns (= 16 Messages) in-memory.
MAX_HISTORY_MESSAGES = 16


class BotApp:
    def __init__(self, tg, cfg):
        self.tg = tg
        self.cfg = cfg
        self.history = {}  # chat_id -> [{"role","content"}, …] (max 8 Turns)
        # Parallel zur History, ein Eintrag je Turn: hat diese Runde Vault-Daten
        # geliefert? Steuert den Websuche-Notaus, siehe _web_erlaubt().
        self.vault_flags = {}  # chat_id -> [bool, …]
        self.seen = set()
        self._seeded = True

    def _chat_model(self):
        return self.cfg.get("chat_model") or llm.DEFAULT_MODEL

    def _token(self):
        tok = self.cfg["paperclip_token"]
        return tok() if callable(tok) else tok

    # ---- Antwort-Kanal (Text/Voice je Chat) ----
    def _reply(self, chat_id, text, reply_to_message_id=None):
        """Direkte Antwort an den Nutzer gemäß Chat-Antwortmodus.

        voice -> ElevenLabs-TTS + sendVoice; bei TtsError sauberer Fallback
        auf Text + kurzer Hinweis. text (Default) -> send_message wie bisher.
        Gilt nur für direkte Antworten auf Nutzer-Nachrichten/-Aktionen; die
        Rückkanal-Pushes (poll_tenants) bleiben bewusst Text.
        """
        path = self.cfg.get("reply_mode_path")
        if path and reply_mode.get_mode(path, chat_id) == "voice":
            workdir = tempfile.mkdtemp()
            ogg = os.path.join(workdir, "reply.ogg")
            try:
                tts.synthesize(text, self.cfg.get("eleven_api_key"), ogg)
                self.tg.send_voice(chat_id, ogg, reply_to_message_id=reply_to_message_id)
                return
            except tts.TtsError:
                traceback.print_exc()
                self.tg.send_message(chat_id, text)
                self.tg.send_message(chat_id, "⚠️ Sprachausgabe fehlgeschlagen — Antwort als Text.")
                return
            finally:
                shutil.rmtree(workdir, ignore_errors=True)
        self.tg.send_message(chat_id, text)

    # ---- Eingang / Dispatcher ----
    def handle_update(self, update):
        # Der Chat legt Issues jetzt direkt per ISSUE-Token an — es gibt keine
        # Bestätigungs-Buttons mehr für den regulären Chat-Flow. callback_query
        # bedienen zwei getrennte Rückkanäle: Academy-Auto-Freigabe
        # (academy:approve|reject:<ts>) und die SEO/GEO-Freigabe (seo:ok/no:<token>).
        # Getrennt nach data-Präfix, damit beide nebeneinander funktionieren.
        if "callback_query" in update:
            cq = update["callback_query"]
            if (cq.get("data") or "").startswith("academy:"):
                self._handle_academy_callback(cq)
            else:
                self._handle_seo_callback(cq)
            return
        if "message" in update:
            msg = update["message"]
            tenant = tenants_mod.resolve_tenant(self.cfg["tenants"], msg.get("from", {}).get("id"))
            if tenant:
                self._handle_message(tenant, msg)

    def _now_ts(self):
        return datetime.now(timezone.utc).isoformat()

    def _academy_intent_path(self):
        return self.cfg.get("academy_intent_path", DEFAULT_ACADEMY_INTENT_PATH)

    def _academy_auto_dir(self):
        return self.cfg.get("academy_auto_dir", DEFAULT_ACADEMY_AUTO_DIR)

    def _handle_academy_callback(self, cq):
        # Gleiches Fail-Closed-Muster wie im Message-Pfad: nur bekannte
        # Mandanten dürfen intent.json schreiben/den Executor anstoßen.
        sender_id = cq.get("from", {}).get("id")
        tenant = tenants_mod.resolve_tenant(self.cfg["tenants"], sender_id)
        if not tenant:
            return
        parsed = academy_bridge.parse_callback(cq.get("data") or "")
        if parsed is None:
            return
        kind, ref = parsed
        d = academy_bridge.build_intent_dict(kind, "", ref, self._now_ts())
        academy_bridge.write_intent_file(self._academy_intent_path(), d)
        academy_bridge.trigger_executor(self._academy_auto_dir())
        self.tg.answer_callback_query(cq["id"], text="Verstanden — läuft.")

    def _seo_cfg(self):
        return {"approvals_dir": config.SEO_APPROVALS_DIR,
                "seo_geo_venv": config.SEO_GEO_VENV, "seo_geo_cli": config.SEO_GEO_CLI,
                "seo_geo_root": config.SEO_GEO_ROOT, "seo_geo_sites": config.SEO_GEO_SITES,
                "wp_env": config.load_env(config.WHITESTAG_ENV)
                if os.path.exists(config.WHITESTAG_ENV) else {}}

    def _handle_seo_callback(self, cq):
        import seo_gate
        parsed = seo_gate.parse_callback(cq.get("data"))
        if not parsed:
            return
        chat_id = cq.get("message", {}).get("chat", {}).get("id")
        if cq.get("from", {}).get("id") != config.WALTER_CHAT_ID:
            self.tg.answer_callback_query(cq["id"], "nicht berechtigt")
            return
        self.tg.answer_callback_query(cq["id"])
        action, token = parsed
        rec = seo_gate.load_token(config.SEO_APPROVALS_DIR, token)
        if rec is None:
            self.tg.send_message(chat_id, "⚠️ Freigabe nicht mehr gefunden (abgelaufen?).")
            return
        if action == "ok":
            self.tg.send_message(chat_id, "⏳ Wende an …")
            result = seo_gate.apply_token(self._seo_cfg(), rec)
        else:
            result = seo_gate.reject_token(self._seo_cfg(), rec)
        self.tg.send_message(chat_id, result + "\n\n(Token {})".format(token))

    def _extract_text(self, msg):
        """Voice -> Whisper (mit Cleanup) oder Textnachricht; None bei Transkriptionsfehler."""
        if "voice" in msg or "audio" in msg:
            media = msg.get("voice") or msg.get("audio")
            workdir = tempfile.mkdtemp()
            ogg = os.path.join(workdir, "in.oga")
            try:
                path = self.tg.get_file_path(media["file_id"])
                self.tg.download_file(path, ogg)
                return transcribe.transcribe(ogg, self.cfg["whisper_model"], workdir=workdir)
            except transcribe.TranscriptionError:
                self.tg.send_message(msg["chat"]["id"], "Transkription fehlgeschlagen, bitte erneut.")
                return None
            finally:
                shutil.rmtree(workdir, ignore_errors=True)
        return msg.get("text")

    def _handle_message(self, tenant, msg):
        # Modus-Befehle (/text, /voice, ggf. mit @botname-Suffix) setzen nur
        # den Antwortmodus des Chats — kein Issue, keine Transkription.
        raw = msg.get("text")
        if isinstance(raw, str) and raw.strip().startswith("/"):
            cmd = raw.strip().split()[0].split("@")[0].lower()
            if cmd == "/voice":
                reply_mode.set_mode(self.cfg["reply_mode_path"], msg["chat"]["id"], "voice")
                self.tg.send_message(msg["chat"]["id"], "🔊 Antworten jetzt als Sprache.")
                return
            if cmd == "/text":
                reply_mode.set_mode(self.cfg["reply_mode_path"], msg["chat"]["id"], "text")
                self.tg.send_message(msg["chat"]["id"], "🔤 Antworten jetzt als Text.")
                return
        reply_to = msg.get("reply_to_message")
        if reply_to:
            if academy_bridge.is_academy_reply(reply_to.get("text") or ""):
                text = self._extract_text(msg)
                if text:
                    d = academy_bridge.build_intent_dict("direction", text, "", self._now_ts())
                    academy_bridge.write_intent_file(self._academy_intent_path(), d)
                    academy_bridge.trigger_executor(self._academy_auto_dir())
                    self.tg.send_message(msg["chat"]["id"], "✍️ Als Nachtaufgabe notiert.")
                return
            seo_m = SEO_TOKEN_RE.search(reply_to.get("text") or "")
            # Gleicher Chat-Guard wie beim Button-Callback (_handle_seo_callback):
            # nur Walter darf SEO-Freigaben per Freitext-Notiz beschreiben
            # (Multi-Tenant-Bot). Bei fremdem Absender NICHT noten, sondern
            # normal weiterbehandeln.
            if seo_m and msg.get("from", {}).get("id") == config.WALTER_CHAT_ID:
                self._handle_seo_note(tenant, msg, seo_m.group(1))
                return
            m = IDENT_RE.search(reply_to.get("text") or "")
            if m:
                self._handle_reply(tenant, msg, m.group(1))
                return
        text = self._extract_text(msg)
        if text is None:
            return
        if isinstance(text, str) and text.startswith("/"):
            self.tg.send_message(msg["chat"]["id"],
                                 "Schreib oder sprich mir einfach — ich antworte, schlage bei "
                                 "Bedarf im Vault nach, suche im Netz und lege auf Wunsch "
                                 "Aufgaben beim CEO an.")
            return
        self._handle_chat(tenant, msg, text)

    # ---- Reply -> SEO-Freigabe-Notiz (kein Auto-Apply) ----
    def _handle_seo_note(self, tenant, msg, token):
        import seo_gate
        chat_id = msg["chat"]["id"]
        text = self._extract_text(msg)
        if text is None:
            return
        seo_gate.note_token(self._seo_cfg(), token, text)
        self.tg.send_message(
            chat_id,
            "📝 Notiz zur Freigabe {} gespeichert — ich ziehe das manuell nach.".format(token))

    # ---- Reply -> Kommentar ----
    def _handle_reply(self, tenant, msg, identifier):
        chat_id = msg["chat"]["id"]
        text = self._extract_text(msg)
        if text is None:
            return
        token = self._token()
        issue = find_issue_by_identifier(token, tenant["company_id"], identifier,
                                         assignee_agent_id=tenant["ceo_agent_id"])
        if not issue:
            self.tg.send_message(chat_id, "Konnte kein passendes Issue ({}) finden.".format(identifier))
            return
        try:
            add_comment(token, issue["id"], text, resume=True)
            self._reply(chat_id, "✅ Antwort an CEO ({}) gesendet.".format(identifier),
                        reply_to_message_id=msg["message_id"])
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            self.tg.send_message(chat_id, "⚠️ Konnte die Antwort nicht senden, bitte erneut.")

    # ---- Chat-Agent (jarvis_brain: LLM + prompt-gesteuerte Werkzeuge) ----
    def _remember(self, chat_id, user_text, assistant_text, vault_treffer=False):
        hist = self.history.setdefault(chat_id, [])
        hist.append({"role": "user", "content": user_text})
        hist.append({"role": "assistant", "content": assistant_text})
        flags = self.vault_flags.setdefault(chat_id, [])
        flags.append(bool(vault_treffer))
        if len(hist) > MAX_HISTORY_MESSAGES:
            del hist[:len(hist) - MAX_HISTORY_MESSAGES]
        # Merker exakt auf die behaltenen Turns kuerzen — laufen die beiden
        # Listen auseinander, zeigt die Sperre auf die falsche Runde.
        turns = len(hist) // 2
        if len(flags) > turns:
            del flags[:len(flags) - turns]

    def _web_erlaubt(self, chat_id):
        """PII-Notaus: keine Websuche, solange Vault-Daten im Kontext stehen.

        `web_erlaubt=False` sperrt in `jarvis_brain.respond()` das WEB-Werkzeug,
        nachdem ein Lookup private Daten in die History gelegt hat — sonst
        koennte das Modell daraus einen Suchbegriff bilden und Adresse oder
        Telefonnummer nach draussen tragen. Gesperrt wird ueber das Flag, nicht
        ueber einen entzogenen `web_key`: der lokale Websuche-Dienst braucht gar
        keinen Schluessel, ein web_key=None wuerde die Suche also nicht aufhalten.

        Die Sperre haengt am History-FENSTER, nicht an der Gespraechskette wie
        beim Wake-Satelliten: der startet jede Kette ohne History, ein
        Telegram-Chat traegt seine ueber die gesamte Bot-Laufzeit. Sie faellt
        also, sobald die Vault-Runde aus den behaltenen Turns gerutscht ist —
        dauerhaft sperren waere kein Schutz, sondern haette dem Chat nach der
        ersten Kontaktabfrage fuer immer die Websuche genommen.
        """
        return not any(self.vault_flags.get(chat_id, []))

    def _handle_chat(self, tenant, msg, text):
        chat_id = msg["chat"]["id"]
        text = (text or "").strip()
        hist = self.history.get(chat_id, [])
        result = jarvis_brain.respond(text, tenant, self._token(),
                                      self._chat_model(), history=hist,
                                      web_key=self.cfg.get("web_key"),
                                      web_erlaubt=self._web_erlaubt(chat_id))
        kind, answer = result["kind"], result["answer"]
        if kind in ("empty", "unparsed_ok", "unparsed_fail"):
            self.tg.send_message(chat_id, answer)
            return
        self._remember(chat_id, text, answer, vault_treffer=(kind == "lookup"))
        self._reply(chat_id, answer, reply_to_message_id=msg["message_id"])

    # ---- Rückkanal-Poll ----
    def _format_push(self, ev):
        i = ev["issue"]
        ident = i.get("identifier") or (i.get("id") or "?")[:8]
        title = i.get("title") or "(ohne Titel)"
        if ev["kind"] == "done":
            return "✅ Erledigt — {}: {}".format(ident, title)
        return ("🟠 Entscheidung benötigt — {}: {}\n\n"
                "↩️ Antworte auf diese Nachricht (Sprache/Text), um dem CEO zu antworten.").format(ident, title)

    def poll_tenants(self):
        token = self._token()
        # Snapshot: pro Poll-Durchlauf dürfen sich Mandanten mit identischen
        # Issue-IDs (unterschiedliche Companies) nicht gegenseitig als
        # "schon gesehen" markieren.
        base_seen = set(self.seen)
        for uid, tenant in self.cfg["tenants"].items():
            try:
                label_id = resolve_label_id(token, tenant["company_id"], self.cfg["decision_label"])
                issues = list_issues(token, tenant["company_id"],
                                     assignee_agent_id=tenant["ceo_agent_id"])
                # Re-Raise-Fall: Label wurde entfernt (Mensch hat entschieden)
                # und später erneut gesetzt -> Key aus 'seen' droppen, damit
                # collect_events das als neues Event erkennt. Streng auf die
                # Issue-IDs DIESES Mandanten skaliert.
                stale = notifier.reconcile_decision_keys(issues, label_id, base_seen)
                tenant_seen = base_seen - stale if stale else base_seen
                if stale:
                    self.seen -= stale
                events, keys = notifier.collect_events(issues, label_id, tenant_seen)
                if self._seeded:
                    for ev in events:
                        try:
                            self.tg.send_message(int(uid), self._format_push(ev))
                        except Exception:  # noqa: BLE001
                            traceback.print_exc()
                self.seen.update(keys)
            except Exception:  # noqa: BLE001
                traceback.print_exc()
        state.save_state(self.cfg["state_path"], self.seen)
        self._seeded = True

    def _drain(self):
        offset = None
        pending = self.tg.get_updates(offset=-1, timeout=0)
        if pending:
            offset = pending[-1]["update_id"] + 1
        return offset

    def run(self):
        offset = self._drain()
        last_poll = 0.0
        while True:
            try:
                for update in self.tg.get_updates(offset=offset, timeout=config.LONGPOLL_TIMEOUT_SEC):
                    offset = update["update_id"] + 1
                    self.handle_update(update)
            except Exception:  # noqa: BLE001
                traceback.print_exc()
                time.sleep(5)
            now = time.monotonic()
            if now - last_poll >= self.cfg["poll_interval"]:
                try:
                    self.poll_tenants()
                except Exception:  # noqa: BLE001
                    traceback.print_exc()
                last_poll = now


def build_app():
    env = config.load_env(config.ENV_PATH)
    cfg = {
        "tenants": tenants_mod.load_tenants(config.TENANTS_PATH),
        "paperclip_token": config.load_paperclip_token,
        "whisper_model": os.path.expanduser(env["WHISPER_MODEL"]),
        "decision_label": config.DECISION_LABEL,
        "poll_interval": config.POLL_INTERVAL_SEC,
        "state_path": config.STATE_PATH,
        "reply_mode_path": config.REPLY_MODE_PATH,
        "eleven_api_key": env.get("ELEVENLABS_API_KEY"),
        "chat_model": env.get("CHAT_MODEL") or llm.DEFAULT_MODEL,
        "academy_intent_path": config.ACADEMY_INTENT_PATH,
        "academy_auto_dir": config.ACADEMY_AUTO_DIR,
        # Nur der Tavily-Fallback braucht den Schluessel; der lokale
        # Websuche-Dienst laeuft ohne. Fehlt er, sucht Jarvis trotzdem.
        "web_key": env.get("TAVILY_API_KEY"),
    }
    app = BotApp(Telegram(env["TELEGRAM_BOT_TOKEN"]), cfg)
    loaded = state.load_state(config.STATE_PATH)
    app.seen = loaded if loaded is not None else set()
    app._seeded = loaded is not None
    return app


if __name__ == "__main__":
    print("voice-echo jarvis-bot startet…", file=sys.stderr)
    build_app().run()
