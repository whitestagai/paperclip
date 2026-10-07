import json

def _symbol(device_name):
    n = device_name or ""
    if "Studio" in n: return "studio"
    if "acbook" in n: return "macbook"
    if "RTX" in n:    return "rtx"
    # Windows-PC mit RTX 5090 + 3090, seit 06.10.2026 Fallback-Traeger
    # von 37 Agenten. Fehlt er hier, ueberspringt plan_actions seine
    # Eintraege STILL und der Lader laedt die Fallback-Modelle nie.
    if "WHITESTAG" in n: return "whitestag-ai"
    return None

def resolve_devices(link_json):
    d = json.loads(link_json)
    out = {"studio": None, "macbook": None, "rtx": None, "whitestag-ai": None,
           "_self": d.get("deviceIdentifier")}
    for entry in [d] + list(d.get("peers", [])):
        sym = _symbol(entry.get("deviceName"))
        if sym:
            out[sym] = entry.get("deviceIdentifier")
    return out

def available_devices(link_json):
    dev = resolve_devices(link_json)
    return {sym for sym in ("studio", "macbook", "rtx", "whitestag-ai") if dev.get(sym)}

def parse_loaded(ps_json):
    raw = json.loads(ps_json)
    models = raw if isinstance(raw, list) else raw.get("models", [])
    out = []
    for m in models:
        out.append({
            "model_key": m.get("modelKey"),
            # Am Node weicht der Identifier vom modelKey ab
            # (gemma-4-31b-win laeuft auf gemma-4-31b-it@q4_k_m).
            # reconcile braucht beide, sonst gilt das Soll als unerfuellt.
            "identifier": m.get("identifier"),
            "ctx": m.get("contextLength"),
            "device_id": m.get("deviceIdentifier"),
        })
    return out
