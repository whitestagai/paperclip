"""Tests der Sammel-Logik. Alles hier ist rein — kein Netz, keine Datenbank."""

from pruefung import Referenz
from waechter import (
    bestand_aus_api,
    laufzeit_aus_lms_ps,
    referenzen_aus_agenten,
    referenzen_aus_launchd_env,
    referenzen_aus_n8n,
    referenzen_aus_template,
)


# ------------------------------------------------------- laufender Dienst

LAUNCHCTL_AUSGABE = """\
io.piiproxy.server = {
	active count = 1
	state = running
	program = /Users/x/.nvm/versions/node/v22.22.0/bin/node
	environment = {
		PATH => /usr/bin:/bin
		PII_PROXY_CLASSIFIER_MODEL => google/gemma-4-12b-qat
		PII_PROXY_CLASSIFIER_FALLBACK_MODEL => google/gemma-4-12b
	}
	default environment = {
		PATH => /usr/bin:/bin
	}
}
"""


def test_launchd_env_liest_das_modell_des_laufenden_dienstes():
    """26.08.: Die plist auf der Platte stand seit einem Tag richtig, der
    laufende Job trug weiter das geloeschte «gemma-4-12b-qat». Die Aufsicht
    las nur die Datei und meldete deshalb «keine Inkonsistenzen», waehrend
    jeder Klassifikator-Aufruf scheiterte."""
    refs = referenzen_aus_launchd_env(LAUNCHCTL_AUSGABE, "PII-Proxy (laufender Dienst)")
    assert Referenz(
        "PII-Proxy (laufender Dienst)", "CLASSIFIER_MODEL", "google/gemma-4-12b-qat"
    ) in refs
    assert Referenz(
        "PII-Proxy (laufender Dienst)", "CLASSIFIER_FALLBACK_MODEL", "google/gemma-4-12b"
    ) in refs


def test_launchd_env_ignoriert_nicht_modellbezogene_variablen():
    refs = referenzen_aus_launchd_env(LAUNCHCTL_AUSGABE, "PII-Proxy (laufender Dienst)")
    assert all("PATH" not in r.feld for r in refs)


def test_launchd_env_ohne_dienst_ist_leer_nicht_kaputt():
    """Ist der Job entladen, gibt launchctl gar keine Umgebung aus. Das ist
    kein Parserfehler — die Nichtverfuegbarkeit meldet der Aufrufer."""
    assert referenzen_aus_launchd_env("Could not find service", "PII-Proxy") == []


# ------------------------------------------------------- Laufzeit-Fenster


LMS_PS = [
    {"identifier": "abiray/qwen3.6-35b-a3b", "contextLength": 98304, "parallel": 5},
    {"identifier": "gemma4-31b-it", "contextLength": 65536, "parallel": 12},
    {"identifier": "text-embedding-bge-m3", "contextLength": 8192, "parallel": None},
]


def test_laufzeit_liest_fenster_und_slots_je_modell():
    z = laufzeit_aus_lms_ps(LMS_PS)
    assert z["abiray/qwen3.6-35b-a3b"] == (98304, 5)
    assert z["gemma4-31b-it"] == (65536, 12)


def test_laufzeit_uebernimmt_auch_modelle_ohne_slots():
    """Einbettungsmodelle melden `parallel: null`. Sie fallen sonst still aus
    der Erfassung, obwohl ihr Fenster genauso kippen kann."""
    assert laufzeit_aus_lms_ps(LMS_PS)["text-embedding-bge-m3"] == (8192, None)


# --------------------------------------------------------------- Bestand


def test_bestand_trennt_heruntergeladen_von_geladen():
    payload = {
        "data": [
            {"id": "gemma4-31b-it", "state": "loaded"},
            {"id": "qwen/qwen3-coder-30b", "state": "not-loaded"},
        ]
    }
    b = bestand_aus_api(payload)
    assert b.vorhanden == frozenset({"gemma4-31b-it", "qwen/qwen3-coder-30b"})
    assert b.geladen == frozenset({"gemma4-31b-it"})


# --------------------------------------------------------------- Paperclip


