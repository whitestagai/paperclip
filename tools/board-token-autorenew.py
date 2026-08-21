#!/usr/bin/env python3
"""
Paperclip Board-Token Auto-Renew
================================
Hält den Board-Token in ~/.paperclip/auth.json dauerhaft gültig, damit
CLI/Watcher nie wieder an der 30-Tage-TTL sterben (vgl. Memory
project_deliverable_watcher_token_ttl + n8n-versioning-and-restart).

Logik (täglich via launchd ing.paperclip.board-token-autorenew):
  1. Token aus auth.json lesen, sha256-Hash bilden (= board_api_keys.key_hash).
  2. Aktiven, nicht-widerrufenen Key in der DB suchen.
  3. Läuft er in > RENEW_WITHIN_DAYS Tagen ab -> nichts tun.
  4. Läuft er bald/schon ab -> expires_at auf now()+30d verlängern
     (Token bleibt gleich, kein auth.json-Schreiben nötig).
  5. Kein passender Key (Token extern rotiert/verloren) -> frischen Key
     über den offiziellen cli-auth-Challenge-Flow prägen (Server erzeugt
     Token+Hash; wir replizieren das Approve per DB, da der Approve-Endpoint
     im authenticated-Modus eine Browser-Session verlangt) und auth.json neu
     schreiben.
  6. Deliverable-Watcher neu treten.

Alles idempotent und self-healing. Läuft nur lokal, vom Eigentümer autorisiert.
"""
import json, os, sys, subprocess, hashlib, datetime, urllib.request, urllib.error

HOME = os.path.expanduser("~")
AUTH_JSON = os.path.join(HOME, ".paperclip", "auth.json")
API_BASE = os.environ.get("PAPERCLIP_API_URL", "http://localhost:3100").rstrip("/")
PSQL_DSN = "postgresql://paperclip:paperclip@localhost:54329/paperclip"
WATCHER_LABEL = "ing.paperclip.walter-deliverable"
RENEW_WITHIN_DAYS = 7          # verlängern, sobald Ablauf näher als das
NEW_TTL_DAYS = 30
WALTER_USER_ID = "18r34Ghx5N0LHRptMCT6Fp1WaoGqhvc9"

def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)

def psql(sql):
    r = subprocess.run(["psql", PSQL_DSN, "-At", "-F", "|", "-v", "ON_ERROR_STOP=1", "-c", sql],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"psql failed: {r.stderr.strip()}")
    return r.stdout.strip()

def load_auth():
    with open(AUTH_JSON) as f:
        return json.load(f)

def get_entry(d):
    creds = d["credentials"]
    # auth.json ist nach der Ausstellungs-URL geschluesselt: erst die
    # konfigurierte Adresse, dann die historischen Schreibweisen, zuletzt
    # der einzige Eintrag.
    for key in (API_BASE, "http://localhost:3100", "http://127.0.0.1:3100"):
        if key in creds:
            return creds[key]
    if len(creds) == 1:
        return next(iter(creds.values()))
    raise KeyError(f"Kein Credential fuer {API_BASE} in {AUTH_JSON}")

def sha256(s):
    return hashlib.sha256(s.encode()).hexdigest()

def kickstart_watcher():
    uid = os.getuid()
    subprocess.run(["launchctl", "kickstart", "-k", f"gui/{uid}/{WATCHER_LABEL}"],
                   capture_output=True, text=True)
    log(f"Watcher {WATCHER_LABEL} neu getreten.")

def extend_key(key_hash):
    psql(f"UPDATE board_api_keys SET expires_at = now() + interval '{NEW_TTL_DAYS} days' "
         f"WHERE key_hash='{key_hash}' AND revoked_at IS NULL;")
    new_exp = psql(f"SELECT expires_at::date FROM board_api_keys WHERE key_hash='{key_hash}' AND revoked_at IS NULL;")
    log(f"Token verlängert -> gültig bis {new_exp}.")

def mint_fresh():
    """Neuen Token über Challenge-Flow prägen + auth.json neu schreiben."""
    log("Kein passender Key gefunden -> präge frischen Token via Challenge-Flow.")
    body = json.dumps({"command": "board-token-autorenew", "requestedAccess": "board"}).encode()
    req = urllib.request.Request(f"{API_BASE}/api/cli-auth/challenges", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        ch = json.load(resp)
    cid = ch["id"]; new_token = ch["boardApiToken"]
    # Approve replizieren: board_api_key aus pending_key_hash anlegen + Challenge markieren
    psql(
        "BEGIN;"
        "INSERT INTO board_api_keys (id, user_id, name, key_hash, expires_at, created_at) "
        f"SELECT gen_random_uuid(), '{WALTER_USER_ID}', pending_key_name, pending_key_hash, "
        f"now() + interval '{NEW_TTL_DAYS} days', now() FROM cli_auth_challenges WHERE id='{cid}';"
        "UPDATE cli_auth_challenges c SET approved_by_user_id='" + WALTER_USER_ID + "', "
        "board_api_key_id=(SELECT id FROM board_api_keys WHERE key_hash=c.pending_key_hash ORDER BY created_at DESC LIMIT 1), "
        f"approved_at=now(), updated_at=now() WHERE c.id='{cid}';"
        "COMMIT;"
    )
    # auth.json aktualisieren (mit Backup)
    d = load_auth(); e = get_entry(d)
    subprocess.run(["cp", AUTH_JSON, AUTH_JSON + ".bak-autorenew"], capture_output=True)
    e["token"] = new_token
    e["updatedAt"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    with open(AUTH_JSON, "w") as f:
        json.dump(d, f, indent=2)
    log(f"Frischer Token in auth.json eingetragen ({new_token[:18]}…).")

def main():
    try:
        d = load_auth(); token = get_entry(d)["token"]
    except Exception as ex:
        log(f"FEHLER beim Lesen von auth.json: {ex}"); return 1
    key_hash = sha256(token)
    row = psql(f"SELECT expires_at, (expires_at > now() + interval '{RENEW_WITHIN_DAYS} days') "
               f"FROM board_api_keys WHERE key_hash='{key_hash}' AND revoked_at IS NULL "
               f"ORDER BY expires_at DESC LIMIT 1;")
    if not row:
        mint_fresh(); kickstart_watcher(); return 0
    expires_at, healthy = row.split("|")
    if healthy == "t":
        log(f"Token gesund (gültig bis {expires_at[:10]}, > {RENEW_WITHIN_DAYS} Tage) — nichts zu tun.")
        return 0
    extend_key(key_hash); kickstart_watcher(); return 0

if __name__ == "__main__":
    sys.exit(main())
