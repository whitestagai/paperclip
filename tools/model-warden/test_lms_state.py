from lms_state import resolve_devices, parse_loaded, available_devices

LINK = '{"deviceName":"MacStudioM4Max128","deviceIdentifier":"S1","peers":[' \
       '{"deviceName":"MacbookM5Mx128","deviceIdentifier":"M1"},' \
       '{"deviceName":"RTX Pro 6000","deviceIdentifier":"R1"}]}'
LINK_NIGHT = '{"deviceName":"MacStudioM4Max128","deviceIdentifier":"S1","peers":[' \
             '{"deviceName":"MacbookM5Mx128","deviceIdentifier":"M1"}]}'
PS = '[{"modelKey":"gemma-4-31b-it-mlx","contextLength":65000,"deviceIdentifier":null},' \
     '{"modelKey":"qwen/qwen3-coder-next","contextLength":131328,"deviceIdentifier":"R1"}]'

def test_resolve_devices():
    d = resolve_devices(LINK)
    assert d["studio"] == "S1" and d["macbook"] == "M1" and d["rtx"] == "R1"

def test_available_excludes_absent_rtx():
    assert available_devices(LINK_NIGHT) == {"studio", "macbook"}
    assert "rtx" in available_devices(LINK)

def test_parse_loaded():
    # Feldweise statt auf Dict-Gleichheit: parse_loaded liefert seit
    # 07.10.2026 zusaetzlich "identifier", und ein Test, der die exakte
    # Dict-Form zusichert, bricht bei jeder Erweiterung ohne echten Befund.
    loaded = parse_loaded(PS)
    nach_key = {m["model_key"]: m for m in loaded}
    assert nach_key["gemma-4-31b-it-mlx"]["ctx"] == 65000
    assert nach_key["gemma-4-31b-it-mlx"]["device_id"] is None
    assert nach_key["qwen/qwen3-coder-next"]["ctx"] == 131328
    assert nach_key["qwen/qwen3-coder-next"]["device_id"] == "R1"


# --- Node WHITESTAG-AI, ergaenzt 07.10.2026 -------------------------------
# Das Geraet ist seit 06.10. Fallback-Traeger von 37 Agenten. Fehlt es in
# _symbol/available_devices, ueberspringt plan_actions seine Eintraege
# STILL — der Lader wuerde die Fallback-Modelle nie laden.
LINK_MIT_NODE = '{"deviceName":"MacStudioM4Max128","deviceIdentifier":"S1","peers":[' \
                '{"deviceName":"RTX Pro 6000","deviceIdentifier":"R1"},' \
                '{"deviceName":"WHITESTAG-AI","deviceIdentifier":"W1"}]}'

def test_resolve_devices_erkennt_whitestag_ai():
    d = resolve_devices(LINK_MIT_NODE)
    assert d["whitestag-ai"] == "W1"

def test_available_devices_enthaelt_whitestag_ai():
    assert available_devices(LINK_MIT_NODE) == {"studio", "rtx", "whitestag-ai"}

def test_parse_loaded_liefert_identifier():
    """Der Identifier ist am Node NICHT gleich dem modelKey.

    `gemma-4-31b-win` (Identifier) laeuft auf `gemma-4-31b-it@q4_k_m`
    (modelKey). Ohne den Identifier kann reconcile nicht erkennen, dass das
    Soll bereits erfuellt ist.
    """
    ps = '[{"identifier":"gemma-4-31b-win","modelKey":"gemma-4-31b-it@q4_k_m",' \
         '"contextLength":98304,"deviceIdentifier":"W1"}]'
    loaded = parse_loaded(ps)
    assert loaded[0]["identifier"] == "gemma-4-31b-win"
    assert loaded[0]["model_key"] == "gemma-4-31b-it@q4_k_m"
