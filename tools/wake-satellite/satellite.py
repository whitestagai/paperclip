# tools/wake-satellite/satellite.py
"""Wake-Word-Satellit „Hey Jarvis": Schleife + Interaktion.

`main` verdrahtet Mikrofon + Wake-Word (Hardware). `handle_interaction` ist die
testbare Interaktion nach einem Wake-Treffer: aufnehmen -> transkribieren ->
Jarvis-Gehirn -> sprechen -> 6-s-Nachfrage-Fenster. Ein Gehirn (jarvis_brain),
geteilt mit dem Telegram-Bot."""
import os
import re
import shutil
import tempfile
import time
import traceback

import config as vco_config          # voice-echo-bot: load_env, ENV_PATH, load_paperclip_token
import jarvis_brain
import transcribe
import tts

import sat_config
import anrede
import capture
import earcon
import lokal_tts
import playback
import quittung
import wake


def _resolve_token(deps):
    tok = deps["token"]
    return tok() if callable(tok) else tok


def _remember(history, user_text, assistant_text):
    hist = list(history)
    hist.append({"role": "user", "content": user_text})
    hist.append({"role": "assistant", "content": assistant_text})
    if len(hist) > sat_config.MAX_HISTORY_MESSAGES:
        del hist[:len(hist) - sat_config.MAX_HISTORY_MESSAGES]
    return hist


def _transcribe(recorded, deps):
    workdir = tempfile.mkdtemp()
    wav = capture.frames_to_wav(recorded, os.path.join(workdir, "utt.wav"))
    try:
        return transcribe.transcribe(wav, deps["whisper_model"])
    except transcribe.TranscriptionError:
        traceback.print_exc()
        return ""
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _synthesize(text, deps, workdir):
    """Phonon lokal, bei Ausfall ElevenLabs. Pfad zur Audiodatei oder None."""
    try:
        return lokal_tts.synthesize(text, os.path.join(workdir, "reply.wav"))
    except tts.TtsError:
        traceback.print_exc()
    try:
        return tts.synthesize(text, deps["eleven_key"], os.path.join(workdir, "reply.mp3"),
                              output_format=sat_config.TTS_FORMAT)
    except tts.TtsError:
        traceback.print_exc()
        return None


# Whisper schreibt Gesungenes als „# … #" oder „♪", reine Musik als „Musik",
# „[Musik]" o. ä. Nur das GANZE Transkript zählt — „spiel Musik von Bach" ist
# eine Frage.
_MUSIKZEICHEN = re.compile(r"[#♪♫]")
_NUR_MUSIK = re.compile(r"\W*(musik|music)\W*", re.IGNORECASE)


def _ist_musik(text):
    text = (text or "").strip()
    return bool(text) and bool(_MUSIKZEICHEN.search(text) or _NUR_MUSIK.fullmatch(text))


def _speak(text, deps):
    """Spricht `text`. Gibt die Synthesezeit in Sekunden zurück (fürs Log)."""
    if not (text or "").strip():
        return 0.0
    workdir = tempfile.mkdtemp()
    try:
        t0 = time.monotonic()
        dest = _synthesize(text, deps, workdir)
        synth = time.monotonic() - t0
        if dest:
            playback.play(dest, device=sat_config.HOMEPOD_DEVICE)
        return synth
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _quittiere(deps):
    """Kurzes „Ja?" — das Signal, dass jetzt zugehört wird."""
    quittung.spiele(deps.get("eleven_key"), device=sat_config.HOMEPOD_DEVICE)


def _mitschneiden(frames, ablage):
    """Reicht die Frames durch und legt jeden zusätzlich in `ablage` ab."""
    for frame in frames:
        ablage.append(frame)
        yield frame


def _melde_stille(gehoert):
    """Protokolliert ein leer gebliebenes Fenster nach der Quittung: höchster
    Pegel und längster lauter Lauf gegen die Startbedingung — zeigt, ob die
    Frage zu leise war, zu kurz oder gar nicht ankam."""
    pegel = [capture._rms(f) for f in gehoert]
    lauf = laengster = 0
    for p in pegel:
        lauf = lauf + 1 if p >= capture.SILENCE_RMS else 0
        laengster = max(laengster, lauf)
    datei = ""
    if sat_config.DIAG_DIR and gehoert:
        os.makedirs(sat_config.DIAG_DIR, exist_ok=True)
        datei = capture.frames_to_wav(gehoert, os.path.join(
            sat_config.DIAG_DIR, time.strftime("stille-%Y%m%d-%H%M%S.wav")))
    print("[stille] nach Quittung: {} Frames, max_rms={:.0f} laengster_lauf={} "
          "(Start braucht {} Frames >= {}) {}".format(
              len(gehoert), max(pegel, default=0), laengster,
              sat_config.MIN_START_RUN_FRAMES, capture.SILENCE_RMS, datei),
          flush=True)