def test_agent_referenzen_erfassen_auch_das_wirksame_cheap_profil():
    """23.08.: Das cheap-Profil in `runtime_config` zeigte noch aufs MacBook,
    während in `adapter_config` der gewollte Wert stand. Wer nur das
    Primärmodell prüft, sieht davon nichts."""
    zeilen = [
        {
            "firma": "WHITESTAG",
            "name": "CTO",
            "adapter_config": {
                "model": "abiray/qwen3.6-35b-a3b",
                "fallbackModel": "gemma-4-31b-it-mlx",
            },
            "runtime_config": {
                "modelProfiles": {
                    "cheap": {
                        "adapterConfig": {
                            "model": "gemma4-31b-it",
                            "fallbackModel": "google/gemma-4-12b",
                        }
                    }
                }
            },
        }
    ]
    refs = referenzen_aus_agenten(zeilen)
    felder = {r.feld for r in refs}
    assert felder == {
        "adapterConfig.model",
        "adapterConfig.fallbackModel",
        "runtimeConfig.modelProfiles.cheap.model",
        "runtimeConfig.modelProfiles.cheap.fallbackModel",
    }
    assert all(r.quelle == "Paperclip-Agent WHITESTAG/CTO" for r in refs)


def test_agent_ohne_modellfeld_erzeugt_keine_referenz():
    """`adapterType: process` legt Agenten ganz ohne Modellfeld an."""
    assert referenzen_aus_agenten([{"firma": "X", "name": "Y", "adapter_config": {}}]) == []


# --------------------------------------------------------------- n8n


def _wf(nodes):
    return [{"name": "WHITESTAG RAG V3", "nodes": nodes}]


def test_n8n_sticky_notes_werden_ignoriert():
    """Am 23.08. habe ich genau hier falsch geschlossen: Die tote ID stand in
    vier aktiven Workflows — ausschliesslich in Sticky Notes, also wirkungslos.
    Ein Wächter, der die mitzählt, meldet vier Geister."""
    nodes = [
        {
            "name": "Sticht A",
            "type": "n8n-nodes-base.stickyNote",
            "parameters": {"content": "frueher lief das auf qwen3.6-35b-a3b-mlx"},
        }
    ]
    assert referenzen_aus_n8n(_wf(nodes)) == []


def test_n8n_liest_literale_zuweisungen_aus_set_knoten():
    nodes = [
        {
            "name": "Konfiguration",
            "type": "n8n-nodes-base.set",
            "parameters": {
                "assignments": {
                    "assignments": [
                        {"name": "rag_input_pfad", "value": "/tmp/x", "type": "string"},
                        {"name": "embedding_model", "value": "text-embedding-bge-m3"},
                        {"name": "chunking_model", "value": "abiray/qwen3.6-35b-a3b"},
                    ]
                }
            },
        }
    ]
    refs = referenzen_aus_n8n(_wf(nodes))
    assert {(r.feld, r.modell) for r in refs} == {
        ("Konfiguration.embedding_model", "text-embedding-bge-m3"),
        ("Konfiguration.chunking_model", "abiray/qwen3.6-35b-a3b"),
    }


def test_n8n_ausdruecke_sind_keine_referenz():
    """`={{ ... }}` wird erst zur Laufzeit aufgelöst — statisch nicht prüfbar.
    Als „unbekanntes Modell" gemeldet wäre es ein täglicher Fehlalarm."""
    nodes = [
        {
            "name": "OpenAI Chat Model",
            "type": "@n8n/n8n-nodes-langchain.lmChatOpenAi",
            "parameters": {
                "model": {"value": "={{ $('Konfiguration').first().json.chunking_model }}"}
            },
        }
    ]
    assert referenzen_aus_n8n(_wf(nodes)) == []


# --------------------------------------------------------------- Templates


def test_template_liest_das_modell_aus_dem_llm_block():
    text = 'llm:\n  modell: "gemma4-31b-it"\n  endpoint: "http://127.0.0.1:1234/v1"\n'
    assert referenzen_aus_template(text, "Tagger WHITESTAG") == [
        Referenz("Tagger WHITESTAG", "llm.modell", "gemma4-31b-it")
    ]


def test_template_ohne_modellzeile_ist_leer_nicht_kaputt():
    assert referenzen_aus_template("basis:\n  title:\n", "Tagger X") == []
