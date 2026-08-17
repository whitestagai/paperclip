# Deploy: Voice-Echo Jarvis-Bot

Telegram-Bot `@whitestag_jarvis_bot`: Sprachnachricht → lokales Whisper → Bestätigung → Issue an den WHITESTAG-CEO. Läuft als launchd-Dienst aus `~/.paperclip/scripts/` (launchd kann SynologyDrive nicht lesen).

## Voraussetzungen
- `~/.paperclip/voice-echo-bot.env` — `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USER_ID`, `WHITESTAG_COMPANY_ID`, `CEO_AGENT_ID`, `WHISPER_MODEL` (Rechte 600)
- `~/.paperclip/models/whisper/ggml-large-v3-turbo.bin`
- `~/.paperclip/auth.json` (Paperclip-Board-Token, auto-renewt)
- Homebrew: `whisper-cli`, `ffmpeg`

## Repo und Live sind zusammengeführt (2026-08-17)

Bis dahin waren `tools/voice-echo-bot/` und `~/.paperclip/scripts/voice-echo-bot/`
**zwei verschiedene Programme** mit einer Zwei-Wege-Divergenz: der Live-`bot.py`
(504 Zeilen) trug `academy_bridge` + `seo_gate` und die Werkzeuge inline, der
Repo-`bot.py` (272 Zeilen) dafür `jarvis_brain`. Das `rsync` unten hätte in
dieser Lage academy-auto und die seo-geo-Freigabe **still** abgeschaltet — keine
Fehlermeldung, die Module wären als verwaiste Dateien liegengeblieben.

Das ist behoben: das Repo trägt jetzt beides. Der Bot denkt über `jarvis_brain`
(damit hat er auch die **Websuche**, die er vorher gar nicht kannte) und
bedient weiterhin beide Freigabe-Rückkanäle. **Das `rsync` unten ist damit
wieder der richtige Weg** — Repo ist die Quelle, live ist die Kopie.

Trotzdem vor jedem Deploy prüfen, ob live unbemerkt wieder vorausgelaufen ist:

```bash
diff -rq tools/voice-echo-bot ~/.paperclip/scripts/voice-echo-bot \
  --exclude=venv --exclude=__pycache__ --exclude=.pytest_cache
```

Erscheinen Unterschiede, die nicht von der eigenen aktuellen Änderung stammen:
**stoppen** und erst zusammenführen — nicht drüberkopieren. Die Tests werden
bewusst **mit** deployed (siehe unten), damit dieser `diff` vollständig ist und
sich der Live-Stand jederzeit selbst nachprüfen lässt.

## Deploy / Update
```bash
mkdir -p ~/.paperclip/scripts/voice-echo-bot ~/.paperclip/logs
# Alle Module INKLUSIVE Tests. Die Tests kosten im Betrieb nichts, machen den
# diff oben aber vollstaendig und erlauben den Rauchtest nach dem Deploy —
# genau ihr Fehlen hat 2026-07 den Fork entstehen lassen (die Live-Tests
# test_academy_bridge.py/test_seo_gate.py kannte das Repo nie).
rsync -a --exclude '__pycache__' --exclude '.pytest_cache' \
   tools/voice-echo-bot/*.py ~/.paperclip/scripts/voice-echo-bot/
# Rauchtest im Live-Verzeichnis, VOR dem Neustart:
( cd ~/.paperclip/scripts/voice-echo-bot && python3 -m pytest -q )
sed "s|__HOME__|$HOME|g" tools/voice-echo-bot/de.whitestag.voice-echo-bot.plist \
   > ~/Library/LaunchAgents/de.whitestag.voice-echo-bot.plist
launchctl bootout gui/$(id -u)/de.whitestag.voice-echo-bot 2>/dev/null || true
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/de.whitestag.voice-echo-bot.plist
launchctl kickstart -k gui/$(id -u)/de.whitestag.voice-echo-bot
```

## Status / Logs
```bash
launchctl print gui/$(id -u)/de.whitestag.voice-echo-bot | grep -E "state =|pid ="
tail -f ~/.paperclip/logs/voice-echo-bot.log
```

## Bedienung
In Telegram an `@whitestag_jarvis_bot` eine Sprach- oder Textnachricht senden — das ist ein normaler Chat. Das Denken steckt in `jarvis_brain` (geteilt mit dem Wake-Satelliten): Jarvis antwortet direkt, schlägt bei Bedarf im **Vault** nach, **sucht im Netz** (lokaler Websuche-Dienst `:7789`, Tavily nur als Fallback) und legt auf ausdrückliche Bitte eine **Aufgabe beim CEO** an. Keine Bestätigungs-Buttons mehr — der frühere `[✅ An CEO senden]`-Ablauf ist seit dem Chat-Umbau weg. `/voice` und `/text` schalten den Antwortkanal um. Bedient werden nur die in `voice-echo-tenants.json` hinterlegten Personen; alle anderen werden ignoriert.

