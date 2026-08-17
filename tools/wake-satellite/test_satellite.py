import numpy as np
import satellite
import sat_config


def loud(n=1280):  return (np.ones(n, dtype=np.int16) * 5000)
def quiet(n=1280): return np.zeros(n, dtype=np.int16)


def _deps():
    return {"whisper_model": "m.bin", "eleven_key": "k",
            "chat_model": "google/gemma-4-12b", "token": "tok"}


def _turn():
    """Eine Runde Sprache: ein lauter Frame, dann Stille bis zum hang-Deckel."""
    return [loud()] + [quiet()] * 10


def _sustained_followup():
    """Anhaltende Sprache im Nachfrage-Fenster (min_run=3)."""
    return [loud(), loud(), loud()]


def _sustained_turn():
    """Eine Runde Sprache OHNE Wake-Wort davor: braucht 3 laute Frames Anlauf,
    bevor die Aufnahme startet."""
    return [loud()] * 3 + [quiet()] * 10


def _stille(n):
    return [quiet()] * n


class FakeMic:
    """Frame-Strom mit Rückstau-Semantik: `flush()` verwirft, was noch im Puffer
    liegt — wie ein neu gestarteter Mikrofon-Stream."""
    def __init__(self, backlog, live):
        self.backlog, self.live = list(backlog), list(live)

    def flush(self):
        self.backlog = []

    def __iter__(self):
        while self.backlog:
            yield self.backlog.pop(0)
        while self.live:
            yield self.live.pop(0)


def test_single_turn_speaks_answer(monkeypatch):
    spoken = []
    monkeypatch.setattr(satellite.transcribe, "transcribe", lambda wav, model: "Wie spät ist es?")
    monkeypatch.setattr(satellite.jarvis_brain, "respond",
                        lambda text, tenant, token, model, history=None, source=None, voice_output=None, web_key=None, web_erlaubt=True: {"kind": "chat", "answer": "Kurz nach drei."})
    monkeypatch.setattr(satellite, "_speak", lambda text, deps: spoken.append(text))
    # 1 Runde Sprache, dann Nachfrage-Fenster leer -> Ende
    frames = iter([loud(), loud(), quiet(), quiet(), quiet(), quiet(), quiet(),
                   quiet(), quiet(), quiet(), quiet(), quiet(), quiet(), quiet()])
    hist = satellite.handle_interaction(frames, _deps())
    assert spoken == ["Kurz nach drei."]
    # Chat-Antwort landet in der History
    assert hist[-1] == {"role": "assistant", "content": "Kurz nach drei."}


def test_followup_window_triggers_second_turn(monkeypatch):
    answers = iter([{"kind": "chat", "answer": "A1"}, {"kind": "chat", "answer": "A2"}])
    calls = []
    monkeypatch.setattr(satellite.transcribe, "transcribe", lambda wav, model: "was ist mit dem Termin")
    monkeypatch.setattr(satellite.jarvis_brain, "respond",
                        lambda *a, **k: (calls.append(1) or next(answers)))
    spoken = []
    monkeypatch.setattr(satellite, "_speak", lambda text, deps: spoken.append(text))
    # Runde 1 Sprache -> hang; Nachfrage-Fenster: sofort laut -> Runde 2 Sprache -> hang;
    # Nachfrage-Fenster 2: nur Stille -> Ende.
    frames = iter(
        [loud(), quiet(), quiet(), quiet(), quiet(), quiet(), quiet(), quiet(), quiet(), quiet(), quiet()]  # Runde 1 (hang=10)
        + [loud(), loud(), loud()]                                                                          # Nachfrage 1: anhaltende Sprache (min_run=3)
        + [loud(), quiet(), quiet(), quiet(), quiet(), quiet(), quiet(), quiet(), quiet(), quiet(), quiet()]  # Runde 2
        + [quiet()] * sat_config.FOLLOWUP_START_FENSTER_FRAMES                                                      # Nachfrage 2: leer
    )
    satellite.handle_interaction(frames, _deps())
    assert spoken == ["A1", "A2"]
    assert len(calls) == 2


