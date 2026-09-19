"""Entlaedt lokal geladene Modelle, die im Soll nicht vorkommen.

Gegenstueck zu reconcile.py: das plant, was GELADEN gehoert, das hier
raeumt weg, was niemand braucht.

Anlass (19.09.2026): Auf der Studio lagen 'google/gemma-4-31b' (33,8 GB)
und 'qwen/qwen3.6-35b-a3b' (20,4 GB) dauerhaft im Speicher — beide ohne
einen einzigen Nutzer, beide von MLX auf 262.144 Kontext aufgezogen
("context auto-fit", LM-Studio-Bug #2250, kein Workaround). Von 128 GB
waren 176 MB frei. Ab 04:00 scheiterten 48 Agenten-Runs an
"Model loading was stopped due to insufficient system resources".

Der Waerter greift bewusst zurueckhaltend ein — er entlaedt nur, wenn
NICHTS dagegen spricht.
"""

STATUS_ARBEITET = {"processingprompt", "generating", "computingembedding",
                   "loading", "unloading"}


def erlaubte_keys(desired, geraet="studio"):
    """Alle Namen, unter denen ein Soll-Modell dieses Geraets auftreten kann."""
    keys = set()
    for e in desired:
        if e.get("device") != geraet:
            continue
        for feld in ("ps_key", "load_key"):
            if e.get(feld):
                keys.add(e[feld])
    return keys


def _bleibt_warum(m, erlaubt, jetzt_ms, ruhefrist_ms):
    """Grund, das Modell in Ruhe zu lassen — oder None, wenn es weg darf."""
    # Fremde Geraete gehoeren dem Verbund. Die WHITESTAG-AI traegt die
    # Agentenflotte; ein Fehlgriff hier legt 37 Agenten lahm.
    if m.get("deviceIdentifier") is not None:
        return "liegt auf einem anderen Geraet"

    if m.get("type") != "llm":
        return "kein Sprachmodell (Embeddings bleiben immer)"

    if {m.get("modelKey"), m.get("identifier")} & erlaubt:
        return "steht im Soll"

    status = str(m.get("status") or "").lower()
    if status in STATUS_ARBEITET:
        return f"arbeitet gerade ({m.get('status')})"

    if m.get("queued"):
        return f"hat {m['queued']} wartende Anfrage(n)"

    # Ein TTL heisst: jemand hat das Modell bewusst auf Zeit geholt und
    # LM Studio raeumt es selbst weg. So laedt der Vault-Tagger nachts
    # sein 31B — da faehrt der Waerter nicht dazwischen.
    if m.get("ttlMs"):
        return f"traegt ein TTL ({int(m['ttlMs'] / 1000)} s)"

    # 'idle' heisst nur "gerade keine Anfrage", nicht "fertig": zwischen
    # zwei Aufrufen eines laufenden Jobs steht jedes Modell auf idle.
    zuletzt = m.get("lastUsedTime")
    if zuletzt is None:
        return "letzte Nutzung unbekannt"
    ruhe_ms = jetzt_ms - zuletzt
    if ruhe_ms < ruhefrist_ms:
        return f"vor {int(ruhe_ms / 60000)} min benutzt"

    return None


def plan_evictions(loaded, erlaubt, jetzt_ms, ruhefrist_ms):
    """-> Liste der Modelle, die entladen werden sollen."""
    aktionen = []
    for m in loaded:
        if _bleibt_warum(m, set(erlaubt), jetzt_ms, ruhefrist_ms) is not None:
            continue
        ruhe_min = int((jetzt_ms - m["lastUsedTime"]) / 60000)
        aktionen.append({
            "model_key": m.get("modelKey"),
            "identifier": m.get("identifier") or m.get("modelKey"),
            "gigabyte": round((m.get("sizeBytes") or 0) / 1_000_000_000, 2),
            "ruhe_min": ruhe_min,
            "grund": f"nicht im Soll, seit {ruhe_min} min unbenutzt",
        })
    return aktionen


def bericht(loaded, erlaubt, jetzt_ms, ruhefrist_ms):
    """Zeile je geladenem Modell — fuer das Log, damit nachvollziehbar
    bleibt, warum etwas NICHT entladen wurde."""
    zeilen = []
    erlaubt = set(erlaubt)
    for m in loaded:
        grund = _bleibt_warum(m, erlaubt, jetzt_ms, ruhefrist_ms)
        name = m.get("modelKey") or m.get("identifier")
        zeilen.append(f"  {name:<40} {'bleibt: ' + grund if grund else 'ENTLADEN'}")
    return zeilen