def handle_interaction(frames, deps, tenant=None, history=None):
    tenant = tenant or sat_config.TENANT
    history = list(history or [])
    flush_mic = deps.get("flush_mic")
    # Sobald eine Runde dieser Kette eine Vault-Antwort geliefert hat, landet
    # der Fund im Gesprächsverlauf (`history`) — die Websuche wird für den
    # Rest der Kette gesperrt (`web_erlaubt=False`), damit private Daten nicht
    # per WEB: nach draußen wandern. Rein lokaler Merker: `main()` startet jede
    # Kette ohne History, die Sperre wirkt also nie über ein erneutes
    # "Hey Jarvis" hinaus.
    web_locked_after_lookup = False
    # Runde 1 folgt direkt auf das Wake-Wort: kurzes Startfenster, und kein
    # Anlauf nötig — das Wake-Wort hat die Aufnahme bereits gerechtfertigt.
    # Für alle späteren Runden gilt beides anders (siehe unten).
    start_fenster = capture.MAX_START_FRAMES
    anlauf = 1
    quittiert = False
    runden = 0
    while runden < sat_config.MAX_TURNS_PER_WAKE:
        gehoert = []
        quelle = _mitschneiden(frames, gehoert) if quittiert and runden == 0 else frames
        recorded = capture.record_until_silence(quelle, max_start_frames=start_fenster,
                                                min_start_run=anlauf)
        if not recorded:
            if quittiert and runden == 0:
                _melde_stille(gehoert)
            break
        # Bis zum Deckel ohne eine einzige Pause: das ist Musik oder Radio,
        # keine Frage (Live-Befund 26.10.: alle sieben solchen Aufnahmen waren
        # Liedtexte, Walters Fragen dauerten 0,9-5 s). Kette still beenden.
        if len(recorded) >= capture.MAX_RECORD_FRAMES:
            print("[dauerton] Aufnahme bis zum Deckel -> keine Frage, Kette endet",
                  flush=True)
            break
        t0 = time.monotonic()
        text = _transcribe(recorded, deps)
        t1 = time.monotonic()
        if _ist_musik(text):
            print("[dauerton] Musik im Transkript ('{}') -> Kette endet".format(
                text.strip()[:40]), flush=True)
            break
        if runden == 0 and not quittiert and anrede.ist_nur_wakeword(text):
            # „Hey Jarvis", absetzen, dann erst die Frage: die Aufnahme endet in
            # der Pause, beim Modell kommt nur die Anrede an und es antwortet
            # „Hallo Walter". Statt dessen kurz quittieren und länger zuhören.
            # Kostet KEINE der Runden — Zögern soll nicht bestraft werden.
            # Nur EINMAL je Kette: sonst hielte ein wiederholtes „Jarvis" die
            # Kette endlos offen, weil die Quittung nicht mitzählt.
            # Und nur in Runde 1: nur dort steckt das Wake-Wort beweisbar mit
            # im Audio, worauf die Kürze-Regel in anrede.py beruht. In einer
            # Nachfrage-Runde ist „Termine heute" eine vollständige Frage.
            quittiert = True
            _quittiere(deps)
            if flush_mic:
                flush_mic()      # eigene Quittung nicht als Frage hören
            start_fenster = sat_config.ANREDE_START_FENSTER_FRAMES
            anlauf = sat_config.MIN_START_RUN_FRAMES
            print("[quittung] nur Anrede ('{}') -> hoere {:.0f}s zu".format(
                (text or "").strip()[:40], sat_config.ANREDE_START_FENSTER_SEC),
                flush=True)
            continue
        # Gesperrt wird über das Flag, nicht über einen entzogenen Schlüssel:
        # der lokale Websuche-Dienst braucht gar keinen, ein web_key=None
        # würde die Suche also nicht mehr aufhalten.
        result = jarvis_brain.respond(text, tenant, _resolve_token(deps),
                                      deps["chat_model"], history=history,
                                      source="per Sprache", voice_output=True,
                                      web_key=deps.get("web_key"),
                                      web_erlaubt=not web_locked_after_lookup,
                                      reasoning_effort=sat_config.CHAT_REASONING_EFFORT,
                                      fallback_model=sat_config.CHAT_FALLBACK_MODEL,
                                      claude_aktiv=sat_config.CLAUDE_AKTIV,
                                      waehrenddessen=lambda: _speak(sat_config.CLAUDE_ANSAGE, deps),
                                      aufgaben_aktiv=sat_config.AUFGABEN_AKTIV)
        t2 = time.monotonic()
        # Paperclip-Daten sind so intern wie Vault-Daten: danach nichts mehr
        # nach draußen (Websuche, Claude).
        if result["kind"] in ("lookup", "aufgaben"):
            web_locked_after_lookup = True
        answer = result["answer"]
        if result["kind"] in ("chat", "lookup", "issue", "web", "claude", "aufgaben"):
            history = _remember(history, text, answer)
        synth = _speak(answer, deps) or 0.0
        if flush_mic:
            flush_mic()      # eigene Wiedergabe nicht als Nachfrage hören
        t3 = time.monotonic()
        runden += 1
        # erster_ton: vom Ende der Aufnahme bis zum Start der Wiedergabe — die
        # Wartezeit, die Walter spürt (ohne die AirPlay-Pufferung des HomePods).
        print("[timing] runde={}/{} aufnahme={:.1f}s stt={:.1f}s llm({})={:.1f}s "
              "tts={:.1f}s play={:.1f}s erster_ton={:.1f}s | text='{}'".format(
                  runden, sat_config.MAX_TURNS_PER_WAKE,
                  len(recorded) * sat_config.FRAME_SAMPLES / sat_config.SAMPLE_RATE,
                  t1 - t0, result["kind"], t2 - t1, synth, t3 - t2 - synth,
                  t2 - t0 + synth, (text or "")[:50]),
              flush=True)
        # Die Nachfrage wird direkt aufgenommen, statt sie erst zu „erkennen"
        # und dann aufzunehmen: das getrennte Horchen verbrauchte genau die
        # Frames, an denen es die Sprache erkannte — im Transkript fehlten
        # dadurch die ersten Wörter der Nachfrage.
        start_fenster = sat_config.FOLLOWUP_START_FENSTER_FRAMES
        anlauf = sat_config.MIN_START_RUN_FRAMES
    return history


