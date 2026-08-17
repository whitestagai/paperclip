# Handoff: Jarvis Telegram-Bot (2026-07-21)

Kontext-Übergabe für einen anderen Chat. Was in dieser Session gebaut wurde, mit allen konkreten IDs, Pfaden und Entscheidungen.

## Ausgangsidee → finaler Scope

Ursprünglich: eine URL (lokal/Cloudflare), auf der man per Sprache eine Aufgabe einspricht, Button drückt → geht als „Echo" an den CEO in Paperclip.

Über zwei Brainstorm-Runden gepivotet zu: **ein dedizierter Telegram-Bot** (ersetzt Web-Seite + Cloudflare komplett — Long-Polling, nichts nach außen exponiert). Dann in zwei Ausbaustufen umgesetzt:
- **Feature 1 (Einbahn):** Sprache/Text → lokales Whisper → Bestätigung → Issue beim CEO.
- **Feature 2 (Rückkanal + Mehrmandanten):** ID-Routing an die richtige Company/CEO; CEO meldet „Fertig"/„Entscheidung benötigt" zurück nach Telegram; Antwort per Reply → Kommentar ans Issue.

## Der Bot

- **`@whitestag_jarvis_bot`** (Anzeigename „J.A.R.V.I.S."), Bot-ID `8757029765`. War bereits per BotFather angelegt, ungenutzt — Token lag nirgends auf dem Mac, nur in BotFather. (Nicht zu verwechseln mit Luna `@whitestag_luna_bot` = n8n, und `@ClaraAiBot`.)
- Token + Secrets liegen in `~/.paperclip/voice-echo-bot.env` (chmod 600, NICHT im Git).

## Mandanten-Tabelle
`~/.paperclip/voice-echo-tenants.json` (600), Telegram-User-ID → {company, CEO}:

| Person | Telegram-ID | Company | Company-ID | CEO-Agent | CEO-ID |
|---|---|---|---|---|---|
| Walter | `8311805232` | WHITESTAG | `9cebf3cf-efe8-4597-a400-f06488900a87` | CEO | `506c873e-3a40-4483-9a45-0eb0fa1554bb` |
| Clara | `1220010628` | Clara Sound | `0e426844-309c-4528-9aa5-90ff76790a51` | Büroleitung | `64ad7d03-ce64-46aa-ae79-d17ff26f5d4f` |

Fremde ID → still ignoriert (Isolation = die Tabelle). Clara muss noch einmal `/start` beim Bot drücken, damit der Bot ihr schreiben darf (sonst 403).

## Architektur (ein Prozess, stdlib-only Python)

Code im Repo: `tools/voice-echo-bot/` (Muster wie `tools/n8n-workflow-watcher/`). Deployt nach `~/.paperclip/scripts/voice-echo-bot/`, läuft als launchd-Dienst `de.whitestag.voice-echo-bot` (KeepAlive, Log `~/.paperclip/logs/voice-echo-bot.log`).

Module:
- `config.py` — Env + Paperclip-Token aus `~/.paperclip/auth.json` (auto-renewt), Pfade/Konstanten
- `telegram_api.py` — Bot-API-Client (getUpdates Long-Poll, sendMessage, answerCallbackQuery, getFile, download)
- `transcribe.py` — ffmpeg → 16 kHz WAV → `whisper-cli` (Modell `~/.paperclip/models/whisper/ggml-large-v3-turbo.bin`), **on-demand** (kein Dauer-Server, wegen RAM-Contention mit LM Studio). Binaries werden absolut aufgelöst (launchd-PATH kennt `/opt/homebrew/bin` nicht).
- `paperclip_client.py` — create_issue, derive_title, add_comment, list_issues, resolve_label_id, find_issue_by_identifier
- `tenants.py`, `state.py`, `notifier.py` — Mandanten, Dedup-State, Event-Sammlung
- `bot.py` — Long-Poll (25 s) + periodischer CEO-Event-Poll (60 s) + Reply-Handling

Ablauf:
- **Eingang:** Nachricht → Absender-ID in Tabelle → Voice→Whisper/Text → Bestätigung [✅ An CEO senden]/[❌ Verwerfen] → `POST /companies/{id}/issues` (assignee = CEO, priority medium, kein status).
- **Rückkanal-Poll je Mandant:** Top-Level-Issue neu `done` → „✅ Erledigt"-Push; Issue trägt Label `entscheidung-noetig` → „🟠 Entscheidung benötigt"-Push. Dedup über `~/.paperclip/voice-echo-state.json`; Erststart markiert Bestand still (kein Push-Sturm).
- **Reply→Kommentar:** Nutzer antwortet per Telegram-Reply auf eine CEO-Meldung → Bot liest die Issue-Referenz (`identifier`, z. B. „WHI-2857") aus dem zitierten Text → `POST /issues/{id}/comments {body, resume:true}` (weckt den CEO). Zustandslos (überlebt Neustarts).

Paperclip-API: `http://127.0.0.1:3100/api`, Auth `Authorization: Bearer <token>` aus `auth.json`.

## „Entscheidung benötigt"-Signal (wichtige Design-Entscheidung)

Es gibt **kein** maschinelles Status-Flag dafür (`blockerAttention: needs_attention` haben ALLE blocked-Issues; `assigneeUserId` immer null; die „Entscheidung benötigt"-Mails schreibt der CEO selbst). → Gewählt: **CEO markiert strukturiert** per Label `entscheidung-noetig`, Bot pollt das Label (`?labelId=`).
- Label angelegt: WHITESTAG `77196d1b-6d7c-45ac-a89f-08424b48ac72`, Clara `4441d371-3ec6-4437-ad03-2e3bc139ae11`.
- CEO-Instruktion ergänzt: WHITESTAG durable in `~/.paperclip/scripts/agents-instructions/roles/ceo.role.md` + Generator (`build-agents-md.py --backup --apply`, ggf. 2× wegen eventual consistency); Clara direkt via `PUT /api/agents/{id}/instructions-bundle/file`. Beide live verifiziert, Jarvis-Namen erhalten.

## Bugs, die nur E2E/Review fanden (alle gefixt)

1. **launchd-PATH:** ffmpeg/whisper-cli in `/opt/homebrew/bin`, launchd-PATH kennt das nicht → „Transkription fehlgeschlagen". Fix: Binaries absolut auflösen + PATH in plist.
2. **500-Cap-Falle:** Unfilterte Company-Issue-Liste ist auf 500 gedeckelt und nicht newest-first → das neueste Issue fällt raus, Poll/Reply verpassen es. Fix: `?assigneeAgentId=<CEO>` (liefert alle CEO-Issues inkl. neuester, unter Cap; = korrekte Scope).
3. **Final-Review (Opus) — 3 Important:** korrupter State → Push-Sturm (`_seeded` an Datei-Existenz statt erfolgreichem Load); `poll_tenants` außerhalb try → launchd-Crash-Loop bei transientem auth/disk-Fehler; zweite Entscheidung am selben Issue verschluckt (decision-Key blieb ewig in `seen`). Alle gefixt.
4. **Regression im Re-Review:** reconcile behandelte `label_id=None` (transienter Auflösungsfehler) wie „Label entfernt" → Doppel-Push. Gefixt (no-op bei falsy label_id).

## Verifikation

- **46 Unit-Tests grün** (stdlib unittest).
- **E2E live:** A (Sprache → WHI-2882) ✅; B (Label → 🟠-Push → Reply → Kommentar am Issue) ✅ voller Roundtrip; C (Fertig-Push) per Proxy (gleicher Push-Pfad + done-Erkennung im Live-Poll verifiziert).
- Dienst läuft, Poll aktiv, kein Push-Sturm, Log sauber.

## Prozess (Superpowers)

Brainstorming → Spec → Plan → Subagent-Driven-Development (Implementer + Review je Task, Fix-Loops) → Final-Review. Specs/Pläne unter `docs/superpowers/specs/` und `docs/superpowers/plans/` (Dateien `2026-07-21-voice-echo-ceo-design.md`, `2026-07-21-jarvis-rueckkanal-multimandant-design.md`, plus die zwei Pläne).

## Git-Stand

- Alle Arbeit committet, per Fast-Forward in `feat/academy-lektor` konsolidiert (20 Jarvis-Commits), temporärer Branch gelöscht.
- **Gepusht auf `fork` = `whitestagai/paperclip`** (euer Fork; NICHT `origin` = `paperclipai/paperclip` = Produkt-Vendor). Upstream gesetzt.
- Head: `c265a0ca5`. PR-Vorschlag: https://github.com/whitestagai/paperclip/pull/new/feat/academy-lektor (noch nicht erstellt).

## Offene Punkte / Follow-ups (nicht blockierend)

- Clara muss `/start` beim Bot drücken.
- Expliziter Fertig-Push-E2E (C) mit Wegwerf-Issue steht noch aus (nur per Proxy abgedeckt).
- Minor: `candidates`/`seen` ohne TTL/Cap; 500-Cap-Ordering-Edge bei >500 CEO-Issues; blockierende Transkription stallt kurz den Loop; at-least-once Duplikat bei create_issue-Response-Timeout.
- **Gotcha:** Nicht `getUpdates` manuell gegen den Bot-Token curlen, während der Dienst läuft — klaut ihm den Single-Consumer und stört das Poll-Timing.
