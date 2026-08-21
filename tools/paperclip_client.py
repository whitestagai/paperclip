"""Dünner, stdlib-only Client für die Paperclip Control-Plane.

Die Adresse kommt aus PAPERCLIP_API_URL; ohne die Variable bleibt es beim
bisherigen http://localhost:3100.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

FALLBACK_BASE = "http://localhost:3100"


def api_base() -> str:
    """Basis-URL der Control-Plane, ohne abschliessenden Slash."""
    return os.environ.get("PAPERCLIP_API_URL", FALLBACK_BASE).rstrip("/")


# Rueckwaertskompatibel: Aufrufer, die DEFAULT_BASE importieren, bekommen den
# konfigurierten Wert statt der alten Konstante.
DEFAULT_BASE = api_base()


class ApiError(RuntimeError):
    pass


def load_token(auth_path: str | None = None) -> str:
    auth_path = auth_path or os.path.expanduser("~/.paperclip/auth.json")
    try:
        with open(auth_path) as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return ""
    creds = (data or {}).get("credentials", {})
    # auth.json ist nach der URL geschluesselt, unter der der Token ausgestellt
    # wurde. Erst die konfigurierte Adresse probieren, dann die historischen
    # Schreibweisen, zuletzt den einzigen Eintrag (haeufigster Fall).
    for key in (api_base(), FALLBACK_BASE, "http://127.0.0.1:3100"):
        entry = creds.get(key)
        if entry:
            return entry.get("token", "")
    if len(creds) == 1:
        return next(iter(creds.values())).get("token", "")
    return ""


def _post(url: str, token: str, payload: dict) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {token}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode("utf-8") or "{}"
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        raise ApiError(f"HTTP {e.code} for {url}") from e
    except Exception as e:  # noqa: BLE001
        raise ApiError(f"request failed for {url}: {e}") from e


def create_issue(base: str, token: str, company_id: str, *, title: str,
                 description: str, assignee_agent_id: str | None,
                 priority: str = "medium", parent_id: str | None = None) -> str:
    payload = {"title": title, "description": description, "priority": priority}
    if assignee_agent_id:
        payload["assigneeAgentId"] = assignee_agent_id
    if parent_id:
        payload["parentId"] = parent_id
    out = _post(f"{base}/api/companies/{company_id}/issues", token, payload)
    return out.get("id", "")


def add_comment(base: str, token: str, issue_id: str, body: str) -> None:
    _post(f"{base}/api/issues/{issue_id}/comments", token, {"body": body})
