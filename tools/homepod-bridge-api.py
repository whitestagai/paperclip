#!/usr/bin/env python3
"""homepod-bridge-api.py — kleiner LAN-HTTP-Service.

GET/POST /speak/<secret>  → fragt Paperclip nach pending WHITESTAG-Approvals,
                            baut den Ansage-Text, ruft homepod-speak.sh,
                            antwortet mit JSON {"spoken": "...", "count": N}.

Lauscht auf 0.0.0.0:8419 (LAN). Secret wird aus ~/.paperclip/state/homepod-bridge.secret gelesen.
"""

from __future__ import annotations

import http.server
import json
import os
import subprocess
import urllib.request

PORT = 8419
COMPANY_ID = "9cebf3cf-efe8-4597-a400-f06488900a87"
PAPERCLIP_BASE = os.environ.get("PAPERCLIP_API_URL", "http://127.0.0.1:3100").rstrip("/")
API_BASE = f"{PAPERCLIP_BASE}/api"
HOME = os.path.expanduser("~")
AUTH_FILE = f"{HOME}/.paperclip/auth.json"
SECRET_FILE = f"{HOME}/.paperclip/state/homepod-bridge.secret"
SPEAK_SCRIPT = f"{HOME}/.paperclip/scripts/homepod-speak.sh"
MUTE_FLAG = f"{HOME}/.paperclip/state/homepod-watcher.disabled"

TYPE_LABELS = {
    "hire_agent": "Einstellung",
    "approve_ceo_strategy": "Strategie-Freigabe",
}

with open(SECRET_FILE) as f:
    SECRET = f.read().strip()


def load_token() -> str:
    with open(AUTH_FILE) as f:
        data = json.load(f)
    creds = data["credentials"]
    # auth.json ist nach der Ausstellungs-URL geschluesselt: erst die
    # konfigurierte Adresse, dann die historischen Schreibweisen, zuletzt
    # der einzige Eintrag.
    for _key in (PAPERCLIP_BASE, "http://localhost:3100", "http://127.0.0.1:3100"):
        if _key in creds:
            return creds[_key]["token"]
    if len(creds) == 1:
        return next(iter(creds.values()))["token"]
    raise KeyError(f"Kein Token fuer {PAPERCLIP_BASE} in der auth.json")


def fetch_pending() -> list[dict]:
    token = load_token()
    url = f"{API_BASE}/companies/{COMPANY_ID}/approvals?status=pending"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())


def label_for(type_str: str) -> str:
    return TYPE_LABELS.get(type_str, type_str.replace("_", " "))


def build_text(approvals: list[dict]) -> str:
    if not approvals:
        return "Paperclip Whitestag: keine offenen Genehmigungen."
    n = len(approvals)
    labels = [label_for(a.get("type", "?")) for a in approvals[:3]]
    listed = ", ".join(labels) + (" und weitere" if n > 3 else "")
    if n == 1:
        return f"Paperclip Whitestag: eine offene Genehmigung — {listed}"
    return f"Paperclip Whitestag: {n} offene Genehmigungen — {listed}"


def speak(text: str) -> None:
    subprocess.run([SPEAK_SCRIPT, text], check=True, timeout=30)


def reply_json(handler: "Handler", payload: dict, status: int = 200) -> None:
    body = json.dumps(payload).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class Handler(http.server.BaseHTTPRequestHandler):
    def _handle_speak(self) -> None:
        approvals = fetch_pending()
        text = build_text(approvals)
        speak(text)
        reply_json(self, {"spoken": text, "count": len(approvals)})

    def _handle_mute(self) -> None:
        open(MUTE_FLAG, "w").close()
        speak("Paperclip-Ansagen sind jetzt stumm.")
        reply_json(self, {"muted": True})

    def _handle_unmute(self) -> None:
        try:
            os.unlink(MUTE_FLAG)
        except FileNotFoundError:
            pass
        speak("Paperclip-Ansagen sind wieder aktiv.")
        reply_json(self, {"muted": False})

    def _handle(self) -> None:
        try:
            if self.path == f"/speak/{SECRET}":
                self._handle_speak()
            elif self.path == f"/mute/{SECRET}":
                self._handle_mute()
            elif self.path == f"/unmute/{SECRET}":
                self._handle_unmute()
            else:
                self.send_error(404)
        except Exception as e:  # noqa: BLE001
            self.send_error(500, str(e))

    def do_GET(self):  # noqa: N802
        self._handle()

    def do_POST(self):  # noqa: N802
        self._handle()

    def log_message(self, fmt, *args):  # quiet
        pass


def main() -> None:
    server = http.server.HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"homepod-bridge-api listening on 0.0.0.0:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
