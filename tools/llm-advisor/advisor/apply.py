"""Deterministischer Ausfuehrer fuer eine freigegebene Modell-Zuweisung.

Reines Python, keine LLM-Schleife -> kann per Definition nicht in
Max-Iterations laufen. Aendert das Agent-Modell via
`PATCH /api/agents/<id> {"adapterConfig": {"model": ...}}` (merged
serverseitig in die bestehende adapterConfig).
"""
import json
import os
import sys
import urllib.error
import urllib.request

API_BASE = os.environ.get("PAPERCLIP_API_URL", "http://localhost:3100")
LMS_MODELS_URL = os.environ.get("LMSTUDIO_MODELS_URL", "http://localhost:1234/v1/models")


def apply_model_change(agent_id, model, *, get_agent, patch_agent, list_models):
    """Setzt das Modell eines Agenten und verifiziert den Erfolg.

    Externe Raender werden injiziert (DI), damit die Kernlogik testbar bleibt:
    - `list_models()` -> Menge real verfuegbarer Modell-IDs.
    - `get_agent(agent_id)` -> Agent-Dict oder None.
    - `patch_agent(agent_id, body)` -> aktualisierter Agent.
    """
    if model not in list_models():
        raise ValueError(f"unknown model: {model!r} (nicht in /v1/models geladen)")
    if get_agent(agent_id) is None:
        raise ValueError(f"unknown agent: {agent_id!r} (404)")
    updated = patch_agent(agent_id, {"adapterConfig": {"model": model}})
    got = (updated or {}).get("adapterConfig", {}).get("model")
    if got != model:
        raise RuntimeError(f"verify failed: adapterConfig.model={got!r}, erwartet {model!r}")
    return {"agent_id": agent_id, "model": model, "ok": True}


# --- CLI-Wiring: echte HTTP-/API-Raender -----------------------------------

def _token():
    tok = os.environ.get("PAPERCLIP_API_KEY")
    if tok:
        return tok
    auth = json.load(open(os.path.expanduser("~/.paperclip/auth.json")))
    creds = auth["credentials"]
    entry = creds.get(API_BASE) or next(iter(creds.values()))
    return entry["token"]


def _req(method, url, token, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method,
                               headers={"Authorization": f"Bearer {token}",
                                        "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        if method == "GET" and e.code == 404:
            return None
        raise


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) != 2:
        print("usage: apply_proposal.py <agent_id> <model>", file=sys.stderr)
        return 2
    agent_id, model = argv
    token = _token()

    def list_models():
        with urllib.request.urlopen(LMS_MODELS_URL, timeout=10) as resp:
            return {m["id"] for m in json.loads(resp.read().decode()).get("data", [])}

    def get_agent(aid):
        return _req("GET", f"{API_BASE}/api/agents/{aid}", token)

    def patch_agent(aid, body):
        return _req("PATCH", f"{API_BASE}/api/agents/{aid}", token, body)

    try:
        res = apply_model_change(agent_id, model,
                                 get_agent=get_agent, patch_agent=patch_agent, list_models=list_models)
    except (ValueError, RuntimeError) as e:
        print(f"apply abgebrochen (kein PATCH): {e}", file=sys.stderr)
        return 1
    print(json.dumps(res, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
