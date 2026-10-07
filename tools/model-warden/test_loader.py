from loader import set_preferred_cmd, load_cmd

def test_set_preferred():
    assert set_preferred_cmd("R1") == ["lms", "link", "set-preferred-device", "R1"]

def test_load_cmd_full():
    e = {"load_key": "qwen/qwen3-coder-next", "ctx": 65000, "parallel": 4}
    assert load_cmd(e) == ["lms", "load", "qwen/qwen3-coder-next", "-c", "65000", "--parallel", "4", "-y"]

def test_load_cmd_embeddings_no_ctx():
    e = {"load_key": "text-embedding-bge-m3", "ctx": None, "parallel": None}
    assert load_cmd(e) == ["lms", "load", "text-embedding-bge-m3", "-y"]


def test_load_cmd_setzt_identifier_wenn_er_vom_load_key_abweicht():
    """Ohne --identifier laedt LM Studio unter dem Standardnamen.

    Am Node ist das `gemma-4-31b-it` — genau die ID, die am 03.10.2026 als
    Ursache von 204 max_iterations-Fehlern aus allen Konfigurationen
    entfernt wurde und die dort weiterhin aufloest. Der Lader wuerde also
    eine zweite Instanz unter der verbrannten ID erzeugen, auf einem Geraet
    mit 48,99 von 56 GB belegt.
    """
    e = {"ps_key": "gemma-4-31b-win", "load_key": "gemma-4-31b-it@q4_k_m",
         "ctx": 98304, "parallel": 2}
    assert load_cmd(e) == ["lms", "load", "gemma-4-31b-it@q4_k_m",
                           "--identifier", "gemma-4-31b-win",
                           "-c", "98304", "--parallel", "2", "-y"]

def test_load_cmd_ohne_identifier_wenn_ps_key_gleich_load_key():
    e = {"ps_key": "google/gemma-4-31b", "load_key": "google/gemma-4-31b",
         "ctx": 98304, "parallel": 4}
    assert load_cmd(e) == ["lms", "load", "google/gemma-4-31b",
                           "-c", "98304", "--parallel", "4", "-y"]