def test_followup_rounds_are_capped(monkeypatch):
    # Ein Dauergespräch im Raum darf die Nachfrage-Schleife nicht endlos am
    # Leben halten — sonst beantwortet Jarvis nach einem Wake-Wort alles.
    monkeypatch.setattr(satellite.transcribe, "transcribe", lambda wav, model: "was ist mit dem Termin")
    monkeypatch.setattr(satellite.jarvis_brain, "respond",
                        lambda *a, **k: {"kind": "chat", "answer": "A"})
    spoken = []
    monkeypatch.setattr(satellite, "_speak", lambda text, deps: spoken.append(text))
    frames = iter((_turn() + _sustained_followup()) * 10)
    satellite.handle_interaction(frames, _deps())
    assert len(spoken) == sat_config.MAX_TURNS_PER_WAKE


def test_own_playback_backlog_does_not_trigger_followup(monkeypatch):
    # Während der Wiedergabe läuft das Mikrofon weiter; der Rückstau enthält
    # Jarvis' eigene Stimme (HomePod, AirPlay-Latenz). Der darf keine
    # Folgerunde auslösen.
    calls = []
    monkeypatch.setattr(satellite.transcribe, "transcribe", lambda wav, model: "was ist mit dem Termin")
    monkeypatch.setattr(satellite.jarvis_brain, "respond",
                        lambda *a, **k: calls.append(1) or {"kind": "chat", "answer": "A"})
    monkeypatch.setattr(satellite, "_speak", lambda text, deps: None)
    mic = FakeMic(backlog=_turn() + [loud()] * 12,
                  live=[quiet()] * sat_config.FOLLOWUP_START_FENSTER_FRAMES)
    deps = _deps()
    deps["flush_mic"] = mic.flush
    satellite.handle_interaction(iter(mic), deps)
    assert len(calls) == 1


def test_empty_transcript_ends_without_speaking(monkeypatch):
    monkeypatch.setattr(satellite.transcribe, "transcribe", lambda wav, model: "")
    responded = []
    monkeypatch.setattr(satellite.jarvis_brain, "respond",
                        lambda *a, **k: responded.append(1) or {"kind": "empty", "answer": "Nichts erkannt, bitte erneut."})
    spoken = []
    monkeypatch.setattr(satellite, "_speak", lambda text, deps: spoken.append(text))
    frames = iter([quiet(), quiet(), quiet()])   # nie Sprache -> record leer
    satellite.handle_interaction(frames, _deps())
    assert spoken == []          # nichts aufgenommen -> nichts gesprochen
    assert responded == []       # respond gar nicht erst aufgerufen


def test_non_remembered_kind_not_added_to_history(monkeypatch):
    monkeypatch.setattr(satellite.transcribe, "transcribe", lambda wav, model: "mach mal bitte xyz")
    monkeypatch.setattr(satellite.jarvis_brain, "respond",
                        lambda *a, **k: {"kind": "unparsed_ok",
                                         "answer": "⚠️ …an den CEO weitergegeben: WHI-10"})
    spoken = []
    monkeypatch.setattr(satellite, "_speak", lambda text, deps: spoken.append(text))
    # Runde 1 Sprache (hang=10), dann Nachfrage-Fenster leer -> Ende
    frames = iter(
        [loud(), quiet(), quiet(), quiet(), quiet(), quiet(), quiet(), quiet(), quiet(), quiet(), quiet()]
        + [quiet()] * sat_config.FOLLOWUP_START_FENSTER_FRAMES
    )
    hist = satellite.handle_interaction(frames, _deps())
    assert hist == []
    assert spoken == ["⚠️ …an den CEO weitergegeben: WHI-10"]


