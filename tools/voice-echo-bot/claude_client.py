# tools/voice-echo-bot/claude_client.py
"""Fragt Claude über die Claude-Code-Kommandozeile (`claude -p`).

Für Jarvis' Netzfragen und alles, was mit „frag Claude" beginnt. Läuft über
Walters Claude-Abo (OAuth im Schlüsselbund) — auf dem Studio gibt es keinen
API-Schlüssel, deshalb auch kein `--bare` (das liest nur ANTHROPIC_API_KEY).

Schlank aufgerufen, weil jede Sekunde im Sprachpfad zählt: eigener kurzer
System-Prompt statt des Claude-Code-Prompts, nur Websuche und Webabruf, keine
MCP-Server, keine Einstellungen, niedriger Denkaufwand, leerer Arbeitsordner
(keine CLAUDE.md). Gemessen 28.10.2026: Wetterfrage 10 s statt 25 s mit
Standardaufruf, Wissensfrage ohne Suche 4 s; haiku war mit 19 s langsamer.

Nie Vault-Daten hierher geben — die Antwort entsteht außer Haus. Die Sperre
dafür sitzt im Aufrufer (jarvis_brain: `web_erlaubt`).

Hinweis: läuft im Satelliten-venv unter Python 3.9 — keine `X | None`-Syntax.
"""
import os
import re
import shutil
import subprocess

CLAUDE_BIN = shutil.which("claude") or "/opt/homebrew/bin/claude"
MODELL = "sonnet"
TIMEOUT_SEC = 90
ARBEITSORDNER = os.path.expanduser("~/.paperclip/wake-satellite/claude-cwd")
SYSTEM_PROMPT = (
    "Du bist Jarvis, der Sprachassistent von Walter in Cottbus. Deine Antwort "
    "wird vorgelesen. Antworte auf Deutsch in höchstens zwei kurzen Sätzen, "
    "ohne Markdown, ohne Aufzählungen, ohne URLs. Schreibe Zahlen, Uhrzeiten "
    "und Daten als Wörter aus. Nutze die Websuche für aktuelle Fakten und "
    "nenne die Quelle im Satz (z. B. „laut tagesschau.de“)."
)

_MARKDOWN = re.compile(r"[*_`#]+")


class ClaudeError(Exception):
    """Claude nicht erreichbar, abgebrochen oder ohne Antwort."""


def _prompt(text, history):
    if not history:
        return text
    zeilen = ["Bisheriges Gespräch:"]
    for m in history:
        wer = "Walter" if m.get("role") == "user" else "Jarvis"
        zeilen.append("{}: {}".format(wer, m.get("content", "")))
    zeilen += ["", "Neue Frage von Walter:", text]
    return "\n".join(zeilen)


def frage(text, history=None, waehrenddessen=None, timeout=TIMEOUT_SEC,
          arbeitsordner=ARBEITSORDNER, popen=subprocess.Popen):
    """Gibt Claudes Antwort als vorlesbaren Text zurück, sonst ClaudeError.

    `waehrenddessen` (z. B. die Ansage „Moment, ich schau nach") läuft erst,
    NACHDEM Claude gestartet ist — die Ansage kostet so keine Wartezeit.
    """
    args = [CLAUDE_BIN, "-p", _prompt(text, history),
            "--system-prompt", SYSTEM_PROMPT,
            "--tools", "WebSearch", "WebFetch",
            "--allowedTools", "WebSearch", "WebFetch",
            "--strict-mcp-config", "--setting-sources", "",
            "--no-session-persistence", "--effort", "low", "--model", MODELL]
    os.makedirs(arbeitsordner, exist_ok=True)
    try:
        proc = popen(args, cwd=arbeitsordner, stdin=subprocess.DEVNULL,
                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except OSError as exc:
        raise ClaudeError("claude nicht startbar: {}".format(exc)) from exc
    if waehrenddessen:
        try:
            waehrenddessen()
        except Exception:  # noqa: BLE001 — eine verpatzte Ansage kostet nicht die Antwort
            pass
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        proc.kill()
        proc.communicate()
        raise ClaudeError("claude nach {} s abgebrochen".format(timeout)) from exc
    if proc.returncode != 0:
        raise ClaudeError("claude Exit {}: {}".format(proc.returncode, (err or "").strip()[:200]))
    antwort = _MARKDOWN.sub("", out or "").strip()
    if not antwort:
        raise ClaudeError("claude lieferte keine Antwort")
    return antwort