def build_deps():
    env = vco_config.load_env(vco_config.ENV_PATH)
    detector = wake.WakeDetector(sat_config.WAKE_MODELS, threshold=sat_config.WAKE_THRESHOLD,
                                 inference_framework=sat_config.INFERENCE_FRAMEWORK,
                                 required_hits=sat_config.WAKE_REQUIRED_HITS)
    return {
        "detector": detector,
        "whisper_model": os.path.expanduser(env["WHISPER_MODEL"]),
        "eleven_key": env.get("ELEVENLABS_API_KEY"),
        "chat_model": sat_config.CHAT_MODEL or env.get("CHAT_MODEL") or jarvis_brain.llm.DEFAULT_MODEL,
        "token": vco_config.load_paperclip_token,
        "web_key": env.get("TAVILY_API_KEY"),
    }


def main():  # pragma: no cover — Hardware
    import sys
    import itertools
    from collections import deque
    print("wake-satellit „Hey Jarvis“ startet…", file=sys.stderr)
    deps = build_deps()
    detector = deps["detector"]
    mic = capture.MicStream()
    deps["flush_mic"] = mic.flush
    frames = iter(mic)
    preroll = deque(maxlen=sat_config.PREROLL_FRAMES)
    while True:
        try:
            frame = next(frames)
            preroll.append(frame)
            hit = detector.process(frame)
            if hit is None:
                continue
            print("[wake] {} score={:.2f}".format(*hit), flush=True)
            earcon.beep_async()                # blockiert nicht -> kein Clipping
            pre = list(preroll)                # ~1,2 s vor dem Treffer voranstellen
            preroll.clear()
            handle_interaction(itertools.chain(pre, frames), deps)
            detector.reset()
            time.sleep(sat_config.PLAYBACK_COOLDOWN_SEC)
            mic.flush()          # Rückstau nicht in den Wake-Detektor spülen
            preroll.clear()
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            time.sleep(1)


if __name__ == "__main__":
    main()