def test_token_callable_is_resolved(monkeypatch):
    seen = {}
    monkeypatch.setattr(satellite.transcribe, "transcribe", lambda wav, model: "wie geht es dir")
    monkeypatch.setattr(satellite.jarvis_brain, "respond",
                        lambda text, tenant, token, model, history=None, source=None, voice_output=None, web_key=None, web_erlaubt=True: seen.update(token=token) or {"kind": "chat", "answer": "ok"})
    monkeypatch.setattr(satellite, "_speak", lambda text, deps: None)
    deps = _deps()
    deps["token"] = lambda: "AUFGELÖST"
    frames = iter([loud()] + [quiet()] * 12 + [quiet()] * sat_config.FOLLOWUP_START_FENSTER_FRAMES)
    satellite.handle_interaction(frames, deps)
    assert seen["token"] == "AUFGELÖST"


def test_web_answer_is_remembered(monkeypatch):
    # Suchantworten gehören ins Gedächtnis, sonst laufen Nachfragen ins Leere.
    monkeypatch.setattr(satellite.transcribe, "transcribe", lambda wav, model: "wie wird das Wetter")
    monkeypatch.setattr(satellite.jarvis_brain, "respond",
                        lambda *a, **k: {"kind": "web", "answer": "Morgen 24 Grad."})
    monkeypatch.setattr(satellite, "_speak", lambda text, deps: None)
    frames = iter(_turn() + [quiet()] * sat_config.FOLLOWUP_START_FENSTER_FRAMES)
    hist = satellite.handle_interaction(frames, _deps())
    assert hist[-1] == {"role": "assistant", "content": "Morgen 24 Grad."}


def test_web_key_is_passed_to_brain(monkeypatch):
    seen = {}
    monkeypatch.setattr(satellite.transcribe, "transcribe", lambda wav, model: "wie wird das Wetter")
    monkeypatch.setattr(satellite.jarvis_brain, "respond",
                        lambda *a, **k: seen.update(k) or {"kind": "chat", "answer": "ok"})
    monkeypatch.setattr(satellite, "_speak", lambda text, deps: None)
    deps = _deps()
    deps["web_key"] = "tvly-k"
    frames = iter(_turn() + [quiet()] * sat_config.FOLLOWUP_START_FENSTER_FRAMES)
    satellite.handle_interaction(frames, deps)
    assert seen["web_key"] == "tvly-k"


def test_web_is_locked_after_vault_lookup_for_rest_of_chain(monkeypatch):
    # Eine Vault-Antwort (kind == "lookup") landet in der Kette-History. Ab der
    # NÄCHSTEN Runde derselben Kette darf die Websuche die Adresse nicht mehr
    # nach draußen tragen — deshalb bekommt respond() ab dann
    # web_erlaubt=False.
    #
    # Gesperrt wird über das Flag, NICHT mehr über web_key=None: der lokale
    # Websuche-Dienst braucht gar keinen Schlüssel, ein entzogener Key würde
    # ihn also kein bisschen aufhalten.
    calls = []
    answers = iter([{"kind": "lookup", "answer": "Blumenweg 7"},
                     {"kind": "chat", "answer": "22 Grad."}])
    monkeypatch.setattr(satellite.transcribe, "transcribe", lambda wav, model: "was ist mit dem Termin")
    monkeypatch.setattr(satellite.jarvis_brain, "respond",
                        lambda *a, **k: calls.append(k) or next(answers))
    monkeypatch.setattr(satellite, "_speak", lambda text, deps: None)
    deps = _deps()
    deps["web_key"] = "tvly-k"
    frames = iter(_turn() + _sustained_followup() + _turn()
                  + [quiet()] * sat_config.FOLLOWUP_START_FENSTER_FRAMES)
    satellite.handle_interaction(frames, deps)
    assert len(calls) == 2
    assert calls[0]["web_erlaubt"] is True     # Runde 1: Lookup, noch frei
    assert calls[1]["web_erlaubt"] is False    # Runde 2: nach Lookup gesperrt


def test_web_stays_allowed_in_turns_without_vault_lookup(monkeypatch):
    # Gegenprobe zu obigem Test: ohne Vault-Zugriff in der Kette darf der
    # Merker nicht versehentlich immer sperren — Suche und Schlüssel bleiben
    # über mehrere Runden erhalten.
    calls = []
    monkeypatch.setattr(satellite.transcribe, "transcribe", lambda wav, model: "was ist mit dem Termin")
    monkeypatch.setattr(satellite.jarvis_brain, "respond",
                        lambda *a, **k: calls.append(k) or {"kind": "chat", "answer": "ok"})
    monkeypatch.setattr(satellite, "_speak", lambda text, deps: None)
    deps = _deps()
    deps["web_key"] = "tvly-k"
    frames = iter(_turn() + _sustained_followup() + _turn()
                  + [quiet()] * sat_config.FOLLOWUP_START_FENSTER_FRAMES)
    satellite.handle_interaction(frames, deps)
    assert len(calls) == 2
    assert calls[0]["web_key"] == "tvly-k"
    assert calls[1]["web_key"] == "tvly-k"
    assert calls[0]["web_erlaubt"] is True
    assert calls[1]["web_erlaubt"] is True


# --- Quittungs-Zweig: „Hey Jarvis" allein -> „Ja?" -> Frage ---------------

def _quittungs_umgebung(monkeypatch, texte, antwort=None):
    """Verdrahtet transcribe/respond/quittung/_speak und gibt die Mitschriften."""
    strom = iter(texte)
    m = {"gefragt": [], "quittiert": [], "gesprochen": []}
    monkeypatch.setattr(satellite.transcribe, "transcribe",
                        lambda wav, model: next(strom, ""))
    monkeypatch.setattr(satellite.jarvis_brain, "respond",
                        lambda text, *a, **k: m["gefragt"].append(text)
                        or (antwort or {"kind": "chat", "answer": "Kurz nach drei."}))
    monkeypatch.setattr(satellite.quittung, "spiele",
                        lambda key, path=None, device=None:
                        m["quittiert"].append(device) or "stimme")
    monkeypatch.setattr(satellite, "_speak", lambda text, deps: m["gesprochen"].append(text))
    return m


def test_bloße_anrede_fragt_nicht_das_sprachmodell(monkeypatch):
    # Der Kern der Änderung: „Hey Jarvis" allein ist eine Ankündigung, keine
    # Äußerung. Vorher ging sie ans Modell und kam als „Hallo Walter" zurück.
    m = _quittungs_umgebung(monkeypatch, ["Hey Jarvis.", "Wie spät ist es?"])
    frames = iter(_turn() + _sustained_turn()
                  + _stille(sat_config.FOLLOWUP_START_FENSTER_FRAMES))
    satellite.handle_interaction(frames, _deps())
    assert m["quittiert"] == [sat_config.HOMEPOD_DEVICE]
    assert m["gefragt"] == ["Wie spät ist es?"]      # NUR die echte Frage
    assert m["gesprochen"] == ["Kurz nach drei."]


def test_quittung_verbraucht_keine_der_drei_runden(monkeypatch):
    # Sonst kostet das Zögern eine Antwort-Runde.
    m = _quittungs_umgebung(monkeypatch, ["Hey Jarvis."] + ["frage"] * 10)
    frames = iter(_turn() + _sustained_turn() * 10)
    satellite.handle_interaction(frames, _deps())
    assert len(m["quittiert"]) == 1
    assert len(m["gesprochen"]) == sat_config.MAX_TURNS_PER_WAKE


