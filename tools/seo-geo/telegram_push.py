"""Direkter Jarvis-Bot-Push für SEO-Freigaben (stdlib urllib, im seo-geo-venv).

Kein Prozess-Coupling zum laufenden Bot — wir sprechen dieselbe Bot-Token-API an.
Der laufende Bot bedient nur die *eingehenden* Callbacks."""
import json, os, urllib.request, uuid

def load_bot_token(env_path):
    with open(os.path.expanduser(env_path), encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if line.startswith("export "):
                line = line[len("export "):]
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise KeyError("TELEGRAM_BOT_TOKEN nicht in " + env_path)

def _urllib_sender(bot_token):
    api = "https://api.telegram.org/bot{}".format(bot_token)
    def send(method, params):
        if method == "sendDocument":
            _send_document(api, params)
            return
        data = json.dumps(params).encode("utf-8")
        req = urllib.request.Request("{}/{}".format(api, method), data=data,
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=30).read()
    return send

def _send_document(api, params):
    boundary = uuid.uuid4().hex
    with open(params["_doc_path"], "rb") as fh:
        content = fh.read()
    parts = []
    for k, v in (("chat_id", params["chat_id"]), ("caption", params.get("caption", ""))):
        parts += ["--" + boundary,
                  'Content-Disposition: form-data; name="{}"'.format(k), "", str(v)]
    head = ("--{b}\r\nContent-Disposition: form-data; name=\"document\"; "
            "filename=\"aenderungen.txt\"\r\nContent-Type: text/plain\r\n\r\n").format(b=boundary)
    body = ("\r\n".join(parts) + "\r\n").encode("utf-8") + head.encode("utf-8") + \
           content + ("\r\n--{}--\r\n".format(boundary)).encode("utf-8")
    req = urllib.request.Request("{}/sendDocument".format(api), data=body,
        headers={"Content-Type": "multipart/form-data; boundary={}".format(boundary)})
    urllib.request.urlopen(req, timeout=30).read()

def push_approval(bot_token, chat_id, caption, doc_path, approval_token, *, sender=None):
    send = sender or _urllib_sender(bot_token)
    send("sendDocument", {"chat_id": chat_id, "caption": caption, "_doc_path": doc_path})
    send("sendMessage", {"chat_id": chat_id,
        # Token im Text, damit eine Freitext-Antwort (Reply) ihn zuordnen kann.
        "text": caption + "\n\nFreigeben? (Token " + approval_token + ")",
        "reply_markup": {"inline_keyboard": [[
            {"text": "✅ Freigeben", "callback_data": "seo:ok:" + approval_token},
            {"text": "❌ Ablehnen", "callback_data": "seo:no:" + approval_token}]]}})

def push_text(bot_token, chat_id, text, *, sender=None):
    send = sender or _urllib_sender(bot_token)
    send("sendMessage", {"chat_id": chat_id, "text": text})
