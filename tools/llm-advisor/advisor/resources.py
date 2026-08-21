"""Parst `lms ls/ps --json` und berechnet das 110-GB-Lade-Budget."""
import json
import subprocess

LMS = "/Users/walterschoenenbroecher.de/.lmstudio/bin/lms"
_GB = 1024 ** 3
VRAM_LIMIT_GB = 110.0

# Welche Geraete laufen durchgaengig? Ein Modell auf einem Geraet, das nachts
# aus ist, taugt nicht fuer Agenten mit Nacht-Last (WHI-3362).
# Unbekannte Fremdgeraete gelten bewusst als NICHT durchgaengig -- lieber eine
# Warnung zu viel als ein Vorschlag, der nachts in llm_unreachable laeuft.
DEVICE_ALWAYS_ON = {
    "Local": True,             # dieser Mac
    "MacbookM5Mx128": True,    # zweiter Mac, 24/7 per LM Link
    "RTX Pro 6000": False,     # nachts aus
}


def _run_lms(subcmd):
    out = subprocess.run([LMS, subcmd, "--json"], capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"lms {subcmd} failed (rc={out.returncode}): {out.stderr.strip()}")
    try:
        return json.loads(out.stdout)
    except json.JSONDecodeError as e:
        raise ValueError(f"lms {subcmd} --json lieferte kein gültiges JSON: {out.stdout[:200]!r}") from e


def fetch_ls():
    return _run_lms("ls")


def fetch_ps():
    return _run_lms("ps")


def fetch_device_names():
    """identifier -> Geraetename aus der Klartext-Tabelle von `lms ps`.

    Der JSON-Ausgabe von `lms ps` fehlt der lesbare Geraetename; sie liefert
    nur den Hash. Faellt die Tabelle aus, bleibt der Hash als Fallback.
    """
    out = subprocess.run([LMS, "ps"], capture_output=True, text=True)
    if out.returncode != 0:
        return {}
    return parse_device_names(out.stdout)


def parse_device_names(table_text):
    """Liest die Spalten IDENTIFIER und DEVICE aus der `lms ps`-Tabelle.

    Spaltenweise nach Kopfzeilen-Offsets, weil Geraetenamen Leerzeichen
    enthalten koennen ("RTX Pro 6000").
    """
    lines = [ln for ln in table_text.splitlines() if ln.strip()]
    if not lines:
        return {}
    header = lines[0]
    try:
        id_end = header.index("MODEL")
        dev_start = header.index("DEVICE")
    except ValueError:
        return {}
    dev_end = header.index("TTL") if "TTL" in header else len(header)

    names = {}
    for line in lines[1:]:
        identifier = line[:id_end].strip()
        device = line[dev_start:dev_end].strip()
        if identifier and device:
            names[identifier] = device
    return names


def parse_models(raw, device_names=None):
    device_names = device_names or {}
    models = []
    for m in raw:
        if m.get("type") != "llm":
            continue
        quant = (m.get("quantization") or {}).get("name", "")
        # None = Mac (Local), Hash = Remote-Link (z.B. RTX Pro 6000)
        device_id = m.get("deviceIdentifier")
        if device_id is None:
            device = "Local"
        else:
            device = device_names.get(m.get("identifier") or m.get("modelKey", ""),
                                      f"remote:{device_id[:8]}")
        models.append({
            "model_key": m.get("modelKey", ""),
            "size_gb": round((m.get("sizeBytes") or 0) / _GB, 2),
            "quant": quant,
            "params": m.get("paramsString", ""),
            "arch": m.get("architecture", ""),
            "device_id": device_id,
            "device": device,
            "always_on": DEVICE_ALWAYS_ON.get(device, False),
            # Nur bei geladenen Modellen (`lms ps`) gesetzt.
            "context_length": m.get("contextLength"),
            "max_context_length": m.get("maxContextLength"),
        })
    return models


def budget_report(all_models, loaded_models, limit_gb=VRAM_LIMIT_GB):
    # Das 110-GB-Limit gilt nur fuer den Mac (Unified Memory). Remote-gelinkte
    # GPUs (deviceIdentifier gesetzt) haben einen eigenen Speicherpool und
    # duerfen das Mac-Budget nicht belasten.
    disk_gb = round(sum(m["size_gb"] for m in all_models), 2)
    local_loaded = [m for m in loaded_models if m.get("device_id") is None]
    remote_loaded = [m for m in loaded_models if m.get("device_id") is not None]
    loaded_gb = round(sum(m["size_gb"] for m in local_loaded), 2)
    remote_gb = round(sum(m["size_gb"] for m in remote_loaded), 2)
    return {
        "limit_gb": limit_gb,
        "disk_gb": disk_gb,
        "loaded_gb": loaded_gb,
        "free_loadable_gb": round(limit_gb - loaded_gb, 2),
        "over_limit": loaded_gb > limit_gb,
        "loaded_keys": [m["model_key"] for m in local_loaded],
        "remote_loaded_gb": remote_gb,
        "remote_keys": [m["model_key"] for m in remote_loaded],
    }