def test_stille_nach_der_quittung_beendet_die_kette_stumm(monkeypatch):
    # Kommt nichts mehr, soll er schweigen — nicht „Nichts erkannt" rufen.
    m = _quittungs_umgebung(monkeypatch, ["Hey Jarvis."])
    frames = iter(_turn() + _stille(sat_config.ANREDE_START_FENSTER_FRAMES + 5))
    satellite.handle_interaction(frames, _deps())
    assert len(m["quittiert"]) == 1
    assert m["gefragt"] == []
    assert m["gesprochen"] == []


def test_zweite_bloße_anrede_geht_ans_sprachmodell(monkeypatch):
    # Die Quittung verbraucht keine Runde — ohne diese Sperre könnte ein
    # wiederholtes „Jarvis" die Kette endlos offen halten.
    m = _quittungs_umgebung(monkeypatch, ["Hey Jarvis.", "Jarvis"])
    frames = iter(_turn() + _sustained_turn()
                  + _stille(sat_config.FOLLOWUP_START_FENSTER_FRAMES))
    satellite.handle_interaction(frames, _deps())
    assert len(m["quittiert"]) == 1
    assert m["gefragt"] == ["Jarvis"]


def test_leeres_transkript_quittiert_statt_zu_antworten(monkeypatch):
    # Aufgenommen, aber nichts verstanden: quittieren und weiter zuhören ist
    # nützlicher als das gesprochene „Nichts erkannt, bitte erneut".
    m = _quittungs_umgebung(monkeypatch, [""])
    frames = iter(_turn() + _stille(sat_config.ANREDE_START_FENSTER_FRAMES + 5))
    satellite.handle_interaction(frames, _deps())
    assert len(m["quittiert"]) == 1
    assert m["gefragt"] == []
    assert m["gesprochen"] == []


def test_frage_in_einem_zug_wird_nicht_quittiert(monkeypatch):
    # Gegenprobe: der eingespielte Weg („Hey Jarvis, wie spät ist es?") darf
    # keine Quittung einschieben — das wäre eine zusätzliche Wartezeit.
    m = _quittungs_umgebung(monkeypatch, ["Hey Jarvis, wie spät ist es?"])
    frames = iter(_turn() + _stille(sat_config.FOLLOWUP_START_FENSTER_FRAMES))
    satellite.handle_interaction(frames, _deps())
    assert m["quittiert"] == []
    assert m["gefragt"] == ["Hey Jarvis, wie spät ist es?"]


def test_kurze_nachfrage_wird_nicht_als_anrede_missverstanden(monkeypatch):
    # Die Kürze-Regel gilt NUR für Runde 1, wo das Wake-Wort beweisbar im Audio
    # steckt. In einer Nachfrage-Runde ist „Termine heute" eine vollständige
    # Frage — würde sie quittiert, käme Walter nie zu einer Antwort.
    m = _quittungs_umgebung(monkeypatch,
                            ["Wie wird das Wetter morgen?", "Termine heute"])
    frames = iter(_turn() + _sustained_turn()
                  + _stille(sat_config.FOLLOWUP_START_FENSTER_FRAMES))
    satellite.handle_interaction(frames, _deps())
    assert m["quittiert"] == []
    assert m["gefragt"] == ["Wie wird das Wetter morgen?", "Termine heute"]


def test_verunstaltetes_wakeword_wird_quittiert(monkeypatch):
    # Live-Befund 17.08.: Whisper machte aus „Hey Jarvis" ein „Chavez." — das
    # ging als echte Frage ans Modell, das daraufhin im Vault nach einem
    # Kontakt „Chavez" suchte (12 s Wartezeit, Fehlantwort).
    m = _quittungs_umgebung(monkeypatch, ["Chavez.", "Wie spät ist es?"])
    frames = iter(_turn() + _sustained_turn()
                  + _stille(sat_config.FOLLOWUP_START_FENSTER_FRAMES))
    satellite.handle_interaction(frames, _deps())
    assert len(m["quittiert"]) == 1
    assert m["gefragt"] == ["Wie spät ist es?"]
