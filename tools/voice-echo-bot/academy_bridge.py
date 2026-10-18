# tools/voice-echo-bot/academy_bridge.py
"""Reine Erkennungs-/Schreiblogik für die Academy-Auto-Brücke im Bot.

Verbindet Telegram-Rückkanal (Approve/Reject-Buttons, Freitext-Reply auf den
Academy-Digest) mit dem lokalen intent.json, das der academy_auto.executor
am nächsten Lauf aufgreift. Fire-and-forget: der Bot soll den Executor
anstoßen können, ohne selbst auf ihn zu warten oder an ihm zu hängen.
"""
from __future__ import annotations

import json
import os
import subprocess

ACADEMY_MARKER = "Academy-Auto — Tagesstand"


def parse_callback(data):
    """'academy:approve:<ts>' -> ('approve', ts); Fremd-Callback -> None."""
    if not isinstance(data, str) or not data.startswith("academy:"):
        return None
    parts = data.split(":", 2)
    if len(parts) != 3 or parts[1] not in ("approve", "reject"):
        return None
    return (parts[1], parts[2])


def is_academy_reply(reply_to_text) -> bool:
    return isinstance(reply_to_text, str) and ACADEMY_MARKER in reply_to_text


def build_intent_dict(kind, text, ref_run_ts, now_ts) -> dict:
    return {"ts": now_ts, "kind": kind, "text": text, "ref_run_ts": ref_run_ts}


def write_intent_file(path, d) -> None:
    path = str(path)
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def trigger_executor(academy_auto_dir) -> None:
    """Fire-and-forget: Executor im Deploy-Verzeichnis anstoßen. Fail-soft."""
    try:
        subprocess.Popen(
            ["python3", "-m", "academy_auto.executor"],
            cwd=academy_auto_dir,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass
