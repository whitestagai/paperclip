# Wake-Word-Satellit „Hey Jarvis" — Deploy (Mac Studio)

Freihändiger Sprachzugang zu Jarvis: „Hey Jarvis, …" -> Antwort laut über den
HomePod „Homepod Studio". Läuft als **LaunchAgent** (nicht Daemon) in Walters
GUI-Session — nur so bekommt der Prozess Mikrofon-Zugriff.

## Voraussetzungen (einmalig)

- Homebrew-Tools: `brew install switchaudio-osx ffmpeg whisper-cpp`
  (`SwitchAudioSource`, `ffmpeg`, `whisper-cli`).
- Der HomePod muss in **Systemeinstellungen -> Ton -> Ausgabe** als
  `Homepod Studio` erscheinen (AirPlay). Heißt er anders, `HOMEPOD_DEVICE`
  in `sat_config.py` anpassen und neu deployen.
- `~/.paperclip/voice-echo-bot.env` existiert bereits (vom Telegram-Jarvis) mit
  `WHISPER_MODEL`, `ELEVENLABS_API_KEY`, `CHAT_MODEL`. Der Satellit nutzt sie.
- Stimme: Ollama läuft auf dem Studio (`:11434`) mit `ollama pull phonon:40m-de`.
  Modell und Stimme (`LOKAL_TTS_*`) stehen in `sat_config.py`. Fehlt Ollama oder
  das Modell, spricht der Satellit mit ElevenLabs weiter — im Log steht dann ein
  Traceback mit `Phonon request failed` bzw. `Phonon HTTP …`.

## Deploy

```bash
cd "…/Paperclip/tools/wake-satellite"
./deploy.sh
```

Das Skript kopiert Satellit + geteilte Module nach
`~/.paperclip/scripts/wake-satellite/`, baut das venv, lädt via
`openwakeword.download_models` die ONNX-Modelle, prüft die Modell-Ladbarkeit
und installiert den LaunchAgent.

### Hinweis zum ONNX-Backend

`openwakeword` lädt `.tflite`-Modelle ausschließlich über das eigenständige
Paket `tflite_runtime` — auf macOS arm64 gibt es dafür kein pip-Wheel
(`tensorflow` liefert dieses `tflite_runtime` NICHT mit). Der Satellit nutzt
deshalb das **ONNX-Backend** (`onnxruntime`, kommt als openwakeword-
Abhängigkeit automatisch mit). `hey_jarvis` ist ein offizielles openwakeword-
Modell; `deploy.sh` lädt per `download_models(['hey_jarvis'])` die passenden
`.onnx` (Wakeword + `melspectrogram`/`embedding`-Feature-Modelle) in den
openwakeword-Ressourcenordner, von wo `sat_config.WAKE_MODELS = ["hey_jarvis"]`
aufgelöst wird. Kein `tensorflow`, kein `tflite_runtime` nötig.

## Mikrofon-Freigabe (Pflicht, manuell)

Ein launchd-Prozess kann den Berechtigungsdialog nicht auslösen. Einmalig:

1. `~/.paperclip/scripts/wake-satellite/venv/bin/python3` in
   **Systemeinstellungen -> Datenschutz & Sicherheit -> Mikrofon** hinzufügen
   und aktivieren. (Ggf. den Ordner via Finder „Gehe zu" öffnen und die Binärdatei
   dorthin ziehen.)
2. Ohne Freigabe protokolliert der Satellit einen klaren Fehler statt still zu
   crashen — im Log sichtbar.

## Start / Stop / Logs

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/de.whitestag.wake-satellite.plist
launchctl kickstart -k gui/$(id -u)/de.whitestag.wake-satellite     # Neustart
launchctl bootout   gui/$(id -u)/de.whitestag.wake-satellite        # Stop
tail -f ~/.paperclip/logs/wake-satellite.log
```

## Bekannte Grenzen (Phase 1)

- Nur Jarvis. Luna folgt in Phase 2 (eigener Zugang zu ihrem n8n-Gehirn).
- Während der HomePod spricht, ist die Wake-Erkennung aus; das Nachfrage-Fenster
  (`FOLLOWUP_START_FENSTER_SEC`, 5 s) startet erst nach der Wiedergabe.
  Restliches Echo dämpft der Cooldown.
- Kam nach dem Wake-Wort nur die Anrede („Hey Jarvis" und dann eine Pause),
  quittiert der Satellit mit „Ja?" und hört `ANREDE_START_FENSTER_SEC` (8 s)
  weiter zu, ohne das Sprachmodell zu fragen. Die Quittung wird beim ersten Mal
  mit Phonon gerendert und liegt danach als
  `~/.paperclip/wake-satellite/quittung-phonon-<stimme>.wav` (ein Stimmwechsel
  rendert also von selbst neu); zum Neu-Rendern bei anderem Text die Datei
  löschen. Ist Phonon nicht zu haben, kommt die ElevenLabs-Fassung
  `quittung.mp3`, ohne beides ein 520-Hz-Ton — hörbar anders als der
  880-Hz-Wake-Ton.
- Dazwischenreden (Barge-in) geht nicht: was während der Wiedergabe gesagt wird,
  verwirft `flush_mic()` bewusst, sonst hörte sich Jarvis selbst zu.
- Deploy-Lücke Repo <-> Live ist ansage-pflichtig: nach Code-Änderung erneut
  `./deploy.sh` + `kickstart -k`.
