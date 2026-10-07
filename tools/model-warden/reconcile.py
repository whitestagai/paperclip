CTX_TOLERANCE = 512  # kleine Abweichungen (Rundung LM Studio) ignorieren

def plan_actions(desired, loaded, devices, available):
    actions = []
    for entry in desired:
        dev_sym = entry["device"]
        if dev_sym not in available:
            continue  # day-only auf abwesendem Geraet: still ueberspringen
        device_id = devices.get(dev_sym)
        match = None
        for m in loaded:
            # ps_key ist der LM-Studio-Identifier. Bei den meisten
            # Eintraegen ist er gleich dem modelKey, am Node WHITESTAG-AI
            # aber nicht (gemma-4-31b-win auf gemma-4-31b-it@q4_k_m) —
            # darum gegen beide vergleichen, sonst gilt das Soll dort als
            # unerfuellt und der Lader laedt bei jedem Lauf erneut.
            if entry["ps_key"] not in (m.get("model_key"), m.get("identifier")):
                continue
            m_is_studio = m["device_id"] is None
            if (dev_sym == "studio" and m_is_studio) or (m["device_id"] == device_id):
                match = m
                break
        if match is None:
            actions.append({"action": "load", "entry": entry, "reason": "fehlt"})
        elif entry["ctx"] is not None and match["ctx"] is not None and abs(match["ctx"] - entry["ctx"]) > CTX_TOLERANCE:
            actions.append({"action": "ctx_mismatch", "entry": entry,
                            "reason": f"ctx {match['ctx']} != soll {entry['ctx']}"})
    return actions
