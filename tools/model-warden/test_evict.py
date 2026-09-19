from evict import erlaubte_keys, plan_evictions

JETZT = 1_800_000_000_000  # ms
MINUTE = 60_000


def modell(**kw):
    """Ein Eintrag wie ihn 'lms ps --json' liefert; Vorgabe = entladbar."""
    basis = {
        "type": "llm",
        "modelKey": "irgendwas/gross-31b",
        "identifier": "irgendwas/gross-31b",
        "deviceIdentifier": None,          # None = lokal auf der Studio
        "ttlMs": None,
        "status": "idle",
        "queued": 0,
        "lastUsedTime": JETZT - 60 * MINUTE,
        "sizeBytes": 33_800_000_000,
        "contextLength": 262144,
    }
    basis.update(kw)
    return basis


def plan(*modelle, erlaubt=frozenset(), ruhefrist_min=20):
    return plan_evictions(list(modelle), erlaubt, JETZT, ruhefrist_min * MINUTE)


# --- Der Normalfall, für den das Ganze gebaut ist --------------------------

def test_unerwuenschtes_lokales_modell_wird_entladen():
    aktionen = plan(modell())
    assert [a["model_key"] for a in aktionen] == ["irgendwas/gross-31b"]


def test_entladen_nennt_den_grund_und_die_groesse():
    a = plan(modell())[0]
    assert "nicht im Soll" in a["grund"]
    assert a["gigabyte"] == 33.8


# --- Was NIE angefasst werden darf ----------------------------------------

def test_modell_auf_fremdem_geraet_bleibt():
    """WHITESTAG-AI traegt die Agentenflotte — da fasst der Waerter nichts an."""
    assert plan(modell(deviceIdentifier="whitestag-ai-1")) == []


def test_erlaubtes_modell_bleibt():
    assert plan(modell(modelKey="google/gemma-4-12b"),
                erlaubt={"google/gemma-4-12b"}) == []


def test_erlaubt_greift_auch_ueber_den_identifier():
    """resident-set kennt ps_key und load_key; beide muessen schuetzen."""
    assert plan(modell(modelKey="a/b", identifier="kurzname"),
                erlaubt={"kurzname"}) == []


def test_arbeitendes_modell_bleibt():
    assert plan(modell(status="processingPrompt")) == []
    assert plan(modell(status="generating")) == []
    assert plan(modell(status="computingEmbedding")) == []


def test_modell_mit_wartender_anfrage_bleibt():
    assert plan(modell(queued=1)) == []


def test_modell_mit_ttl_bleibt():
    """Wer ein TTL traegt, wird von LM Studio selbst geraeumt.
    Genau so holt sich der Vault-Tagger nachts sein 31B."""
    assert plan(modell(ttlMs=1_800_000)) == []


def test_frisch_benutztes_modell_bleibt():
    """Schutz gegen das Rennen mit einem gerade laufenden Job: zwischen zwei
    Anfragen steht ein Modell auf 'idle', ist aber mitten in der Arbeit."""
    assert plan(modell(lastUsedTime=JETZT - 5 * MINUTE)) == []


def test_ruhefrist_ist_die_grenze():
    assert plan(modell(lastUsedTime=JETZT - 19 * MINUTE)) == []
    assert len(plan(modell(lastUsedTime=JETZT - 21 * MINUTE))) == 1


def test_embeddings_bleiben_auch_ohne_eintrag():
    """Winzig, staendig im Einsatz, und ihr Fehlen bricht die RAG-Ketten."""
    assert plan(modell(type="embeddings", sizeBytes=634_000_000)) == []


def test_unbekannte_letzte_nutzung_gilt_als_frisch():
    assert plan(modell(lastUsedTime=None)) == []


# --- Mehrere auf einmal ----------------------------------------------------

def test_trennt_sauber_zwischen_behalten_und_entladen():
    aktionen = plan(
        modell(modelKey="google/gemma-4-12b"),              # erlaubt
        modell(modelKey="google/gemma-4-31b", ttlMs=900000),  # Tagger, mit TTL
        modell(modelKey="qwen/qwen3.6-35b-a3b"),            # Karteileiche
        modell(modelKey="gemma-4-31b-it", deviceIdentifier="rtx-1"),  # Node
        erlaubt={"google/gemma-4-12b"},
    )
    assert [a["model_key"] for a in aktionen] == ["qwen/qwen3.6-35b-a3b"]


# --- Erlaubt-Liste aus dem resident-set ------------------------------------

def test_erlaubte_keys_nimmt_nur_die_studio_eintraege():
    desired = [
        {"device": "studio", "ps_key": "a", "load_key": "a-lang"},
        {"device": "rtx", "ps_key": "b", "load_key": "b-lang"},
    ]
    assert erlaubte_keys(desired, "studio") == {"a", "a-lang"}