**PII-Notaus:** Nach einer Vault-Abfrage ist die Websuche für diesen Chat gesperrt, solange der Treffer im behaltenen History-Fenster (8 Turns) steht — sonst könnten private Daten als Suchbegriff nach draußen wandern. Danach löst sich die Sperre von selbst. Sie hängt am Flag `web_erlaubt`, **nicht** am `TAVILY_API_KEY`: der lokale Dienst braucht keinen Schlüssel, ein entzogener Key würde die Suche also nicht mehr aufhalten.

## Hinweise
- **Nur EIN Long-Poll-Consumer je Bot-Token.** Nicht parallel woanders `getUpdates`/Webhook auf denselben Token laufen lassen (Luna ist ein anderer Bot/Token — kein Konflikt).
- Whisper läuft on-demand (Modell wird pro Aufnahme geladen, RAM danach frei) — bewusst kein Dauer-Server wegen RAM-Contention mit LM Studio.
- **Chat-Modell:** `google/gemma-4-12b` (klein, lokal auf der Studio resident), Fallback `gemma-4-31b-it-mlx`. Bewusst NICHT das grosse 31b als Primärmodell: es lag per LM Link auf dem MacBook und riss beim JIT-Kaltstart (33,8 GB) regelmässig den Timeout → HTTP 400 am RAM-Guardrail. Überschreibbar per `CHAT_MODEL` in der env.
- **Kein Auftragsverlust:** Scheitert das LLM endgültig (2 Versuche Primärmodell + 1 Fallback), legt der Bot den Wortlaut trotzdem als Issue beim CEO an und nennt dir die Nummer. Nur wenn auch die Issue-Anlage scheitert, meldet er „NICHT angekommen". Liegt seit der Zusammenführung in `jarvis_brain._unparsed` (vorher `bot._file_unparsed`), Rückgabe-`kind` = `unparsed_ok` bzw. `unparsed_fail`.
- **Freigabe-Rückkanäle:** `academy:approve|reject:<ts>` (academy-auto) und `seo:ok/no:<token>` (SEO/GEO) laufen über `handle_update` → Präfix-Dispatcher. Kein Unit-Test deckt den echten Knopfdruck ab, deshalb prüft `test_freigabe_pfade_e2e.py` beide Ketten gegen die *echten* Brücken bis auf die Platte. Diese Datei vor jedem Deploy grün sehen — ein Ausfall hier wäre still.

## Rückkanal + Mehrmandanten (Feature 2)

**Mandanten-Tabelle:** `~/.paperclip/voice-echo-tenants.json` (600) — Telegram-ID → {company_id, ceo_agent_id}. Aktuell: Walter `8311805232` → WHITESTAG/CEO, Clara `1220010628` → Clara Sound/Büroleitung. Neue Person: Zeile ergänzen, sie drückt `/start` beim Bot.

**Dedup-State:** `~/.paperclip/voice-echo-state.json` — verhindert Doppel-Pushes; Erststart markiert Bestand still als „seen".

**Decision-Label `entscheidung-noetig`:**
- WHITESTAG: `77196d1b-6d7c-45ac-a89f-08424b48ac72`
- Clara Sound: `4441d371-3ec6-4437-ad03-2e3bc139ae11`
- Bot löst die ID zur Laufzeit per Name auf (`resolve_label_id`), IDs hier nur zur Referenz.

**CEO-Instruktion (setzt das Label bei Entscheidungsbedarf):**
- WHITESTAG-CEO: durable in `~/.paperclip/scripts/agents-instructions/roles/ceo.role.md` (Abschnitt „Entscheidungen an Walter"); via Generator übernommen:
  ```bash
  cd ~/.paperclip/scripts/agents-instructions
  export PCP_API=http://localhost:3100 PCP_CID=9cebf3cf-efe8-4597-a400-f06488900a87
  export PCP_TOKEN=$(python3 -c "import json,os;print(json.load(open(os.path.expanduser('~/.paperclip/auth.json')))['credentials']['http://localhost:3100']['token'])")
  python3 build-agents-md.py --dry-run   # Umfang prüfen (nur CEO ändert sich)
  python3 build-agents-md.py --backup --apply   # ggf. 2× (eventual consistency)
  ```
- Clara-Büroleitung: NICHT im WHITESTAG-Generator → direkt via API-Bundle geschrieben
  (`PUT /api/agents/64ad7d03-…/instructions-bundle/file` mit `{"path":"AGENTS.md","content":…}`),
  Abschnitt „Entscheidungen an Clara".

**Rückkanal-Verhalten:** Bot pollt je Mandant alle ~60 s: Top-Level-Issue neu `done` → „✅ Erledigt"-Push; Issue trägt `entscheidung-noetig` → „🟠 Entscheidung benötigt"-Push. Nutzer antwortet per Telegram-**Reply** (Sprache/Text) → Kommentar ans Issue (`resume:true`).
