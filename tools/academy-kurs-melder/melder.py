"""Meldet neu fertiggestellte WHITESTAG.ACADEMY-Kurse per Telegram (Jarvis).

Quelle der Wahrheit ist die Tabelle "## Gebaute Kurse" im Themen-Log — dort
traegt der CEO einen Kurs erst nach dem Lektorat (GRUEN/GELB) ein. Neu ist ein
Kurs, dessen Slug noch nicht in der State-Datei steht. Beim allerersten Lauf
(keine State-Datei) wird nur der Ist-Stand gemerkt, nichts gesendet.

Laeuft per launchd alle 15 Min. Fail-soft: ein Telegram-Fehler laesst den Slug
ungemerkt, damit der naechste Lauf es erneut versucht.
"""
import html
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ACADEMY = Path.home() / "Obsidian" / "WHITESTAG-Vault" / "WHITESTAG.ACADEMY"
THEMEN_LOG = ACADEMY / "Workshops" / "_themen-log.md"
CONTENT_DIR = ACADEMY / "content"
STATE_PATH = Path.home() / ".paperclip" / "academy-kurs-melder-state.json"
ENV_PATH = Path.home() / ".paperclip" / "voice-echo-bot.env"
TENANTS_PATH = Path.home() / ".paperclip" / "voice-echo-tenants.json"

SECTION = "## Gebaute Kurse"


def parse_gebaute_kurse(text):
    """Zeilen der Tabelle 'Gebaute Kurse' -> {slug: {titel, status, is_free, issue}}."""
    kurse = {}
    in_section = False
    for line in text.splitlines():
        if line.startswith("## "):
            in_section = line.strip().startswith(SECTION)
            continue
        if not in_section or not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 6:
            continue
        m = re.fullmatch(r"`([a-z0-9-]+)`", cells[0])
        if not m:
            continue  # Kopfzeile / Trennzeile
        kurse[m.group(1)] = {
            "titel": cells[1],
            "status": cells[2],
            "is_free": cells[3],
            "issue": cells[5],
        }
    return kurse


def read_frontmatter(path):
    """Minimaler YAML-Frontmatter-Leser fuer einfache 'key: wert'-Zeilen."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    fm = {}
    for line in text[3:end].splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        fm[key.strip()] = val
    return fm


def build_message(slug, row, fm):
    titel = fm.get("title") or row["titel"]
    teile = []
    m = re.search(r"\((\d+) Lektionen\)", row["status"])
    if m:
        teile.append("{} Lektionen".format(m.group(1)))
    teile.append("kostenlos" if "kostenlos" in row["is_free"] else "kostenpflichtig")
    m = re.search(r"Lektorat\s+(GRÜN|GELB|ROT)", row["status"])
    if m:
        teile.append("Lektorat " + m.group(1))
    issue = re.search(r"WHI-\d+", row["issue"])
    if issue:
        teile.append(issue.group(0))
    zeilen = ["🎓 <b>Neuer ACADEMY-Kurs fertig</b>", "", "<b>{}</b>".format(html.escape(titel))]
    if fm.get("zusammenfassung"):
        zeilen.append(html.escape(fm["zusammenfassung"]))
    zeilen += ["", html.escape(" · ".join(teile))]
    return "\n".join(zeilen)


def read_env_value(path, key):
    try:
        for line in Path(path).read_text().splitlines():
            line = line.strip()
            if line.startswith("export "):
                line = line[len("export "):]
            k, sep, v = line.partition("=")
            if sep and k.strip() == key:
                return v.strip().strip('"').strip("'")
    except OSError:
        pass
    return None


def resolve_chat_id(path, vault="whitestag"):
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None
    for chat_id, entry in data.items():
        if isinstance(entry, dict) and entry.get("vault") == vault:
            return str(chat_id)
    return None


def send_telegram(text, token, chat_id):
    data = urllib.parse.urlencode({
        "chat_id": chat_id, "text": text, "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode()
    req = urllib.request.Request(
        "https://api.telegram.org/bot{}/sendMessage".format(token), data=data)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return bool(json.loads(resp.read().decode()).get("ok"))
    except Exception as exc:  # noqa: BLE001
        print("Telegram-Fehler: {}".format(exc), file=sys.stderr)
        return False


def load_state(path):
    try:
        return set(json.loads(Path(path).read_text())["gemeldet"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def save_state(path, slugs):
    Path(path).write_text(json.dumps({"gemeldet": sorted(slugs)}, indent=1))


def run(themen_log=THEMEN_LOG, content_dir=CONTENT_DIR, state_path=STATE_PATH,
        sender=None):
    try:
        kurse = parse_gebaute_kurse(Path(themen_log).read_text(encoding="utf-8"))
    except OSError as exc:
        print("Themen-Log nicht lesbar: {}".format(exc), file=sys.stderr)
        return 1
    if not kurse:
        # Leere Tabelle = vermutlich kaputt editiert; nichts als "neu" werten.
        print("keine Kurse in '{}' gefunden".format(SECTION))
        return 0
    gemeldet = load_state(state_path)
    if gemeldet is None:
        save_state(state_path, kurse)
        print("Erstlauf: {} Kurse gemerkt, nichts gesendet".format(len(kurse)))
        return 0
    neu = [s for s in kurse if s not in gemeldet]
    if not neu:
        return 0
    if sender is None:
        token = read_env_value(ENV_PATH, "TELEGRAM_BOT_TOKEN")
        chat_id = resolve_chat_id(TENANTS_PATH)
        if not token or not chat_id:
            print("Token oder Chat-ID fehlt", file=sys.stderr)
            return 1
        sender = lambda text: send_telegram(text, token, chat_id)  # noqa: E731
    for slug in neu:
        fm = read_frontmatter(Path(content_dir) / "{}.md".format(slug))
        if sender(build_message(slug, kurse[slug], fm)):
            gemeldet.add(slug)
            print("gemeldet: {}".format(slug))
        else:
            print("NICHT gemeldet (naechster Lauf versucht erneut): {}".format(slug))
    save_state(state_path, gemeldet)
    return 0


if __name__ == "__main__":
    sys.exit(run())
