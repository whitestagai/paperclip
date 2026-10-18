"""SEO-Freigabe-Callback-Logik für den Jarvis-Bot (stdlib only).

Liest das gemeinsame Token-JSON (vom seo-geo-Dienst geschrieben) und ruft
approve+apply deterministisch via Subprozess über das seo-geo-venv auf. Kein
Import von seo-geo — nur das JSON-Format ist geteilt."""
import json, os, re, shutil, subprocess

# Token kommt direkt aus externem Telegram callback_data und wird zu einem
# Dateipfad zusammengesetzt (siehe seo-geo seo_approvals) — ohne Whitelist
# wäre ein Token wie "../evil" ein Path-Traversal-Vektor.
_TOKEN_RE = re.compile(r"[A-Za-z0-9_-]+\Z")


def _valid_token(token):
    return isinstance(token, str) and bool(_TOKEN_RE.match(token))


def parse_callback(data):
    parts = (data or "").split(":")
    if len(parts) == 3 and parts[0] == "seo" and parts[1] in ("ok", "no"):
        token = parts[2]
        if not _valid_token(token):
            return None
        return parts[1], token
    return None

def load_token(approvals_dir, token):
    if not _valid_token(token):
        return None
    path = os.path.join(os.path.expanduser(approvals_dir), token + ".json")
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return None

def _set_status(approvals_dir, token, status, note=None):
    rec = load_token(approvals_dir, token)
    if rec is None:
        return
    rec["status"] = status
    if note is not None:
        rec["note"] = note
    path = os.path.join(os.path.expanduser(approvals_dir), token + ".json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(rec, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

def summarize_last_apply(site_dir, changeset_basename):
    """Liest den Apply-Log EINES bestimmten Changesets.

    Die seo-geo-CLI schreibt pro Changeset genau eine Log-Datei
    `apply-log.<changeset_basename>.json`, nach `failed/` bei einem
    fehlgeschlagenen Lauf, sonst nach `applied/`. Beide Verzeichnisse
    akkumulieren historische Logs über alle Changesets hinweg — deshalb
    muss der Dateiname explizit auf DIESES Changeset eingeschränkt werden,
    sonst liest man versehentlich einen älteren, unpassenden Lauf.
    """
    log_name = "apply-log.{}.json".format(changeset_basename)
    for sub in ("failed", "applied"):
        path = os.path.join(site_dir, sub, log_name)
        if os.path.isfile(path):
            data = json.load(open(path))
            return len(data.get("applied", [])), len(data.get("failed", []))
    return 0, 0

def _run(cfg, runner, subcmd_argv):
    argv = [cfg["seo_geo_venv"], cfg["seo_geo_cli"]] + subcmd_argv
    if runner:
        return runner(argv)
    env = {**os.environ, **cfg.get("wp_env", {})}
    return subprocess.run(argv, env=env).returncode

def apply_token(cfg, rec, *, runner=None):
    if rec.get("status") != "pending":
        return "ℹ️ Diese Freigabe wurde bereits bearbeitet ({}).".format(rec.get("status"))
    root = cfg["seo_geo_root"]
    approve_rc = _run(cfg, runner, ["approve", "--changeset", rec["changeset_path"], "--root", root])
    if approve_rc != 0:
        _set_status(cfg["approvals_dir"], rec["token"], "failed")
        return "⚠️ {} — approve fehlgeschlagen (rc={}). Bitte prüfen.".format(rec["site"], approve_rc)
    rc = _run(cfg, runner, ["apply", "--site", rec["site"],
                            "--sites", cfg["seo_geo_sites"], "--root", root])
    site_dir = os.path.expanduser(os.path.join(root, rec["site"]))
    applied, failed = summarize_last_apply(site_dir, os.path.basename(rec["changeset_path"]))
    status = "failed" if (failed or rc != 0) else "applied"
    _set_status(cfg["approvals_dir"], rec["token"], status)
    if status == "applied":
        return "✅ {} live — {} angewendet, {} Fehler".format(rec["site"], applied, failed)
    return "⚠️ {} — {} angewendet, {} Fehler. Bitte prüfen.".format(rec["site"], applied, failed)

def reject_token(cfg, rec):
    if rec.get("status") != "pending":
        return "ℹ️ Bereits bearbeitet ({}).".format(rec.get("status"))
    _set_status(cfg["approvals_dir"], rec["token"], "rejected")
    # Changeset aus pending/ nach rejected/ verschieben (Spec-Anforderung).
    src = rec.get("changeset_path")
    if src and os.path.isfile(src):
        rej = os.path.join(os.path.dirname(os.path.dirname(src)), "rejected")
        os.makedirs(rej, exist_ok=True)
        shutil.move(src, os.path.join(rej, os.path.basename(src)))
    return "❌ {} abgelehnt. Grund? (Antwort optional)".format(rec["site"])

def note_token(cfg, token, text):
    """Legt Walters Freitext-Antwort als Notiz am Token ab (kein Auto-Apply)."""
    if not _valid_token(token):
        return
    rec = load_token(cfg["approvals_dir"], token)
    if rec is None:
        return
    rec["note"] = text
    path = os.path.join(os.path.expanduser(cfg["approvals_dir"]), token + ".json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(rec, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
