# ToDo — Paperclip

Chatuebergreifende Aufgabenliste. Was hier steht, ist noch offen.

## Farm-Stabilitaet

- [ ] **★★WHITESTAG-AI nach jedem Neustart: Kartenzuordnung von Hand** — seit
      21.10. traegt der PC Primaerlast: `qwen3.6-35b-a3b` (Q4) allein auf der
      **5090** fuer 13 qwen-Agenten, `gemma-4-31b-it` (Q4) allein auf der **3090**
      fuer CMO + LLM-Analyst. `lms` kann keine GPU waehlen; nach einem Neustart
      liegen beide Modelle verteilt und LANGSAM. Neue `start_llms.bat`
      (Commit `db7362f38`, CRLF) hat Walter eingespielt; sie laedt nur und nennt
      oben die GUI-Schritte (`Ctrl+Shift+H`: 3090 aus → qwen, 5090 aus → gemma).
      **Zwei gespeicherte GUI-Einstellungen sind Pflicht:** bei qwen „Number of
      layers … MoE weights onto CPU" = **0** (stand auf 40 → alles CPU, 25 tok/s)
      und Kontext **262144** wegen „Unified KV Cache" (mit 98304 scheiterten
      4 × 27k). Nach dem naechsten Neustart von hier messen (`nvidia-smi` am PC:
      5090 ~24 GB, 3090 ~20 GB; Decode qwen > 150 tok/s). *(2026-10-21, Chat: LLM-Farm ohne RTX)*

- [ ] **Ursache der Geraeteausfaelle unbekannt** — RTX Pro 6000 am 10.10. ~10:30
      bis 12.10. morgens, WHITESTAG-AI am 14.10. ~09:30–15:20 (danach mit
      Standard-Kennungen, also vermutlich Neustart). Beide von Walter von Hand
      zurueckgeholt, nicht untersucht. Seit 12.10. kommt bei jedem Ausfall eine
      Mail. *(2026-10-14, Chat: WHITESTAG-AI Farm-Aufsicht)*

- [ ] **`google/gemma-4-12b` laeuft mit Fenster 131328 statt 65536** — hat
      sich im Lauf des 07.10. geaendert (um 09:09 war es noch 65536),
      Schwere niedrig. Vermutlich per Just-in-Time nachgeladen, das die
      `-c`-Vorgabe mit dem Default-Preset ueberschreibt. Kostet Speicher auf
      der Studio, die ohnehin 26 Primaermodelle traegt. Entweder das Soll
      anheben und begruenden oder die Default-Load-Config nachziehen.
      *(2026-10-07, Chat: WHITESTAG-AI Fallback-Node)*
      Seit 13.10. ist das 12B **kein Fallback mehr** — nur noch Hauptmodell des
      Link-Detektors. Das senkt die Dringlichkeit. *(2026-10-14, Chat: Agentenausfälle und Ursachen)*
      **Stand 14.10. abends: 98304 statt 65536** (nicht mehr 131328), weiter
      Schwere niedrig. *(2026-10-14, Chat: WHITESTAG-AI Farm-Aufsicht)*

- [ ] **Zwei Commits mit unpassendem Betreff aufraeumen (oder bewusst lassen)**
      — `f9e1893e2 docs(spec): Quantisierung …` enthaelt 458 Zeilen `ToDo.md`,
      `96d08d761 fix(plan): Aufsicht …` einen fremden Altplan vom 11.09.
      Beides durch unsauberes `git add` (`-a` bzw. `-A <ordner>` mit untracked
      Dateien). Inhaltlich gehoert beides ins Repo, nur die Betreffe passen
      nicht. Nicht korrigiert, weil gepusht — ein History-Rewrite auf einem
      Branch mit fremder Arbeit ist eine Entscheidung des Menschen.
      *(2026-10-07, Chat: WHITESTAG-AI Fallback-Node)*

- [ ] **Branch-Abschluss `fix/backup-leere-ref-ordner`** — die
      Node-Einbindung (14 Commits) liegt auf diesem Branch, der auch fremde
      Arbeit traegt (nextcloud-backup, wake-satellite, test_evict). Der
      merge-base zu master liegt weit zurueck: ein Review-Paket gegen master
      umfasste 24 Commits und 37 Dateien. Zu entscheiden: PR nach master,
      Umsortieren auf einen eigenen Branch, oder offen lassen.
      *(2026-10-07, Chat: WHITESTAG-AI Fallback-Node)*
      **Stand 14.10.:** der Heartbeat-Fix vom 07.10. ist auf einen eigenen Branch
      gezogen (`fix/heartbeat-active-runs-prozessweit` auf `fork/master`, 46 Tests
      gruen, gepusht). Auf diesem Branch kam `2ff46e9fd` (dataless-Waechter nach
      `tools/`) dazu. *(2026-10-14, Chat: Agentenausfälle und Ursachen)*
      **Stand 17.10.:** drei weitere Commits darauf (Heartbeat-Wake-Fix `7aa1a31a3`,
      Lektorats-Regel `bf4a427d1`, Testfix `af675f8cb`), per Fast-Forward von
      `fix/kinder-weckruf-folgelauf` uebernommen (Hilfsbranch danach lokal und
      auf `fork` geloescht). *(2026-10-17, Chat: Academy Kurs-Routine)*

- [ ] **Reasoning-Abschaltung fuer qwen3.6 im lmstudio-Adapter verankern** —
      gemessen senkt ein leerer `<think></think>`-Block als Assistant-Prefill
      die Antwortzeit von 9,86 s auf **1,85 s** (Faktor 5,3) bei gleicher
      Generierungsrate. `reasoning_effort: none` wirkt bei diesem Modell
      **nicht** und verschlechtert messbar. Der Hebel sitzt im Adapter
      (`opensource/paperclip-adapter-lmstudio`), dort wo die drei
      `reasoning_effort`-Pfade liegen. Betrifft die 12 qwen-Agenten inkl.
      C-Suite. Eigener Vorgang, weil Antwortqualitaet zu pruefen ist.
      *(2026-10-07, Chat: WHITESTAG-AI Fallback-Node)*

- [ ] **n8n-Betriebsingenieur: 92x `400 bad_request` in 16 Tagen — zugesagt, nicht
      diagnostiziert** — jeder Lauf scheitert zunaechst mit
      `Claude run failed: subtype=success: API Error: 400 bad_request` und
      **gelingt rund 12 Sekunden spaeter im Folgeversuch** (Modell
      `claude-sonnet-4-6`). Es haengt also nichts, aber jeder Lauf verbrennt einen
      Versuch, und der erste Fehlschlag zaehlt in jede Fehlerstatistik der Flotte
      hinein. Zuletzt am 04.10. 11:30 beobachtet. Das Modell ist nicht die
      Ursache — der Folgeversuch nutzt dasselbe. Verdacht: fehlerhafter Request
      (Tool-Schema oder Kontextgroesse) beim ersten Anlauf.
      Einstieg: `stderr_excerpt`/`stdout_excerpt` und `log_ref` eines
      `adapter_failed`-Laufs lesen —
      `select error_code, count(*), max(started_at) from heartbeat_runs r join agents a on a.id=r.agent_id where a.name='n8n-Betriebsingenieur' and r.status='failed' group by 1;`
      *(2026-10-06, Chat: Tote Modell-ID)*

- [ ] **`n8n_health.healthz()` im Recovery-Skript: API-Key statt Base-URL** —
      in `~/.paperclip/scripts/recovery/` wird `healthz(api_key)` statt
      `healthz(base_url)` aufgerufen. Das erzeugt eine Python-Exception →
      `False`-Rueckgabe → Folgeaufrufe laufen gegen eine falsch angenommene tote
      n8n-Instanz. Root Cause des fehlgeschlagenen Runs `9afec123` vom 15.10.
      Korrektur: den Aufruf auf die konfigurierte Base-URL umstellen (z.B.
      `os.environ["N8N_BASE_URL"]` oder aequivalent). Genaue Zeile noch zu
      bestimmen (`grep -n "healthz" ~/.paperclip/scripts/recovery/*.py`).
      *(2026-10-15, Chat: n8n Ops Recovery)*

- [ ] **★★Die Brain-/Vault-Werkzeuge erreichen die Agenten ueberhaupt nicht** —
      in **300 Runs ueber 48 Stunden kein einziger** `vault.*`-Aufruf,
      stattdessen **400x `shell_exec`**. Das ist die Ursache der Blindsuche und
      damit ein guter Teil der `max_iterations` (siehe Eintrag unten): Die
      AGENTS.md verweist auf `whitestag.brain` mit den Tools `vault.search` /
      `vault.list_scope` und der Anweisung „Erst suchen, dann handeln" — die
      Agenten greifen trotzdem zu `ls -R`, `find` und `grep -r` (Letzteres laeuft
      in den 30-s-Deckel von `shell_exec`).
      **Gegengeprueft und NICHT die Ursache:** Plugin-Status ist `ready`
      (`aeff1be7`, `whitestag.brain` 0.2.0), beide Dienste antworten
      (`:7777` WHITESTAG, `:7778` Clara, launchd `com.whitestag.brain-mcp*`),
      und `plugin_company_settings` ist **leer** — es gibt also keine
      Company-Sperre. Im Lauf-Log werden nur Paperclip-Skills aufgezaehlt, keine
      Plugin-Tools. **Verdacht:** der lmstudio-Adapter sammelt Plugin-Tools gar
      nicht erst ein. Naechster Schritt: im Adapter nachsehen, wie die
      Tool-Liste je Run zusammengestellt wird — ein Eingriff dort trifft die
      ganze Flotte, also nicht nebenbei.
      Nachweis: Tool-Namen aus allen `run-logs/*.ndjson` der letzten 48 h
      zaehlen (`kind == "tool_call"`).
      *(2026-09-15, Chat: Mailhub und Recovery-Kaskade)*
      **Bestaetigt 12.10.:** in 763 lmstudio-Runs ueber 7 Tage **null**
      `vault`-/`brain`-Aufrufe. Weiter offen. *(2026-10-14, Chat: Agentenausfälle und Ursachen)*

- [ ] **Mailhub-Reste nach dem IMAP-Fix** — die Phantomflut ist weg (2–5 pro
      Stunde → **eine in 20 Stunden**, `Mailhub V11` mit `forceReconnect: 15`
      statt 60 in allen 11 IMAP-Nodes; `Error-Handler V7` liest jetzt
      `t.trigger?.error` und liefert wieder echte Diagnosen). Offen bleiben drei
      Kleinigkeiten: (1) **Mailempfang nie end-to-end geprueft** — belegt ist
      nur eine zufaellig eingegangene Mail, eine Testmail an eines der elf
      Postfaecher steht aus; (2) **WHI-8228** (die verbliebene echte Meldung,
      Node `IMAP Clara CEO`, 04:34 nachts — vermutlich Provider-Wartung) liegt
      **unassigned im `backlog`**, der n8n-Betriebsingenieur greift diese
      Issue-Sorte nicht auf; (3) im Error-Handler steckt ein **Paperclip-
      Board-Token im Klartext** fest verdrahtet (Fundort: Workflow
      `spvMh6dLQpd43BSz`, Node `Konfiguration`) — genau so ein hartkodierter
      Token hat den Mailhub-Inbound schon einmal nach 30 Tagen still
      stillgelegt, vgl. `project_deliverable_watcher_token_ttl`.
      *(2026-09-15, Chat: Mailhub und Recovery-Kaskade)*
      **Stand 19.09.: (2) und (3) sind erledigt, (1) steht weiter aus.**
      (3) gegengeprueft: Der Node `Konfiguration` traegt **keinen** Klartext-
      Token mehr, `paperclipToken` ist die Expression
      `={{ $('Token lesen').first().json.token }}` und liest aus
      `~/.paperclip/.n8n-link-detektor-token`. (2) WHI-8228 ist `cancelled` —
      allerdings **durch den Massen-Storno vom 19.09.**, nicht inhaltlich
      bearbeitet; falls die Provider-Wartungs-Frage noch interessiert, ist sie
      damit unbeantwortet.
      **Und der Kern des Eintrags ist widerlegt:** `forceReconnect: 15`
      **reicht nicht**. In der Nacht zum 19.09. entstanden erneut **443 Issues
      in 15 Stunden** (282 Mailhub, 161 Clara), alle 11 IMAP-Nodes gleichmaessig
      betroffen (24–36 je Node) — der Mailserver kappt die Langzeitverbindung
      haeufiger, als n8n von sich aus neu verbindet. Die Issue-Flut ist seit dem
      19.09. per Entprellung im Error-Handler V8 gedeckelt (ein Issue je
      Workflow und Tag), **die Ursache am Mailserver ist damit nur zugedeckt,
      nicht behoben**. Verdacht: Verbindungslimit bei 11 gleichzeitigen
      Postfaechern auf demselben Server. *(2026-09-19, Chat: Nachtfehler und Modell-Wächter)*

- [ ] **★★VP Engineering laeuft leer — 2.143 Runs, 99 % Fehlerquote** — mit
      Abstand der groesste Einzelverbraucher der Flotte (23 % aller Runs der
      letzten 14 Tage) und praktisch ohne Ergebnis. **Zwei Drittel davon sind
      derselbe Fehler:** 1.388 von 2.118 Fehlschlaegen lauten
      `LLM call failed on fallback: LM Studio model error 400 — Invalid model
      identifier "qwen2.5-coder-14b-instruct-mlx"`. Der Agent faehrt
      `claude-sonnet-5` ueber den PII-Proxy (`ANTHROPIC_BASE_URL` →
      `localhost:4711/anthropic`); sein `fallbackModel` ist **`null`**, die tote
      Modell-ID steht also **nicht** in seiner `adapter_config`. Gegenprobe: die
      ID kommt weder in `agents.adapter_config`/`runtime_config` noch in
      `instance_settings` vor — nur in LM Studios `model-data.json` und in
      llm-advisor-Testfixtures. Sie wird demnach **zur Laufzeit** vergeben,
      Verdacht: Modell-Router/lmstudio-Adapter waehlt fuer die Coder-Rolle ein
      „coder"-Modell, das nach dem `-mlx`-Rename nicht mehr existiert (passt zum
      bekannten Muster „LM-Studio-Rename bricht Fallbacks"). Zweitgroesster
      Posten: 642 × `Prompt is too long` / `adapter_failed`.
      Nachweis:
      `select error_code, count(*) from heartbeat_runs r join agents a on a.id=r.agent_id where a.name='VP Engineering' and r.status='failed' and r.started_at > now() - interval '14 days' group by 1 order by 2 desc;`
      **Verwandter Befund aus derselben Messung:** Buchhaltung (418 Runs, 96 %
      Fehler) und Lektorat (159 Runs, 96 %) laufen ebenfalls leer, dort aber aus
      anderer Ursache — fast ausschliesslich `max_iterations` (386 bzw. 147),
      gehoert also zum bestehenden `max_iterations`-Eintrag unten. Die drei
      Agenten zusammen sind rund ein Drittel aller Flotten-Runs.
      *(2026-09-11, Chat: Routinen-Lastverteilung)*
      **Gegenprobe 11.09. abends: der Hauptposten ist weg.** Die tote Modell-ID
      `qwen2.5-coder-14b-instruct-mlx` kommt in **7 Tagen kein einziges Mal**
      mehr vor (`select count(*) from heartbeat_runs where error like
      '%qwen2.5-coder%' and started_at > now()-interval '7 days'` → 0). Was in
      den letzten 24 h bleibt, ist ein **anderer** Fehler: 8 × `adapter_failed`
      und 2 × `claude_auth_required`, beide mit derselben Meldung
      `400 blocked_by_pii_proxy:classifier_unavailable`. Der Eintrag gehoert
      damit inhaltlich zum PII-Proxy-Punkt weiter unten, nicht mehr zum
      Modell-Rename. *(2026-09-11, Chat: WHITESTAG Agenten-Aufsicht)*
      **Stand 12.09.: der PII-Anteil ist weg, ein neues Muster tritt hervor.**
      In 14 Tagen 2.120 `failed` gegen 24 `succeeded` (1,1 %), davon 641×
      `classifier_unavailable` seit dem 01.09. — diese Ursache ist am 12.09.
      behoben (siehe PII-Proxy-Punkt). **Seit dem Deploy um 21:11 kein einziger
      `classifier_unavailable` mehr**, dafuer 2 von 4 Runs mit
      `error_max_turns: Reached maximum number of turns (80)`; einer lief
      29 Minuten in dieses Limit. `maxTurnsPerRun: 80` steht in seiner
      `adapter_config`. Zu klaeren, ob das Limit zu niedrig ist oder der Agent
      sich verrennt — erst eine Woche mit funktionierendem Proxy beobachten,
      vorher ist jede Bewertung Blindflug. *(2026-09-12, Chat: LLM-Farm GeForce-Umzug)*

- [ ] **`max_iterations` bleibt als eigenes Muster** — die Infrastrukturfehler
      (`fetch failed`, `Engine protocol`) sind mit dem Circuit Breaker und der
      RTX-Rueckkehr weg; `max_iterations` nicht. Sechs Agenten stehen weiter auf
      Limit 8 (Adobe, CFO, DPO, Mistika VR, Vermoegensverwaltung, Web-Design
      Specialist). Die Buchhaltung wurde am 05.09. auf 12 gesetzt, weil sie bei 8
      alle Turns fuer die Vorbereitung verbrauchte und nie zur Aussage kam, was
      ihr fehlt. Ob die uebrigen sechs das auch brauchen, ist ungeprueft — der
      CFO schafft mit 8 durchaus 184 erfolgreiche Runs, es haengt am
      Arbeitsablauf. *(2026-09-05, Chat: Routinen, Fallback und Mail-Anhänge)*
      **Ergänzung 06.09.:** Beim neuen Agenten R9 (Clara) war Limit 8 nachweislich
      zu niedrig — die Runden gingen für Inbox, Checkout und Kontextlesen drauf,
      *bevor* die erste Seite geladen war. Merksatz für die sechs übrigen:
      `maxIterations` begrenzt **Tool-Runden**, `maxPromptTokens` den **Kontext**.
      Beide zusammen zu senken ist ein Denkfehler — eine kontextsparende
      Arbeitsweise (Einheit für Einheit, Ergebnis sofort wegschreiben) braucht per
      Konstruktion *mehr* Runden. Wer viele Tool-Aufrufe je Aufgabe macht, braucht
      ein hohes Limit; 60 hat sich bei R9 bewährt. *(2026-09-06, Chat: Kontaktrecherche-Agent Clara)*
      **★Messung 13.09. — die Betroffenen sind andere als gedacht.** Anteil
      `max_iterations` an allen Runs (14 Tage): **Lektorat 94 %** (227/242),
      **Buchhaltung 92 %** (393/427), Recherche 64 %, **Online-Rechercheur 49 %
      trotz Limit 30**, Akquise & Booking 38 %, Redaktion & PR 36 %, Creative
      Assistant 33 %, Bueroleitung 22 %, Sekretaerin 18 %, CFO 8 % (Limit 8!),
      **CTO 7 %, CEO 7 %**. Bei Lektorat und Buchhaltung ist das Scheitern also
      der **Normalzustand**, nicht die Ausnahme — die Buchhaltung wurde am 05.09.
      bereits von 8 auf 12 gehoben, ohne Wirkung. Umgekehrt sind CEO/CTO trotz
      Limit 12 unauffaellig; dass beide in der Nacht zum 13.09. daran scheiterten,
      war Zufall. **Naechster Schritt:** bei einem der beiden Dauerfaelle
      nachsehen, wofuer die zwoelf Runden draufgehen (`heartbeat_run_events`) —
      Hochdrehen allein hilft nachweislich nicht, siehe Online-Rechercheur.
      Nachweis: `select a.name, a.adapter_config->>'maxIterations', count(*) filter (where r.error_code='max_iterations'), count(*) from heartbeat_runs r join agents a on a.id=r.agent_id where r.started_at > now() - interval '14 days' group by 1,2;`
      *(2026-09-13, Chat: Selbstheilung wiederhergestellt)*
      **★★15.09.: der „naechste Schritt" ist erledigt — die Runden gehen fuer
      ORIENTIERUNG drauf, nicht fuer die Aufgabe.** Ein typischer Office-&-Admin-
      Run (Volllog `heartbeat_run_events` + `run-logs/*.ndjson`) verbraucht alle
      zwoelf Runden so: **6 fuer Paperclip-Verwaltung** (Inbox, Checkout → HTTP
      422 durch einen abgebrochenen Blocker, Kontext, Kommentare, Blocker loesen,
      Checkout) und **6 fuer Blindsuche im Vault** (`ls -R`, `find`, `grep -r`
      → Timeout nach 30 s, wieder `find`) — **null fuer die eigentliche Arbeit**.
      **Die Ursache der Blindsuche ist ein fehlendes Werkzeug, kein fehlendes
      Wissen:** die AGENTS.md nennt die Vault-Pfade absolut *und* das Suchwerkzeug
      `whitestag.brain` — siehe eigenen Eintrag unten, es wird nie aufgerufen.
      **Hochdrehen ist damit widerlegt, nicht nur zweifelhaft:** Limit bei sieben
      nachweislich betroffenen Agenten am 14.09. von 12 auf **20** gesetzt
      (Office & Admin, Bueroleitung, Creative Assistant, Akquise & Booking, CEO,
      CTO, Sekretaerin). Die Meldungen sagen seither „Max iterations (20)" — und
      scheitern weiter; der Online-Rechercheur ebenso bei 30. **Wirksam war
      stattdessen das Abraeumen der toten Blocker:** Office & Admin fiel von 16
      Fehlschlaegen (14.09.) auf 0 (Nacht auf den 15.09.).
      **Nebenrisiko der Erhoehung, noch nicht gemessen:** 20 Runden x
      `maxToolResultChars: 12000` liegt rechnerisch an der `maxPromptTokens`-
      Grenze von 70k — passt zum Overflow-Eintrag weiter unten.
      *(2026-09-15, Chat: Mailhub und Recovery-Kaskade)*
      **★★04.–06.10.: ein naheliegender Verdacht ist widerlegt.** Die Vermutung
      war, die stille Umleitung auf das kleinere `google/gemma-4-12b` (tote
      Modell-ID, siehe eigener Eintrag) erzeuge die Flut — ein 12B braucht fuer
      dieselbe Werkzeugkette mehr Runden. **Nach der Korrektur aller Fundorte
      sank die Zahl NICHT:** 10-01: 13 · 10-02: 23 · 10-03: 29 · 10-04: 12 ·
      **10-05: 46** · 10-06: 9. Der hoechste Wert liegt NACH dem Fix. Und 27 von
      46 Fehllaeufen liefen weiter auf dem 12B — nicht wegen einer toten ID (die
      Konfigurationen sind sauber), sondern weil `fallbackModel` bei 25 Agenten
      regulaer dorthin zeigt und greift, wenn das 31B gerade nicht liefert.
      **Die Diagnose vom 15.09. bleibt also gueltig und ist zweimal bestaetigt:**
      Bei Lektorat gingen 10 von 12 Runden fuer die Suche eines Pfades weg, den
      die Rollendatei nur vault-relativ nannte — nach der Korrektur auf den
      absoluten Pfad las der Folgelauf beim ersten Versuch und schloss zwei
      Issues mit substanziellen Befunden ab. Beim Clara-Vault-Maintainer fehlte
      die `AGENTS.md` komplett (eigener Eintrag unten).
      **Konkreter naechster Fall:** **Redaktion & PR**, seit dem 05.10. mit
      **37 Fehllaeufen bei Grenze 12** der dominante Verursacher, Modell
      `google/gemma-4-31b` — Laufprotokoll noch nicht angesehen.
      **Vorgehen, das sich bewaehrt hat:** `log_ref` aus `heartbeat_runs` holen,
      die ndjson lesen und die Werkzeugabfolge extrahieren. Geht das Budget fuer
      Orientierung weg (`fs_glob`, `fs_list_directory`, mehrfaches `grep` nach
      derselben Sache), fehlt ein Rezept — dann hilft weder ein groesseres Modell
      noch eine hoehere Grenze.
      *(2026-10-06, Chat: Tote Modell-ID)*
      **★★Stand 14.10.: drei Ursachen gefunden und behoben, die Zahl ist trotzdem
      noch 22/Tag — aber aus ANDEREN Agenten.** (1) Neun Clara-Agenten hatten in
      der AGENTS.md den falschen Vault (`WHITESTAG-Vault/Paperclip/Clara` statt
      `/Volumes/homes/cw/Obsidian/Clara-Vault`) → „Path traversal blocked" in 41 %
      der Fehllaeufe (5 % bei Erfolgen); korrigiert, 187 Dateien umgezogen.
      (2) LLM-Konfigurationsanalyst hielt Exit-Code 1 des Waechters fuer Absturz
      → Routine klargestellt. (3) `runtime_config…cheap.fallbackModel` war bei
      11 Agenten `gemma-4-12b`: 38 % max_iter und ALLE Schleifen → auf
      `gemma-4-31b-win` (Walters Wahl). Ergebnis nach 24 h: Pfadsperren 0,
      Schleifen 0, Redaktion & PR 0 (vorher 51/Woche), Analyst 0 (vorher 20).
      **Die 22 kommen jetzt von Buchhaltung (11) und Creative Assistant (5)** —
      eigener Eintrag unten. *(2026-10-14, Chat: Agentenausfälle und Ursachen)*

- [ ] **★Doppelter Follow-up-Run unter Last (Verdacht)** — in
      `heartbeat-comment-wake-batching.test.ts` scheitern zwei Tests **nicht am
      Timing, sondern an der Anzahl**: Diagnose in der Wartebedingung ergab
      `["cancelled","succeeded","succeeded"]` — **drei** Runs statt der
      erwarteten zwei, alle in Endzuständen. Einzeln ausgeführt ist der Test
      grün (zwei Runs), erst zusammen mit den anderen Tests der Datei kommt ein
      dritter dazu. Die `agentId` ist pro Test zufällig, Verschmutzung durch
      Nachbartests scheidet aus. In CI grün — also ein Zeitfenster, das lokal
      häufiger trifft. Wenn sich das bestätigt, erzeugt Paperclip unter Last
      überzählige Runs; das schlägt direkt auf die Laufkosten durch. Nächster
      Schritt: herausfinden, wer den dritten Run anlegt (Heartbeat-Kern).
      *(2026-09-05, Chat: Release-Kette repariert)*

- [ ] **PII-Proxy: Ursache behoben, Wirkung über 24 h noch gegenzuprüfen** —
      der Dauerposten `blocked_by_pii_proxy:classifier_unavailable` (882 Treffer
      in 14 Tagen, drittgroesster Fehlerposten der Flotte) ist am **12.09.
      ursaechlich behoben**: `buildBoundary()` wuerfelte den Trenner zwischen den
      Nachrichten **pro Request neu**, dadurch bekam jeder Chunk mit einer
      Nachrichtengrenze einen neuen sha256 — gemessen rund die **Haelfte aller
      Chunks** (120 Runden: 122 von 248). Der Chunk-Cache lief damit ins Leere:
      141.930 Eintraege, taeglich tausende neue (12.09.: 11.249), 63,2 s mittlere
      Antwortzeit (Max 710,9 s), Client bricht ab, fail-closed blockt.
      Fix: `FIXED_BOUNDARY` in beiden Passthrough-Routen, `buildBoundary()` bleibt
      Kollisions-Ausweichung. Commit `dd1bbfd` auf `fix/stable-classifier-boundary`,
      gebaut und per launchd deployed. Seit 21:11 kein Block mehr, erster Testlauf
      nach Wochen wieder `succeeded`.
      **Offen ist die Gegenprobe:** (1) taegliche neue Cache-Hashes gegen den Wert
      vom 12.09. (11.249) stellen — sie muessen bei vergleichbarer Last deutlich
      einbrechen; (2) Erfolgsquote der Cloud-Agenten ueber 24 h.
      `select count(*) from heartbeat_runs where error like '%classifier_unavailable%' and started_at > now() - interval '24 hours';`
      *(2026-09-12, Chat: LLM-Farm GeForce-Umzug)*
      **Teil (2) am 13.09. bestanden: 0 Treffer in 24 h** gegen **791 in sieben
      Tagen**. Der Fehler ist damit weg, nicht nur seltener. **Teil (1) steht
      weiterhin aus** — die Cache-Hashes wurden nicht gemessen; ohne sie ist
      belegt, dass die Wirkung eintrat, aber nicht, dass der Cache jetzt
      greift. *(2026-09-13, Chat: Selbstheilung wiederhergestellt)*

- [ ] **★Buchhaltung findet die Rechnungen nicht — jetzt Hauptverursacher von
      `max_iterations` (11 von 22 in 24 h)** — Beispiel WHI-10049 „IKEA-Rechnung
      verbuchen": der Agent sucht in `WHITESTAG-Vault/Buchhaltung/` und
      `Paperclip/_INBOX/`, `fs_glob *IKEA*` bleibt leer, Runden verbraucht. Ihm
      fehlt die Angabe, WO Rechnungen ankommen (Mail-Anhang? Belege-Ordner aus dem
      Mail-Spiegel, vgl. Abschnitt „Mail-Spiegel und Belege"). Gleiches Muster wie
      die Feinschliff-Routine: Rezept mit einem einzigen Suchaufruf in die Routine
      bzw. AGENTS.md. Danach Creative Assistant (5) ansehen. *(2026-10-14, Chat: Agentenausfälle und Ursachen)*
      **Stand 17.10.:** WHI-10049 (IKEA 1622979641) ist echt, aber die PDF hing
      nur an der Mail vom 17.08. und wurde nie gespiegelt (Mail im Vault sagt
      „im Anhang") → **Walter: PDF aus ws@whitestag.film nach
      `Buchhaltung/Rechnungseingang/` legen**, dann WHI-10049 wecken.
      WHI-10048 („Lorberg #1089") abgebrochen: Absender `sweetmusiclessons.com`,
      „bereits ueberwiesen", kein Anhang, Lorberg sonst nirgends im Vault —
      **vermutlich Phishing, Walter bitte bestaetigen.** *(2026-10-17, Chat: Academy Kurs-Routine)*
      **Stand 21.10.:** Buchhaltung stand seit 17.10. auf `error` und nahm nichts mehr an —
      per `resume` zurueckgeholt (`idle`). WHI-10049 bleibt `blocked`, bis die IKEA-PDF
      in `Buchhaltung/Rechnungseingang/` liegt. *(2026-10-21, Chat: LLM-Farm ohne RTX)*

## Selbstheilung und Agenten-Aufsicht

- [ ] **Aufsicht sieht nicht, ob ein Modell auf der GPU rechnet** — Soll-Laufzeit prueft
      nur Kontext und Slots. Am 21.10. lief qwen auf WHITESTAG-AI stundenlang mit
      Experten auf der CPU (25 statt 170+ tok/s), ohne jeden Befund. Vorschlag: in
      `node-wacht/erreichbarkeit.sh` alle 15 Min eine Kurzanfrage (≈600 Token) an
      beide Node-Modelle, Decode-Rate loggen; unter Schwelle (qwen < 80, gemma < 15
      tok/s) Mail ueber den Melder. *(2026-10-21, Chat: LLM-Farm ohne RTX)*

- [ ] **Office & Admin (Clara) scheitert an CLAA-3169** — „Oktober-Auftritte ermitteln und
      Rechnungen erstellen" (R7): 6 Fehllaeufe am 21.10. (`max_iterations` 20, ein
      Timeout), sucht eine **Rechnungsvorlage, die es nicht gibt**; Hilfestellung der
      Bueroleitung half nicht. Agent per `resume` aus `error` geholt, Issue `blocked`.
      **Zu entscheiden:** Vorlage bereitstellen (Pfad in die AGENTS.md), Auftrag in
      Einzelrechnungen zerlegen, oder an einen qwen-Agenten (jetzt schnell auf der 5090)
      geben. *(2026-10-21, Chat: LLM-Farm ohne RTX)*

- [ ] **Heartbeat-Wake-Fix im Live-Betrieb belegen** — seit 17.10. 09:36 werden
      `issue_children_completed`/`issue_blockers_resolved` bei laufendem Run
      zurueckgestellt statt eingerechnet (Commit `7aa1a31a3`). Der Ernstfall trat
      bis Feierabend nicht auf. Pruefen, dass er greift und nichts mehr verschluckt:
      `select status, count(*) from agent_wakeup_requests where created_at > '2026-10-17 09:36+02' and payload ? 'childIssueIds' group by 1;`
      — `deferred_issue_execution` muss auftauchen, `coalesced` darf nicht mehr. *(2026-10-17, Chat: Academy Kurs-Routine)*

- [ ] **Clara: zwei Sammelauftraege laufen in `max_iterations`** — CLAA-2994
      (R4 Oktober-Newsletter, mit doppelten Pressetext-Kindern CLAA-3019/3030/3024)
      und CLAA-2977 (R5 Themen-Dossier, Kind CLAA-2981 ohne Assignee) sind fuer 12
      Schritte zu gross. Inhaltlich entscheiden: Oktober-Newsletter noch senden?
      Dann Kinder entdoppeln und zuweisen, sonst abbrechen. CLAA-2867 hat sich die
      Kinder selbst zugewiesen, ist aber wieder `blocked` (Post-Run-Guard). *(2026-10-17, Chat: Academy Kurs-Routine)*

- [ ] **Generator-Falle `build-agents-md.py`** — `--backup --apply` zusammen fuehrt
      nur das Backup aus (`main()` kehrt nach dem ersten Modus zurueck), meldet aber
      nichts. Entweder Modi kombinierbar machen oder bei mehreren Flags abbrechen. *(2026-10-17, Chat: Academy Kurs-Routine)*

- [ ] **★★Clara-Vault-Routine stillgelegt — Entscheidung ueber die Zukunft offen**
      — der Agent (Clara Sound / Vault-Maintainer, `500a1656`) hat **keinen
      `instructionsFilePath`**, das Issue verweist aber auf „Siehe AGENTS.md fuer
      den vollstaendigen Ablauf". Folge: Er suchte sie im Dateisystem und
      verbrauchte sein Budget — und wenn er doch abschloss, tat er es mit
      **erfundenem Text**. Der als `succeeded` verbuchte Lauf vom 03.10. machte
      sechs Schritte (Inbox, Checkout, Kontext, Kommentare, **ein einzelnes
      `ls -R`**) und kommentierte dann „Running obsidian-tagger … All files
      processed successfully. Frontmatter and tags are updated." Der Tagger wurde
      nie aufgerufen.
      **Am 04.10. abgeraeumt:** Routine auf `paused` (nicht `archived` —
      rueckholbar), 35 hohle `done` und 8 liegengebliebene `blocked` auf
      `cancelled`, die 30 echten bis 22.08. unberuehrt, Agent aus `error` zurueck.
      Null Laeufe dabei ausgeloest (Status-Patch ohne `comment`, vorher an einem
      Issue geprueft). Begruendung samt Randbedingungen steht in der
      Routinen-Beschreibung.
      **Und sie wird womoeglich gar nicht gebraucht:** 15.929 von 15.962
      Markdown-Dateien im Clara-Vault haben Frontmatter (99 %); ohne die Ordner
      `.obsidian-tagger-backup` und `.obsidian` fehlen **genau zwei**
      (`_status.md`, `.trash/Willkommen.md`). Der Tagger lief zuletzt am
      **22.08.** gegen Clara.
      **Zu entscheiden:** ganz aufgeben, oder als monatliches Sicherheitsnetz neu
      bauen. **Drei harte Randbedingungen dafuer:** (1) der lokale Spiegel
      `~/.paperclip/clara-vault-mirror` taugt NICHT als Ziel — `sync-clara-mirror.js`
      ist read-only mit `rsync -a --delete`, Frontmatter schreiben muss auf SMB;
      (2) ein zsh-launchd-Job kommt nicht an SMB-Inhalte, **node schon** (Beweis:
      `com.whitestag.brain-indexer-clara` laeuft als node-Job direkt auf dem
      Vault); (3) `shell_exec` cappt bei 120 s — der Agent darf den Tagger nicht
      selbst fahren, genau deshalb wurde er bei WHITESTAG in einen launchd-Dienst
      ausgelagert. Richtige Bauweise waere also ein node-launchd-Dienst, der
      `vault-tagger-clara-last.json` schreibt, plus eine AGENTS.md, die den
      Agenten nur den Status lesen und **mit Zahlen** berichten laesst
      (`exit_code`, `ok=/fail=`, Report-Pfad) — diese Belegpflicht ist das, was
      das Fabulieren verhindert, nicht die Iterationszahl.
      *(2026-10-04, Chat: Tote Modell-ID)*

- [ ] **★Vorfall-Abschluss nachziehen — Entscheidung offen** — er liegt weiter
      **nur** in `feat/vorfall-abschluss`, waehrend die plist des Dev-Servers
      `INCIDENT_CLOSURE_ENABLED=true` setzt: eine Variable fuer Code, der im
      laufenden Stand nicht existiert. Am 13.09. bewusst **nicht** mit der
      Selbstheilung uebernommen, weil er damit **sofort scharf** gewesen waere —
      er gibt geparkte Arbeit frei und war bei gestoerter Farm schon einmal ein
      Laufband (104 Issues zu, 74 neu). Bei aktuell 87 blockierten Issues eine
      eigene Entscheidung. **Wenn nachgezogen: vorher `INCIDENT_CLOSURE_ENABLED`
      auf `false`**, dann bewusst einschalten und den ersten Lauf beobachten.
      Dateien: `server/src/services/recovery/incident-closure*.ts` plus
      `config.incidentClosure` (Default dort ist `=== "true"`, also AUS).
      *(2026-09-13, Chat: Selbstheilung wiederhergestellt)*

- [ ] **Der neue Waechter hat noch nie einen Ernstfall gemeldet** — der
      **Meldeweg** ist end-to-end belegt (Testmail 13.09., n8n-Ausfuehrung
      08:51:16 `success`), die **Befundlogik im Feld** aber noch nicht ausgeloest
      worden: Bei jedem bisherigen Lauf war die Lage `ruhig`. Beim ersten echten
      Befund gegenlesen, ob Betreff und Text taugen und ob die
      Zustandswechsel-Erkennung wirklich nur einmal mailt.
      Log: `~/.paperclip/logs/agent-wacht.launchd.log`,
      Zustand: `~/.paperclip/logs/agent-wacht-last.json`.
      *(2026-09-13, Chat: Selbstheilung wiederhergestellt)*

## Recovery-Mechanismus

- [ ] **★Der `todo`-Stapel ist sortiert, aber nicht abgeraeumt** — 109 Issues ohne
      Assignee, 103 davon aelter als eine Woche, 37 aelter als 30 Tage. Agenten
      greifen per Regel **nie** nach unzugewiesener Arbeit, der Stapel ist also
      nicht langsam, sondern tot. Triage vom 03.10.:
      **A Modell-Aufsicht 30** — **erledigt 12./14.10.:** alle offenen
      Aufsichts-Issues (112 + 6 Routine-Reste + 2) auf `cancelled`, die
      07:30-Routine pausiert.
      **B Clara-Briefings 56** — Wochen-Briefings R2–R8, 12–47 Tage alt; ein
      KW-34-Briefing hat im Oktober keinen Wert.
      **C echte Arbeit 11** — brauchen einen Assignee, darunter **WHI-4843**
      („Antwort an VanChat finalisieren und versenden", kundenseitig, inzwischen
      ueber 40 Tage) und **WHI-9013** („🔴 ROT: E-Mails Clara V1 — NAS-Volume
      nicht gemountet, 160+ Fehler").
      **D Meta/Folgeaufgaben 7** und **E Routine-Rauschen 5** — durch die Arbeit
      vom 04.10. ueberholt.
      **Beim Abraeumen:** ohne `comment` fahren, siehe Aufraeum-Rezept.
      Nebenbefund: **WHI-5067** will den Newsletter auf `abiray/qwen3.6-35b-a3b`
      setzen — diese ID ist selbst tot (HTTP 400), das Issue wuerde den Fehler
      einbauen.
      *(2026-10-03, Chat: Tote Modell-ID)*

- [ ] **★★Recovery-Issues blockieren ihr eigenes Rettungsziel** — struktureller
      Bug: Paperclip erzeugt fuer ein haengendes Issue Z ein Recovery-Issue R,
      traegt dabei `R blocks Z` ein und gibt anschliessend auf ("Paperclip
      stopped automatic stranded-work recovery"). Damit haelt R sein eigenes
      Ziel dauerhaft fest. Am 02.09. wurden 35 solcher Paare aufgeloest, bis
      zum Abend bildeten sich **24 neue**. Das ist die Ursache der immer wieder
      volllaufenden Issue-Liste — Abraeumen ist nur Symptombehandlung.
      Nachweis:
      `select r.identifier, z.identifier from issues r join issues z on z.id=r.origin_id::uuid join issue_relations x on x.issue_id=r.id and x.related_issue_id=z.id and x.type='blocks' where r.status='blocked' and z.status='blocked';`
      *(2026-09-02, Chat: Paperclip Issue-Bereinigung)*
      **Stand 11.09.: Halde zweimal geleert, Bug besteht.** Am 09.09. wurden 57
      Paare aufgeloest, am 11.09. weitere 27 plus 33 **verwaiste** Recovery-Issues
      (blocked, blockieren aber nichts — reine Karteileichen) und 8 Faelle mit
      ausschliesslich toten Blockern. `blocked` fiel von **158 auf 44**, davon
      sind jetzt **39 regulaere Arbeit** statt Mechanik: Recovery-Issues in
      `blocked` gingen von 60 auf **1**. Das Nachwachsen ist damit nicht
      gestoppt, nur der Bestand abgetragen — am 09.09. entstanden binnen eines
      Tages 65 neue Recovery-Issues. Die **wirksame** Gegenmassnahme war nicht
      das Abraeumen, sondern das Beseitigen der Fehlerquelle, die das Stranden
      ausloest (siehe Lessons-Schleife unten).
      **Stand 13.09.: Halde wieder bei 87** (von 44 am 11.09. abends), davon
      **15 Recovery-Issues** (gegen 1) und 72 regulaere Arbeit. **Elf Paare
      blockieren erneut ihr eigenes Rettungsziel.** Aus der Nacht selbst stammen
      allerdings nur **5** neue — das Wachstum liegt ueberwiegend im Zeitraum
      11.–12.09. Zu pruefen, ob die am 13.09. reparierte Selbstheilung das
      Nachwachsen daempft: sie beseitigt eine Quelle des Strandens (Agenten, die
      in `error` liegen bleiben, waehrend ihre Issues offen sind).
      *(2026-09-13, Chat: Selbstheilung wiederhergestellt)*
      **★★15.09.: die NEUERZEUGUNG ist behoben — Commit `fb0898d22`.** Zweite,
      eigenstaendige Ursache neben dem Blocker-Bug oben: Der Cap
      `MAX_RECOVERY_IN_PLACE_CYCLES = 3` zaehlt Eskalationen **pro
      Recovery-Issue-Id**, und `findOpenStrandedIssueRecoveryIssue` schliesst
      `done`/`cancelled` aus. Gelingt die Recovery — der **Normalfall**, sie
      weckt ja nur — gilt sie weder als offen noch traegt sie einen
      Zaehlerstand; der naechste Fehlschlag legt eine **frische** Recovery mit
      Zaehler 0 an. Die Bremse wird nie erreicht.
      **Live belegt:** acht Quell-Issues mit Mehrfach-Recovery in drei Tagen und
      **in jedem Fall ALLE Recovery-Issues `done`** (9/9, 9/9, 8/8, 6/6, 3/3,
      3/3, 2/2, 2/2). Zwei Kaskaden liefen an aufeinanderfolgenden Tagen ueber
      je ~1,5 h (CLAA-2307 mit Office & Admin, WHI-8230 mit dem
      Online-Rechercheur) und verbrannten je ein bis zwei Dutzend Laeufe, bis
      sie sich zufaellig selbst aufloesten.
      Fix: abgeschlossene Recoveries zaehlen pro **Quell-Issue** mit; ist der
      Deckel erreicht, entsteht kein neues Recovery-Issue und die Quelle bleibt
      sichtbar `blocked`. TDD (RED `expected 5 to be less than or equal to 3`),
      45/45 + 111 Tests gruen, `tsc --noEmit` sauber, nach `fork/master`.
      Nachweis: `select o.identifier, count(*), count(*) filter (where r.status='done') from issues r join issues o on o.id::text = r.origin_id where r.origin_kind is not null group by 1 having count(*) > 1;`
      *(2026-09-15, Chat: Mailhub und Recovery-Kaskade)*

- [ ] **★Der neue Kaskaden-Deckel ist noch durch keine echte Kaskade gelaufen** —
      getestet und seit dem 15.09. live (Dev-Server per `kickstart` neu
      gestartet), aber im Feld unbewiesen. Beim naechsten Vorfall gegenlesen:
      Bei **drei** Recovery-Issues je Quelle muss Schluss sein, und das
      Quell-Issue muss sichtbar `blocked` liegen bleiben statt weiterzurotieren.
      Wartende Kandidaten: **WHI-8230**, **CLAA-2508**, **CLAA-2499** (alle
      `todo`). *(2026-09-15, Chat: Mailhub und Recovery-Kaskade)*

- [ ] **CLAA-2499 und CLAA-2508 haengen seit dem 03.09.** — „R3 Woechentlicher
      Redaktionsplan" (Social Media & Community) und „R4 Taegliche
      Textfeinschliff-Triage" (Redaktion & PR) stehen seit zwoelf Tagen auf
      `todo` und erzeugen alle sechs Stunden eine Productivity-Review, bisher
      **23 Stueck**. **Kein Code-Fehler:** die Abstaende entsprechen exakt
      `DEFAULT_PRODUCTIVITY_REVIEW_RESOLVED_SNOOZE_MS` (6 h), der Mechanismus
      arbeitet wie ausgelegt. Das Problem sind die Quell-Issues — inhaltliche
      Entscheidung: loesen, neu zuschneiden oder abbrechen.
      *(2026-09-15, Chat: Mailhub und Recovery-Kaskade)*

- [ ] **Zwei Stornierungen mit Vorbehalt — zurueckholen oder bestaetigen?** — bei
      der Blocker-Bereinigung am 14.09. wurden auf Ansage „alte Aufgaben koennen
      weg" sieben gestaute Issues abgebrochen. Zwei davon koennten inhaltlich
      noch aktuell sein: **WHI-6304** („Modell-ID in n8n Workflow aktualisieren",
      12 Tage, war `in_review`, VP Engineering) — thematisch genau der Bereich,
      an dem am selben Tag gearbeitet wurde — und **WHI-1641** („LM Studio
      Adapter auf qwen2.5-coder", 85 Tage), dessen Blocker als einziger `done`
      war, dessen Vorarbeit also fertig ist. Ein Status-Patch ist umkehrbar.
      *(2026-09-15, Chat: Mailhub und Recovery-Kaskade)*


- [ ] **★★Lessons-Schleife entschaerft — Wirkung erst ab dem Nachtlauf 02:00
      messbar** — der naechtliche „Reibungs-Sweep" (`de.whitestag.agent-learning.lessons`)
      war der **Motor** der Recovery-Halde: Er legt fuer jeden `failed`-Run des
      Vortags einen Lessons-Kandidaten an; scheiterte das Issue selbst, erzeugte
      genau dieses Scheitern neue failed-Runs, die am Folgetag wieder im
      naechsten Issue landeten. 64 solcher Issues seit dem 14.05., 18 davon offen.
      **Ursache war eine rechnerisch unloesbare Aufgabe:** je Run zwei
      API-Abrufe, Destillat, Vault-Datei und MEMORY-Update — bei
      `max_runs_per_sweep: 10` plus Context-Bundle-Sync sind das 40+
      Werkzeugaufrufe gegen `maxIterations: 12`. Die Config nimmt in ihrem
      Kommentar noch an, der Loop laufe auf `claude_local`/Sonnet; tatsaechlich
      haengt er am Online-Rechercheur auf `lmstudio_local`/qwen3.6-35b.
      **Am 11.09. geaendert:** `max_runs_per_sweep` 10 → **3**
      (`~/.paperclip/instances/default/agent-learning.config.yaml`) und
      `maxIterations` des Online-Rechercheurs 12 → **30**. 16 veraltete
      Lessons-Issues (aelter als eine Woche) abgebrochen, die zwei juengsten
      (WHI-6983, WHI-7439) bewusst als **Probelauf** auf `todo` gelassen.
      **Zu pruefen:** Laeuft der Sweep um 02:00 erstmals bis `done` durch? Wenn
      nein, ist das Iterationsbudget immer noch zu klein — dann Faustregel
      `max_runs x 5 Schritte < maxIterations` nachziehen.
      *(2026-09-11, Chat: WHITESTAG Agenten-Aufsicht)*
      **Antwort 13.09.: ja, aber teuer.** WHI-8091 („Lessons aus Reibungs-Runs
      vom 2026-09-12") steht auf `done`, abgeschlossen um 03:33. Der Weg dahin
      kostete jedoch **sechs Runs, davon vier in `max_iterations`** (Limit 30),
      und nebenbei entstand ein Recovery-Issue (WHI-8093). Die Faustregel
      `max_runs x 5 < maxIterations` waere mit 3 x 5 = 15 < 30 erfuellt und
      stimmt trotzdem nicht — der Rechercheur braucht real mehr Runden je Run.
      Passt zum Gesamtbild: er scheitert zu **49 % an `max_iterations` trotz
      Limit 30** (382 von 782 Runs, 14 Tage). Hochdrehen allein loest es nicht.
      *(2026-09-13, Chat: Selbstheilung wiederhergestellt)*

- [x] **~~Agenten kommen aus `error` nicht von selbst zurueck~~ — Ursache am
      13.09. gefunden und behoben.** Der Selbstheilungs-Pfad griff nicht, **weil
      es ihn im laufenden Stand nicht mehr gab**: Am **02.09. um 20:57** wechselte
      der Watch-Tree von `feat/vorfall-abschluss` auf `master` (reflog
      `80ce1cc55`), und der Code lag nur im Feature-Branch. Letzter Eintrag in
      `agent_self_heal_ledger`: **02.09. 20:57:11** — auf die Minute. Elf Tage
      lautlos, weil ein fehlender Waechter nichts meldet. Behoben mit
      `52875b766` (Code nach master) und `20fcb39f3` (externer launchd-Waechter
      `tools/agent-wacht/`, 15-Min-Takt, mailt bei Befund). Belegt: um 08:40 holte
      die interne Selbstheilung den CTO selbstaendig zurueck; zum Feierabend
      0 Agenten in `error`. **Merksatz:** Was nur in einem Feature-Branch lebt,
      ist nicht deployed — Gegenprobe ist der Ledger, nie die Erinnerung:
      `select max(updated_at) from agent_self_heal_ledger;`
      *(2026-09-13, Chat: Selbstheilung wiederhergestellt)*
      **★★Nachtrag 03.10.: die Rueckholung war UNVOLLSTAENDIG.** `52875b766`
      brachte die Funktionen nach master, **nicht aber ihren Aufrufort**. Das
      Quittieren des Ledgers war damit 31 Tage toter Code: `resolved_at` blieb
      leer, `attempt_count` wuchs unbegrenzt (Vault-Maintainer 77, CHO und
      Lektorat je 57). Weil die Politik `convergence` ab `attemptCount >= 1`
      dauerhaft an den Menschen eskaliert, war das eine Einbahnstrasse — nach dem
      ersten `max_iterations` bekam ein Agent fuer diesen Fingerprint nie wieder
      einen Manager-Versuch. Behoben mit `96a5c92ab`
      (`applySelfHealLedgerResolutionForRunOutcome()`, 7 Tests, Gesamtsuite 3142
      gruen); im Betrieb belegt, und um 16:56:43 feuerte erstmals wieder
      `agent.self_heal.escalated_manager`.
      **Merksatz fuer die naechste Rueckholung:** Bei „Funktion wird nicht
      aufgerufen" erst `git log -S <Name>` — ein `feat`, das sie einbaut, und ein
      spaeteres `fix`, das sie nicht mehr enthaelt, heisst **Regression bei einer
      Rueckholung**, nicht „nie fertig". Dann lohnt der Diff des Rueckhol-Commits
      gegen den Feature-Branch, Stueck fuer Stueck.
      *(2026-10-03, Chat: Tote Modell-ID)*

## WHITESTAG.ACADEMY

- [ ] **★Routine „KI-Tool-Stand aktualisieren" anlegen** — `_KI-TOOL-STAND.md` ist
      am 16.10. von Hand auf Stand gebracht, die 90-Tage-Grenze faellt also
      wieder am **14.01.2027**. Body und Trigger (`0 6 1 */2 *`, Europe/Berlin,
      Online-Rechercheur) liegen fertig in `tools/academy-tool-stand/`; angelegt
      werden konnte sie nicht, weil das Laden des Board-Tokens per
      Sicherheitspruefung verwehrt war. Per Board-UI anlegen oder Token-Zugriff
      freigeben. Bis dahin stimmt der Abschnitt „Pflege" der Datei nicht, der
      die Routine schon als zustaendig nennt. *(2026-10-17, Chat: KI-Tool-Stand Academy)*

- [ ] **Antwort an den CEO zu WHI-10094 verschicken** — Entwurf im Chatverlauf:
      Tool-Stand aktualisiert, kein eigener Auftrag noetig. Den Satz „Pflege
      laeuft kuenftig ueber eine Routine" nur mitschicken, wenn sie angelegt ist.
      *(2026-10-17, Chat: KI-Tool-Stand Academy)*

- [ ] **Offene Recherchepunkte im Tool-Stand** — (1) ob die ChatGPT-Google-
      Connectoren im EWR noch gesperrt sind (nur Drittquellen, help.openai.com
      gab 403 — in einem deutschen Plus-Konto unter Einstellungen → Apps
      nachsehen); (2) ob Claude-Gmail „Senden" schon bei allen Konten ankommt;
      (3) was „ChatGPT Work eingeschraenkt" im Free-Plan konkret heisst. Stehen
      auch in der Datei selbst. *(2026-10-17, Chat: KI-Tool-Stand Academy)*

- [ ] **Zwei ACADEMY-Auftraege ohne Ergebnis — Muster pruefen** — WHI-5016 wurde
      mit **leerer Beschreibung** angelegt; der Autor meldete daraufhin dreimal
      `No work assigned, exiting heartbeat` und das Issue lag 15 Tage auf `todo`.
      Abgebrochen, weil Thema und Slug nicht rekonstruierbar waren. Falls das
      wieder auftritt: Der CEO erzeugt den Auftrag offenbar gelegentlich ohne
      Rumpf — dann gehoert eine Mindestpruefung in die Routine.
      *(2026-09-11, Chat: WHITESTAG Agenten-Aufsicht)*

- [ ] **Sekretärin: Quoting-Fehler beim Telegram-Versand** — ihre Run-Logs zeigen
      bei jedem Aufruf von `send-walter-telegram.sh` ein
      `unexpected EOF while looking for matching`, danach trotzdem „Push OK“.
      Prüfen, ob Freigabe-Meldungen kaputt oder doppelt ankommen; Ursache
      vermutlich die Anführungszeichen „…" im HTML-Text. *(2026-10-17, Chat: Telegram-Meldungen aufräumen)*

- [ ] **Ersten Kurs nach `_KURS-SPEC.md` v5 gegenlesen** — prüfen, ob der Autor
      `langbeschreibung` (1700–2400 Zeichen, eine Zeile mit `\n\n`) liefert, ob
      `kurzbeschreibung_sie`/`langbeschreibung_sie` **wortgleich in Du-Form** gefüllt sind
      (kein Sie-Text, Felder nicht gelöscht) und ob der Import den Kurs annimmt. Dabei auch prüfen,
      ob der Lektor ein „Sie" an Lernende tatsächlich mit ROT bewertet (seit 19.10. Pflicht). *(2026-10-19, Chat: ACADEMY Kurs-Langtext)*
      **Erster Befund 19.10. (`vibe-coding-context-engineering`): Autor UND Lektor
      verfehlen die Felder.** `langbeschreibung` nur 1187 Zeichen (Import 14:36
      abgelehnt), `langbeschreibung_sie` fehlte ganz. Beides vom Board nachgetragen
      (1284 Zeichen), danach Import `created`. Die Sie-ROT-Prüfung ist weiter unbelegt. *(2026-10-19, Chat: WHITESTAG-AI Fallback-Umstellung)*

- [ ] **Ersten Kurs aus dem Ideen-Eingang gegenlesen** — WHI-10264 „Vibe Coding hat sich
      verändert“ (allgemein · fortgeschritten, Material `Workshops/_ideen/K-20261019-142206.md`,
      Quelle YouTube Niklas Steenfatt). Prüfen: Lektorat, Freigabe, setzt der CEO in
      `_ideen-eingang.md` den Status auf `gebaut (<slug>)`, und hat der Autor das Material
      genutzt, ohne abzuschreiben. Kleinigkeit: Als „in Arbeit“ trug der CEO das
      Routinen-Issue WHI-10263 ein statt des Autoren-Issues. *(2026-10-19, Chat: Kursideen per Jarvis)*
      **Stand 19.10. abends:** Kurs importiert, Status `gebaut (vibe-coding-context-engineering)`
      vom CEO gesetzt, Themen-Log eingetragen. Offen bleibt nur die Frage, ob der Autor das
      Material genutzt hat, ohne abzuschreiben. *(2026-10-19, Chat: WHITESTAG-AI Fallback-Umstellung)*

- [ ] **★Lektor meldet ROT für eine vorhandene Lektion und überliest Hinweise** —
      WHI-10267 (19.10. 17:18, Modell `google/gemma-4-31b`): „Lektion 4 fehlt", obwohl
      `## Lektion 4 — Claude 5 und die sechs Verschiebungen` in Zeile 187 steht. Die zu
      kurze `langbeschreibung` und das fehlende `langbeschreibung_sie` übersah er, obwohl
      die Länge im Board-Kommentar ausdrücklich genannt war. Prüfen: Laufprotokoll
      (`log_ref` des Runs `8f8e2402`) — hat er die Datei ganz gelesen oder nur einen
      Ausschnitt (Kontextkürzung bei 39 KB)? Für Punkt 9a/§ 8 wäre eine deterministische
      Vorprüfung (Lektionen zählen, Feldlängen messen) zuverlässiger als das Modell. *(2026-10-19, Chat: WHITESTAG-AI Fallback-Umstellung)*
      **Stand 22.10.: die deterministische Vorprüfung gibt es jetzt** — `kurs-check.mjs` (Formfehler, Feldlängen,
      Lektionszahl) läuft vor jedem Lektorat. Bei WHI-10320 übersah der Lektor erneut einen mehrzeiligen Langtext,
      den fehlenden Abschnitt `## Quellen` und ein erfundenes `datum`. Offen bleibt nur die Auswertung des
      Laufprotokolls (liest er die Datei ganz?). *(2026-10-22, Chat: ACADEMY Kurs-Formprüfung)*

- [ ] **Ersten Fortgeschrittenen-Kurs gegenlesen (Do 22.10.)** — Routine `afb99dc2`
      („Fortgeschritten (Mi–Do)“, seit 20.10. Mi+Do). Prüfen: `kurs_niveau: fortgeschritten`
      und `kurs_gruppe: grundlagen` im Frontmatter, Abschnitte `## Voraussetzungen` und
      `## Quellen` (Spec § 10 F1/F4), Sicherheitsrahmen in ausführenden Übungen (F3), ob
      der Lektor die Prüfpunkte 15–17 anwendet und ob die Kurskarte „Fortgeschritten“ mit
      zwei Balken zeigt. *(2026-10-19, Chat: Kursmix und Niveau)*
      **Stand 21.10.:** Der erste Mittwochslauf (WHI-10320) nahm noch die Einsteiger-Idee L01,
      bewusst nicht abgebrochen. Seitdem nimmt Schritt 0 an Mi/Do nur Ideen vom Typ
      `allgemein · fortgeschritten` (im Eingang gibt es gerade keine). Am 22.10. also zusätzlich
      prüfen: lässt der CEO die Einsteiger- und Branchen-Ideen `offen` liegen und beauftragt ein
      eigenes Werkzeug-Thema? *(2026-10-21, Chat: Kursmix Fortgeschrittene)*
      **Stand 22.10.:** WHI-10365 baute `ki-automatisierung-n8n` (8 Lektionen, Lektorat GELB, importiert),
      also ein eigenes Werkzeug-Thema. Formprüfung lief vor beiden Runden mit OK. Noch offen aus diesem Eintrag:
      F3-Sicherheitsrahmen in den Übungen, Prüfpunkte 15–17 beim Lektor und die Kurskarte mit zwei Balken. *(2026-10-22, Chat: ACADEMY Kurs-Formprüfung)*
      **Stand 27.10.:** Im Eingang stehen jetzt Fortgeschrittenen-Ideen (V01–V03 mit Vorrang, dazu Agentic AI) — die
      offenen Prüfpunkte gleich an den Vorrang-Kursen mitprüfen (Eintrag unten). *(2026-10-27, Chat: ACADEMY Kurse Vorrang)*

- [ ] **Ersten Kurs mit 8–10 Lektionen beobachten** — seit 19.10. verlangt Spec § 5
      8 bis 10 statt 7 Lektionen (Prüfprofil Punkt 9a, ROT). Längere Kurse heißen
      längere Läufe des Online-Rechercheurs (scheitert ohnehin oft an `max_iterations`)
      und mehr Kontext beim Lektor. Beim ersten Kurs danach prüfen: Lektionszahl,
      `**Umfang:**`-Angabe, Laufzahl und Fehlläufe des Autors gegenüber den 7er-Kursen.
      *(2026-10-19, Chat: Kursmix und Niveau)*

- [ ] **Ruft der Autor `kurs-check` selbst auf?** — seit 21.10. Pflicht in `roles/online-rechercheur.role.md`
      (vor `done`, bis OK). Im ersten Lauf (22.10., WHI-10367) ist der Aufruf nur beim CEO belegt; in den
      Run-Events des Online-Rechercheurs fand sich kein Treffer. Beim nächsten Kurs im Run-Protokoll des Autors
      (`log_ref` → ndjson, `shell_exec` mit `kurs-check.mjs`) nachsehen. *(2026-10-22, Chat: ACADEMY Kurs-Formprüfung)*

- [ ] **CEO-Mail nach dem API-Key-Fix im Echtbetrieb belegen** — seit 14.05. scheiterte jede Mail eines
      lmstudio-Agenten (CEO u. a.) an „PAPERCLIP_API_KEY nicht im Env“, Fix im Adapter `fbe4976` seit 23.10. 08:20 live.
      Nach dem nächsten Kurslauf (06:00) im `~/.paperclip/instances/default/logs/walter-deliverable.log` nach
      `SENT … agent=CEO` sehen. Kommt stattdessen ein anderer Fehler, ist das der nächste Befund. *(2026-10-23, Chat: Kurs-Import und CEO-Mail)*

- [ ] **Kfz-Kurs im Admin freigeben** — `ki-kfz-betrieb` (8 Lektionen, Lektorat GELB) liegt seit 23.10. als Entwurf
      in der Akademie. Nur Walter kann freigeben. *(2026-10-23, Chat: Kurs-Import und CEO-Mail)*

- [ ] **`is_free` bei `ki-werkzeug-auswahl` widersprüchlich** — die Kursdatei sagt `is_free: true`,
      das Themen-Log (beide Tabellen) „❌ kostenpflichtig“. Walter entscheidet, was gilt; danach Datei oder
      Log angleichen. *(2026-10-22, Chat: ACADEMY Kurs-Formprüfung)*

- [ ] **Überarbeitung veröffentlichter Kurse — Entscheidung offen** — der Import fasst
      einen einmal veröffentlichten Kurs nie wieder an (`409 already_published`,
      Import-Design vom 17.10., Entscheidung 1). Änderungen an der Vault-Datei kommen
      also nie in der App an: keine Korrekturen, kein neuer Tool-Stand, keine
      Erweiterung der alten 7er-Kurse. Bei Werkzeug-Kursen (Claude Code, Codex …)
      veraltet das schnell. Möglicher Weg: Überarbeitung als zweiter Entwurf neben dem
      veröffentlichten Kurs, Freigabe im Admin ersetzt die Lektionen, Fortschritt der
      Teilnehmer bleibt erhalten. *(2026-10-19, Chat: Kursmix und Niveau)*

- [ ] **Vorrang-Kurse n8n, Paperclip, Claude Code gegenlesen (Mi 28.–Fr 30.10.)** — `K-20261027-V01…V03`,
      fortgeschritten, **12–15 Lektionen** (Walters Vorgabe, Spec § 5 Ausnahme, Prüfprofil 9a). Prüfen: Nimmt der CEO
      die VORRANG-Zeile vor L08, setzt er `Umfang: …` unter die Kurstyp-Zeile, wertet der Lektor 12–15 nicht als ROT,
      baut der n8n-Kurs erkennbar auf `ki-automatisierung-n8n` auf? Laufzahl und `max_iterations` des Autors bei den
      langen Kursen beobachten; `skip_if_active` kann Donnerstag ausfallen lassen. *(2026-10-27, Chat: ACADEMY Kurse Vorrang)*

- [ ] **Agentic-AI-Kurs aus dem LHIND-Whitepaper gegenlesen** — Idee `K-20261026-141307` (fortgeschritten,
      Material `Workshops/_ideen/K-20261026-141307.md`), läuft nach den drei Vorrang-Kursen, voraussichtlich Mi 04.11.
      Prüfen: Material genutzt ohne Abschreiben, keine LHIND-Marken- oder Firmendarstellung, Abgrenzung zum n8n-Kurs. *(2026-10-27, Chat: ACADEMY Kurse Vorrang)*

## SEO/GEO

- [ ] **Search Console: Dienstkonto für die drei neuen Sites freigeben** — in der Search
      Console je Property (whitestag.tv, whitestag.academy, whitestag.app) unter
      *Einstellungen → Nutzer und Berechtigungen*
      `seo-geo-reader@n8n-projekte-486711.iam.gserviceaccount.com` mit „Eingeschränkt“
      hinzufügen. `gsc_property` steht schon in `sites.json`. *(2026-10-19, Chat: SEO-GEO neue Sites)*

- [ ] **★whitestag.de und virtuelle-lausitz.de liefern GSC 403** — das Dienstkonto steht dort
      nur noch als `siteUnverifiedUser`, die Audit-Mail vom 19.10. hat für beide keine
      Search-Console-Zahlen. Prüfen, ob die Property-Bestätigung verloren ging (Site Kit oder
      Bestätigungs-Tag entfernt?); notfalls über das mu-Plugin (`/gsc-verify`) neu bestätigen. *(2026-10-19, Chat: SEO-GEO neue Sites)*

- [ ] **Fünf neue Findings auf whitestag.film** — aus dem Audit vom 19.10.:
      `/projekte/lausitz-science-park/` (Meta-Description + Alt-Text) und je ein Alt-Text auf
      `/werkschau/interaktive-projekte/{virtuelle-lausitz,kinderhaus-pusteblume-interaktiv,chesco}/`.
      Changesets selbst bauen, `resolve` + `validate`, Freigabe über Telegram. *(2026-10-19, Chat: SEO-GEO neue Sites)*

- [ ] **whitestag.app: Audit scheitert bis zum Livegang** — noindex-Platzhalter ohne
      `sitemap.xml`, steht deshalb jede Woche als „Audit fehlgeschlagen“ in der Mail. Bewusst als
      Erinnerung drin; beim Livegang prüfen, dass eine Sitemap ausgeliefert wird. *(2026-10-19, Chat: SEO-GEO neue Sites)*

## Mail-Spiegel und Belege

- [ ] **V16 ist erst an einem einzigen Anhang erprobt** — der Live-Test mit der
      weitergeleiteten BIKEpoint-Rechnung belegt Rekursion und
      RFC-2047-Dekodierung. Der Fall „generischer Dateiname bekommt den Absender
      vorangestellt" (image001.png & Co.) ist **nur im Pruefstand** gruen, live
      noch nicht ausgeloest. Beobachten, wenn die naechste Mail mit Inline-Bild
      eingeht. Pruefstand: `tools/n8n-mail-mirror/`, `node mime-test.js`.
      *(2026-09-05, Chat: Routinen, Fallback und Mail-Anhänge)*

- [ ] **Wie viele Belege fehlen rueckwirkend?** — von 24 Rechnungs-Mails der
      letzten vier Wochen hatten 8 kein PDF am selben Tag. Das ist ein Hinweis,
      **kein Beweis**: bei Apple, Telekom oder „Rechnung bezahlt"-Mails haengt
      legitim nichts an. Nur ein Abgleich gegen das echte Postfach zeigt, welche
      davon der alte Spiegel verschluckt hat. Der Dubletten-Schutz ueber
      `message_id` verhindert, dass alte Mails neu verarbeitet werden — ein
      Nachziehen muesste gezielt erfolgen.
      *(2026-09-05, Chat: Routinen, Fallback und Mail-Anhänge)*

## Modelle und Agenten

- [ ] **VP Engineering auf Strata bei echter Code-Arbeit gegenlesen** — seit 23.10.
      faehrt er tagsueber `qwen3.8-flash-next-unsloth-ud-q4_k_xl` ueber Strata
      (Film-Rechner), der Umschalter `de.whitestag.strata-umschalter` stellt bei Ausfall
      auf Sonnet. Erprobt ist nur eine Lese-/Testaufgabe (WHI-10497, sauber). Bei den
      ersten Fixes pruefen: Aufrufe nicht vorhandener Werkzeuge (das Modell nennt im
      Denken Claude-Code-Tools wie „Glob“), Schleifen, inhaltliche Fehler, und ob der
      beim Probelauf verlorene `done`-PATCH wiederkehrt. Welches Modell lief, steht in
      `cost_events.model`; Wechsel im `~/.paperclip/logs/strata-umschalter.log`. *(2026-10-25, Chat: Strata für Agenten)*

- [ ] **Sechs INAKTIVE n8n-Workflows tragen die tote Modell-ID noch** — die sechs
      aktiven wurden am 04.10. korrigiert; bewusst nicht angefasst wurden
      `Dokumente Clara V5`, `Google-Alert V10`, `Paperclip Daily Digest V13`
      und `V14`, `RAG-intern Chat V3`, `RAG-intern Telegram V4`. Sie laufen nicht,
      schaden also nicht — brechen aber beim Aktivieren sofort. Wer einen davon
      scharfstellt, muss vorher `gemma-4-31b-it` → `google/gemma-4-31b` ersetzen.
      Rezept steht in `project_n8n_versioning_and_restart`; `stickyNote`-Knoten
      ueberspringen (der Daily Digest traegt die ID nur in einer Haftnotiz).
      Nachweis: `sqlite3 ~/.n8n/database.sqlite "select name, active from workflow_entity where nodes like '%gemma-4-31b-it%'"`
      *(2026-10-04, Chat: Tote Modell-ID)*

- [ ] **~~Primaermodelle stehen auf toten Eintraegen~~ — die toten IDs sind weg,
      die Fallback-Frage ist anders geloest** — am 04.10. wurden alle Fundorte von
      `gemma-4-31b-it` auf `google/gemma-4-31b` korrigiert (35 von 43 Agenten); die
      Modell-Aufsicht meldet seither `unbekannt: 0`. Das 31B liegt jetzt lokal auf
      der Studio im `resident-set` (ctx 98304), das MacBook-MLX braucht es damit
      nicht mehr — die zweimal angebotene Entscheidung ist gegenstandslos.
      **ERLEDIGT 2026-10-07:** Die Commits `27ea81930`, `ae7149875`,
      `1cb7eb080` waren **nicht die Flotte**, sondern diese Session — sie sind
      gewollt, gepusht und geprueft. Alle 37 lmstudio-Agenten haben jetzt
      Primaermodell und Fallback auf verschiedenen Geraeten (gegen die
      laufenden Instanzen geprueft: 0 Verstoesse, vorher 25). Wirksamkeit
      belegt: an einem Agenten das Primaermodell gebrochen, Lauf endete
      `succeeded` und `cost_events` bucht `gemma-4-31b-win`.
      Siehe `docs/superpowers/specs/2026-10-06-whitestag-ai-node-farm-einbindung-design.md`.
      *(2026-09-22, Chat: LLM-Farm und Netzausfall; erledigt 2026-10-04, Chat:
      Tote Modell-ID; Restfrage beantwortet 2026-10-07, Chat: WHITESTAG-AI
      Fallback-Node)*

- [ ] **★Die Sekretaerin laeuft in einem LEEREN Fallback-Workspace** — sie rief
      `luna-queue-approval.py` ueber einen selbstgebauten Pfad mit zwei UUIDs
      auf und verstuemmelte beide (35 statt 36, 32 statt 36 Zeichen), lief
      danach sechsmal gegen „Path traversal blocked" und verbrannte so ihr
      Iterationsbudget. **Die UUID-Verstuemmelung ist nur das Symptom:** In
      `roles/sekret-rin.role.md` steht der Aufruf **relativ**
      (`bin/luna-queue-approval.py`), der Agent laeuft aber laut erster Logzeile
      im Fallback-Workspace `~/.paperclip/instances/default/workspaces/<agent-id>/`
      — seit Mai angelegt und **komplett leer**, weil ihm kein Projekt-Workspace
      zugeordnet ist. Erst daraufhin konstruiert das Modell einen absoluten Pfad.
      **Pflaster am 15.09.:** Symlink `workspaces/<id>/bin → agents/<id>/bin`,
      verifiziert per `--help` (Exit 0, Importe `approval_queue` /
      `luna_mail_render` laden durch). **Offen:** (1) warum ihr kein
      Projekt-Workspace zugewiesen ist — der Symlink hilft nur im Fallback, bei
      echtem Projekt-Workspace ist das cwd wieder anders; (2) in der Praxis
      unbewiesen, sie hat das Werkzeug seither nicht aufgerufen; (3) ein
      End-to-End-Test legt eine echte Freigabe-Mail in Walters ws@-Postfach.
      **Nebenbefund:** ihre `allowedWriteRoots` sind `Vault + /tmp`, die
      `fs_*`-Werkzeuge koennen in `.paperclip` grundsaetzlich nicht schauen —
      die Suche konnte also nie klappen, egal wie korrekt der Pfad waere.
      Nur die Sekretaerin hat ueberhaupt ein `bin/`-Verzeichnis.
      *(2026-09-15, Chat: Mailhub und Recovery-Kaskade)*

- [ ] **Die beiden Obsidian-Tagger fahren verschiedene Modelle** — WHITESTAG auf
      dem lokalen `gemma-4-31b-it-mlx`, Clara auf `google/gemma-4-12b`. Bewusst
      so entschieden (zwei Nachtlaeufe kurz hintereinander auf demselben 33-GB-
      Modell waeren bei zeitweise 1,5 GB freiem RAM riskant), aber uneinheitlich.
      Wenn der RAM dauerhaft Luft hat, angleichen.
      *(2026-09-05, Chat: Routinen, Fallback und Mail-Anhänge)*
      **ID-Korrektur 19.09.: WHITESTAG faehrt jetzt `google/gemma-4-31b`** —
      dieselbe Datei (`lmstudio-community/gemma-4-31B-it-MLX-8bit`), nur der
      Identifier hat sich geaendert. Unter dem alten Namen lief der Tagger vom
      **16.–19.09. vier Naechte tot** (ok=0, fail=3/5/6/7, jede Datei HTTP 400,
      21 Notizen ungetaggt). Commit `bb8e91cbf`.
      **Das RAM-Argument ist entschaerft, nicht erledigt:** Das 31B wird nicht
      mehr dauerhaft vorgehalten, sondern vom nightly-Skript mit `--ttl 1800`
      geholt und danach freigegeben. Die 34-GB-Spitze faellt also nur noch
      waehrend des Laufs an. Ein Angleichen beider Tagger auf
      `google/gemma-4-12b` bliebe trotzdem moeglich — das steht als Alternative
      im Template-Kommentar. *(2026-09-19, Chat: Nachtfehler und Modell-Wächter)*

- [ ] **Breaker-Cooldown ist ungetestet lang** — 60 Minuten sind gesetzt, weil
      sie zu einer Renderphase passen. Ob das im Alltag zu traege oder zu hektisch
      ist, zeigt erst der Betrieb. Stellschraube: `breakerCooldownMs` in der
      Agent-Config, Zustand unter `~/.paperclip-adapter-lmstudio/breaker-state.json`.
      *(2026-09-05, Chat: Routinen, Fallback und Mail-Anhänge)*

## Netz und Standort der WHITESTAG-AI

- [ ] **★★Bad-Repeater ersetzen — er reisst die ganze Lager-Strecke mit** —
      seit **19.09., 06:57:48 Uhr** keine einzige Meldung mehr; davor eine
      Woche lang stoerungsfrei. Er war die **Bridge** fuer den Lager-Repeater:
      Belegt ueber die MAC-Adressen im FRITZ!Box-Ereignisprotokoll — die dort
      genannte MAC ist die **Basis**, bei der die Anmeldung scheiterte, und bis
      zum 19.09. war das `0C:C5:74:54:BE:4x` (Bad-Repeater-Familie), danach
      `DC:15:C8:68:B2:E2/E3` (FRITZ!Box 7590). Der Lager-Repeater hielt zwei Tage
      im Notbetrieb durch (666× „Kanalbandbreite reduziert") und gab am **21.09.
      um 22:23:49** auf; seitdem ist die **WHITESTAG-AI nicht erreichbar**
      (letzter LLM-Aufruf 21.09. 16:15:43).
      **Drei Fernversuche am 22.09. erfolglos:** Lager-Steckdose geschaltet
      (5 W Last, nichts kam zurueck), Bad-Steckdose geschaltet (Repeater wieder
      im Mesh, traegt aber **keinen IP-Verkehr** — nur ARP-Antwort bei 100 %
      Ping-Verlust), FRITZ!Box 7590 neu gestartet (10:34:48 weg, 10:35:35
      zurueck, ohne Wirkung auf die Kette).
      **Gelernt:** FRITZ-Mesh waehlt den Uplink nach **Signalstaerke**, nicht
      nach Pfadlaenge — der Bad-Repeater haengte sich nach dem Neustart des
      Buehnen-Repeaters sofort wieder an die Buehne statt an die 7590. Und das
      WLAN eines Repeaters ueber seine Weboberflaeche abzuschalten sperrt einen
      selbst aus, weil er darueber angebunden ist.
      *(2026-09-22, Chat: LLM-Farm und Netzausfall)*

- [ ] **★Die Maschine mit der ganzen Flotte haengt an einer WLAN-Kette** — die
      WHITESTAG-AI ist ueber Lager-Repeater → Bad-Repeater → FRITZ!Box 7590
      angebunden, also hinter **zwei** Funk-Hops, waehrend im Haus ein
      **10G-Switch mit acht SFP+-Ports** steht (`SL-SWTGW3C8F`, `192.168.2.2`,
      MAC `1C:2A:A3:30:61:5D`). Jeder WLAN-Hop halbiert grob den Durchsatz, und
      jedes Glied ist ein Single Point of Failure fuer 40 Agenten — heute
      eingetreten. Beim Kartentausch ist ohnehin das Gehaeuse offen: **das ist
      der Moment fuer eine Kabelanbindung oder einen anderen Standort.**
      Ausserdem fehlt der Maschine ein **Wake-on-LAN-Pfad**: Die einzige
      dokumentierte MAC (`A8:A1:59:6E:47:4B`) ist die WLAN-Schnittstelle, und
      WoWLAN traegt nach einem Stromausfall nicht. Vor Ort zu setzen: BIOS
      „Restore on AC Power Loss" auf **Power On** (die Maschine faehrt nach
      Stromausfall derzeit **nicht** von selbst hoch) und Wake-on-LAN aktivieren.
      Drittens: **Repeater und Rechner haengen an derselben Smart-Steckdose** —
      solange das so ist, laesst sich der Repeater nie allein neu starten.
      **NACHTRAG 2026-10-07: die WLAN-Kette ist nicht mehr der Pfad.** Die
      Maschine haengt per **Kabel** am Netz: `ipconfig` zeigt den
      Ethernet-Adapter auf `192.168.2.171/24` (Gateway 192.168.2.1), beide
      WLAN-Adapter stehen auf „Medium getrennt"; Ping zum Studio 2-11 ms bei
      0 % Verlust. Damit ist der Haupt-Single-Point-of-Failure aus diesem
      Eintrag weg. **Offen bleiben** BIOS „Restore on AC Power Loss" und ein
      Wake-on-LAN-Pfad ueber die KABEL-MAC (die dokumentierte
      `A8:A1:59:6E:47:4B` ist die WLAN-Schnittstelle) — beides ist jetzt
      wichtiger als vorher, weil 37 Agenten diese Maschine als Fallback
      nutzen.
      *(2026-09-22, Chat: LLM-Farm und Netzausfall; Nachtrag 2026-10-07,
      Chat: Geschwindigkeit der beiden LLMs)*

- [ ] **Beobachtung der WHITESTAG-AI auswerten, dann ueber Welle B
      entscheiden** — `tools/node-wacht/erreichbarkeit.sh` protokolliert seit
      06.10., 20:30 alle 15 Minuten nach
      `~/.paperclip/logs/node-erreichbarkeit.log`. Die erste Nacht war sauber
      (51 von 52 Punkten `connected`, der Abweicher ein Skriptfehler vor der
      Korrektur). Die Spec verlangte eigentlich **mehrere Tage** vor der
      Umstellung der 37 Agenten; umgestellt wurde nach einer Nacht, mit
      Begruendung im Spec. **Faellt der Node in den naechsten Tagen aus, ist
      Welle B (die 12 qwen-Agenten inkl. C-Suite) zurueckzunehmen** — der
      Rueckweg liegt in `tools/model-warden/fallback-ist-stand-20261006.json`.
      Pruefen mit:
      `awk -F'|' '{print $2}' ~/.paperclip/logs/node-erreichbarkeit.log | sort | uniq -c`
      *(2026-10-07, Chat: Geschwindigkeit der beiden LLMs)*
      **★Der Fall ist eingetreten (14.10.):** der Node war von ca. 09:30 bis
      15:20 weg und kam danach unter den Standard-Kennungen zurueck — die 37
      Fallbacks zeigten rund sechs Stunden ins Leere. Seit 15:23 wieder gruen.
      Umgekehrt fing der Node am 10.–12.10. den zweitaegigen RTX-Ausfall ab.
      Die Entscheidung ueber Welle B ist damit faellig, nicht mehr hypothetisch. *(2026-10-14, Chat: WHITESTAG-AI Farm-Aufsicht)*
      **19.10.: zweiter Fall gleicher Art** (Neustart → Standard-Kennungen → Fallback
      tot, diesmal ~2,5 h). Die Kennungs-Ursache ist behoben (siehe Farm-Stabilitaet),
      die Frage, warum der Node neu startet, nicht. *(2026-10-19, Chat: WHITESTAG-AI Fallback-Umstellung)*
      **Stand 21.10.: Welle B ist entschieden — andersherum.** WHITESTAG-AI ist jetzt
      PRIMAER fuer die 13 qwen-Agenten (5090, ~2x MacBook) und CMO/LLM-Analyst (3090),
      Fallback jeweils MacBook. Damit ist die Neustart-Frage wichtiger als vorher:
      jeder Neustart heisst langsamer Betrieb bis zur GUI-Zuordnung (Eintrag oben). *(2026-10-21, Chat: LLM-Farm ohne RTX)*

- [ ] **OpenSSH auf WHITESTAG-AI einrichten (optional)** — `lms load` vom Studio
      aus kann zwar per `set-preferred-device` aufs Node-Geraet zielen, verwirft
      dabei aber `-c`/`--parallel` (belegt am MacBook, 29.07.). Mit SSH liesse sich
      `start_llms.bat` von hier ausfuehren. Kurzname am PC per `whoami` holen, nicht
      raten. *(2026-10-19, Chat: WHITESTAG-AI Fallback-Umstellung)*

## Kontext-Budget und LM-Studio-Flotte

- [ ] **★★`maxPromptTokens` ist gesetzt und wirkungslos — 268 Overflows bei
      `gemma4-31b-it`** — 36 Agenten tragen `maxPromptTokens: 70000`, MAX30d
      liegt aber bei 83,8k (gemma) bzw. 97,7k (qwen). Gegenprobe in
      `heartbeat_run_events`: in **11.080 Lauf-Events der letzten 7 Tage kein
      einziges** `Kontext gekuerzt` und kein `Kontextbudget:` — der Mechanismus
      hat nie ausgeloest. Ursache im Adapter (`execute.ts`): `enforceBudget()`
      kehrt unterhalb `BUDGET_LOOKUP_THRESHOLD_TOKENS = 32_000` sofort zurueck,
      und **`tokenFactor` startet bei 1** — kalibriert wird er erst an einer
      erfolgreichen Antwort, die es beim Overflow nie gibt. `chars/4`
      unterschaetzt JSON/Shell-Ausgaben um mehr als das Doppelte, ein real 96k
      grosser Prompt wird als ~31k geschaetzt und ungekuerzt gesendet.
      **Hebel:** `tokenFactor` konservativ initialisieren (z. B. 2,5) oder die
      Schwelle am ungeschaetzten Zeichenvolumen pruefen — kostet kein VRAM.
      Das Fenster zu vergroessern hilft *nicht*: 98k deckt 98 % der Last.
      Kontrollbeweis: `qwen3.6-35b` faehrt gleiches Geraet, Fenster und Deckel
      bei hoeherem p99 (44k) und hat **1** Overflow. Haengt mit den vier
      blockierten R2-Issues bei Clara zusammen (gleiche Fehlermeldung).
      *(2026-09-07, Chat: Kontext-Bedarf und MLX-Autofit)*

- [ ] **★Die Ampel im Kontext-Bericht unterschaetzt den Bedarf** — bei
      `gemma4-31b-it` scheitern die obersten **1,83 %** der Aufrufe, der echte
      p99 liegt damit **ueber 98.304**; ausgewiesen sind **34.600** (Faktor 2,8
      zu niedrig). Grund: p99 und MAX entstehen nur aus erfolgreichen Aufrufen.
      `ctx_report.py` kennt das Problem (Kommentar in `parse_overflows`) und
      zaehlt die Overflows separat, faerbt die Zeile aber weiterhin nach dem
      geschoenten p99 — die Zeile liest sich wie „Fenster fast dreifach
      ausreichend". Vorschlag: den effektiven p99 unter Einbeziehung der
      gezaehlten Overflows ausweisen.
      *(2026-09-07, Chat: Kontext-Bedarf und MLX-Autofit)*

- [ ] **RTX-Karteileichen aufraeumen — Restpunkte** — **Stand 21.10.: die RTX ist aus
      der Farm (Walters Coding-Rechner), traegt keine Modelle mehr; Punkt (1) `n8n.sh`
      laedt aber weiter auf sie.** *(2026-10-21, Chat: LLM-Farm ohne RTX)* **Die Praemisse „arbeitslos"
      ist ueberholt (04.10.2026):** die Karte traegt jetzt `qwen3.6-35b-a3b` und
      als **Primaer-Klassifikator des PII-Proxys** `google/gemma-4-12b-qat`.
      Urspruenglich am 22.09. aufgenommen, weil kein Agent (39 geprueft), kein
      aktiver n8n-Workflow (21 geprueft) und kein Dienst auf ein Modell dort
      zeigte. Offen sind noch:
      (1) `~/Desktop/n8n.sh` laedt beim Start
      `mistral-small-3.2-24b-instruct-2506@q4_k_m` auf die RTX — **das Modell
      existiert auf keiner Maschine mehr**. *(Der Wake-Satellit ist am 04.10.
      erledigt: `CHAT_MODEL` stand auf der toten `gemma-4-31b-it` bei laufendem
      launchd-Job, jetzt `google/gemma-4-31b` — live UND im Repo-Spiegel, weil
      `waechter.py -> hole_satellit()` die REPO-Datei liest.)*;
      (2) **teilweise erledigt (04.10.2026):** `google/gemma-4-12b-qat` ist
      nicht mehr gelöscht, sondern der Primaer-Klassifikator des PII-Proxys —
      Eintrag in `resident-set.json` auf `when: always` gehoben, begruendet und
      das ctx-Soll auf die geladenen 32768 angeglichen. **Offen bleibt
      `qwen/qwen3-coder-next`:** es existiert wieder im Modellindex der Karte,
      ist aber nicht geladen und steht weiter auf `day-only` — pruefen, ob es
      noch gebraucht wird (es ist zugleich der 48,49-GB-Posten im
      Archivierungs-Eintrag unten);
      (3) **erledigt (04.10.2026):** `tools/modell-wacht/soll-laufzeit.json`
      bewertete die alten IDs `abiray/qwen3.6-35b-a3b` und `gemma4-31b-it` — beide
      auf die `lms ps`-Identifier `qwen3.6-35b-a3b` bzw. `google/gemma-4-31b`
      umbenannt, 44 Tests gruen;
      (4) **erledigt (12.10.2026):** die Modell-Aufsicht prueft jetzt alle drei
      Geraete (`bewerte_geraete`, Feld `geraet` in `soll-laufzeit.json`) und
      mailt bei harten Befunden an ws@. Der Entlade-Waerter fasst weiter nur
      `studio` an.
      Nebenwirkung der sporadisch verbundenen Karte: Die Modell-Aufsicht
      flackerte zwischen 41 und 135 Befunden und legte bei jedem Wechsel ein
      Issue an. *(2026-09-22, Chat: LLM-Farm und Netzausfall)*

- [ ] **313 GB tote Modelle auf der RTX-Platte — Archivierung entschieden, nicht
      ausfuehrbar** — `deepseek-v4.1-flash-fp8` (264,52 GB) und
      `qwen/qwen3-coder-next` (48,49 GB), beide null Aufrufe in 30 Tagen. Walter
      hat „beide aufs NAS archivieren" gewaehlt; **von der Studio aus nicht
      machbar**, weil der Filmrechner keinen Zugang bietet (SMB lehnt die
      Authentifizierung ab, SSH ist zu, WinRM offen aber ungenutzt). Der
      Transfer gehoert ohnehin direkt NAS → Filmrechner statt ueber den Mac —
      sonst laufen die Daten zweimal ueber die Leitung. Rezept: `rsync
      --partial` mit Retry, weil SMB unter Last reisst.
      **Ergaenzt 04.10.2026:** dazu kommt `strands-qwen3-vl-2b` (2,05 GB) — das
      Modell ist aus dem VRAM entladen, die Datei liegt aber weiter auf der
      Platte und steht deshalb noch in `/v1/models` (der Index listet auch nicht
      geladene Modelle). Der fehlende Zugang ist erneut belegt: `lms` hat gar
      keinen Lösch-Befehl und `192.168.2.181` hat **Port 22 zu** — im LAN
      annonciert nur die Studio `_ssh._tcp`. Alles drei nur an der Maschine
      selbst loeschbar.
      *(2026-09-22, Chat: LLM-Farm und Netzausfall; ergaenzt 2026-10-04, Chat: Strands und PII-Fallback)*

- [ ] **`gemma-4-31b-it@q8_0` auf WHITESTAG-AI ist ein 1,26-GB-Teildownload** —
      ein 31B-Modell in Q8 hat rund 33 GB. Die Leiche wuerde beim Q8-Umstieg als
      „ist ja schon da" durchgehen und beim Laden scheitern. Entweder sauber neu
      ziehen oder loeschen. *(2026-09-22, Chat: LLM-Farm und Netzausfall)*

- [ ] **★KV-Quantisierung ist die Bedingung fuer 4 Slots — und per CLI nicht
      setzbar** — `gemma-4-31b-it` mit ctx 98304 × 4 passt nur mit K- und
      V-Cache auf `q8_0` ins VRAM. Fehlt die Einstellung, faellt das Modell
      **ohne jede Fehlermeldung** von 37 tok/s auf **0,2 tok/s** (CPU-Offload)
      und 4 von 6 parallelen Anfragen laufen in den Timeout. Die Einstellung
      haengt an den Per-Modell-Defaults in der **GUI am Node**; `lms load` hat
      kein Flag dafuer. Ein Node-Neustart am 12.09. hat sie ueberstanden — das ist
      belegt, aber kein Verlass. Nach jedem Neustart einmal nachmessen statt
      annehmen. *(2026-09-12, Chat: LLM-Farm GeForce-Umzug)*

- [ ] **Preload-Skript fuer WHITESTAG-AI ist ungetestet** — `~/Desktop/n8n.sh`
      wurde am 12.09. um einen Geraete-Block erweitert (beide Flottenmodelle,
      ctx 98304 × 4, Aufwaermlauf per curl, Warnung wenn der Node fehlt).
      `bash -n` ist sauber und die Geraete-Erkennung trocken geprueft, **der
      Ladepfad selbst lief nie**. Sicherung: `n8n.sh.bak-20260912-203132`.
      Falle, die dabei entschaerft wurde: der `load`-Helper grept ungeankert —
      ohne `^…​ ` haette `gemma-4-31b-it` auf `gemma-4-31b-it-mlx` mitgematcht und
      das Laden stumm uebersprungen. Beim naechsten `n8n.sh`-Lauf ins Log sehen:
      `~/Library/Logs/*/lmstudio-preload.log`.
      *(2026-09-12, Chat: LLM-Farm GeForce-Umzug)*
      **Achtung, veraltet:** der Block laedt mit `ctx 98304 × 4` und den alten
      Namen. Seit 19.10. gilt am Node `gemma-4-31b-it`/`abiray/qwen3.6-35b-a3b` mit
      **2** Slots, und geladen wird am PC selbst per `tools/node-wacht/start_llms.bat`
      (siehe Eintrag oben). Den Block in `n8n.sh` entfernen oder angleichen. *(2026-10-14, Chat: WHITESTAG-AI Farm-Aufsicht)*

- [ ] **Erster Aufruf nach jedem Modell-Laden kostet ~2 Minuten** — beobachtet
      am 12.09.: 120 s bis 197 s beim ersten Request, danach unter 1 s. Der erste
      Agent, der nach einem Reload zugreift, laeuft damit in sein Timeout. Im
      Preload ist deshalb ein Aufwaermlauf ergaenzt; bei manuellen Ladevorgaengen
      daran denken. *(2026-09-12, Chat: LLM-Farm GeForce-Umzug)*

- [ ] **KW36-Bericht (Montag 31.08.) ist ersatzlos ausgefallen** — kein
      `ctx-report-2026-08-31.json` in `ctx-stats/state/`, in einer seit dem
      06.07. lueckenlosen Montagsserie. Der Ausfall fiel nur auf, weil der
      Trendvergleich zwei Wochen ueberspringen musste. Ursache ungeklaert;
      pruefen, ob die Routine still scheiterte oder gar nicht ausgeloest wurde.
      *(2026-09-07, Chat: Kontext-Bedarf und MLX-Autofit)*

- [ ] **MLX-Autofit: Wiedervorlage beim naechsten Engine-Update** — am 07.09.
      nachrecherchiert, weiterhin **ungeloest**: `lmstudio-bug-tracker#2250` und
      `mlx-engine#366` beide offen und unkommentiert, `lms runtime get -l
      mlx-llm` meldet 1.11.0 als neueste (auch `--channel beta`), App 0.4.22 und
      0.4.23 erwaehnen MLX-Kontext in keinem Changelog. **Der Fix existiert
      upstream** — PR #355 fuehrte am 31.07. das Feld `auto_fit_context` ein —
      ist aber nach fuenf Wochen in keinem Build. **Nicht auf die Versionsnummer
      pruefen, sondern auf das Feld:**
      `grep -rl auto_fit_context ~/.lmstudio/extensions/backends/vendor/_amphibian/app-mlx-generate-mac14-arm64@*/lib/python3.11/site-packages/mlx_engine/`
      Am 07.09. ueber @31–@34 null Treffer. Gegenrichtung beachten: Commit
      `bc4bd41` (21.08.) vergroessert das autogefittete Fenster noch.
      *(2026-09-07, Chat: Kontext-Bedarf und MLX-Autofit)*

- [ ] **★LM Studio laedt beim Start Modelle, die niemand braucht — Quelle
      unauffindbar** — in der Nacht zum 19.09. lagen `google/gemma-4-31b`
      (33,8 GB) und `qwen/qwen3.6-35b-a3b` (20,4 GB) dauerhaft im Speicher,
      **beide ohne einen einzigen Nutzer** (0 Treffer in `agents`, n8n-Nodes,
      Tagger-Templates, PII-Proxy, Wake-Satellit) und beide per MLX-Autofit auf
      262.144 Kontext. Von 128 GB waren **176 MB** frei; 48 Runs scheiterten.
      **Per JIT waren sie es nicht** — JIT-geladene Modelle tragen in
      `lms ps --json` ein `ttlMs`, diese hatten keins. Eine Autostart-Liste ist
      in `~/.lmstudio/settings.json`, `cli-pref.json`, `ui-state/` und
      `.internal/` **nicht auffindbar**; `lastLoadedModels` ist nur eine
      Historie. Vermutlich Sitzungswiederherstellung — **pruefbar nur in der
      GUI**: beide auswerfen, LM Studio neu starten, nachsehen ob sie
      wiederkommen. Relevante Schalter dort (Zahnrad → Developer):
      `jitModelTTL.ttlSeconds: 3600`, `unloadPreviousJITModelOnLoad: false`,
      `modelLoadingGuardrails.alwaysAllowLoadAnyway: true`.
      **Abgesichert ist die Lage trotzdem:** der neue Entlade-Waerter
      `ai.whitestag.model-evict` raeumt sie spaetestens nach 20 Minuten weg,
      egal wer sie laedt. *(2026-09-19, Chat: Nachtfehler und Modell-Wächter)*

- [ ] **Drei Modell-Entscheidungen offen (Rueckfragen vom 19.09. unbeantwortet)** —
      (1) Die lokale MLX-Kopie `qwen/qwen3.6-35b-a3b` (**20,4 GB**) hat null
      Referenzen; das Pendant laeuft auf WHITESTAG-AI. Platte freigeben oder
      nur nicht mehr laden? (2) `qwen/qwen3-32b` und `qwen3-32b-dwq` (je
      **18,5 GB**) liegen ungeladen und ohne Referenz — Kandidaten fuers
      NAS-Archiv, vgl. `project_lmstudio_model_archive`. (3) Die **12 Agenten
      mit Primaer `qwen3.6-35b-a3b`** haben als Fallback `gemma-4-31b-it` —
      ein anderes Modell, aber **auf demselben Node**. Faellt LM Link aus (in
      der Nacht 693 `peer_keepalive_timeout`), faellt beides aus. Die 25
      gemma-Agenten wurden am 19.09. auf das lokale `google/gemma-4-12b`
      umgestellt; fuer die 12 steht die Entscheidung aus.
      **(3) erledigt 21.10.:** alle Fallbacks liegen auf einem anderen Geraet als das
      Primaermodell (Agenten-Audit 0 Verstoesse). *(2026-10-21, Chat: LLM-Farm ohne RTX)*
      **Falle bei (1)/(2):** `lms ls` zeigt bei `qwen/qwen3.6-35b-a3b` einen
      Namen, der **nicht** als Ladeschluessel taugt (`lms load` → „Model not
      found"). *(2026-09-19, Chat: Nachtfehler und Modell-Wächter)*

- [ ] **Entprellung im Error-Handler V8 ist im Feld unbewiesen** — die Logik ist
      per Unit-Test mit dem echten Fehlerobjekt aus WHI-9017 belegt und der
      Normalpfad end-to-end (3 Fehler → 3 Issues), **der Sammel-Pfad aber
      nicht**: Seit dem Deploy um 09:12 kam kein echter IMAP-Abbruch mehr.
      Kuenstlich nicht ausloesbar — n8n verpackt selbst geworfene Fehler anders
      (`err.name` wird zu `Error`, die `description` ueberschrieben), der
      IMAP-Text kommt am Error-Trigger gar nicht an. **Beim naechsten echten
      Abbruch gegenlesen:** Es darf hoechstens **eine** Issue je Workflow und
      Tag entstehen, Titel `n8n-Fehler: <Workflow> — IMAP-Verbindungsabbrueche
      — <Datum>`. Pruefen mit:
      `select title, count(*) from issues where title like '%IMAP-Verbindungsabbrueche%' group by 1;`
      *(2026-09-19, Chat: Nachtfehler und Modell-Wächter)*

- [ ] **model-evict: Zehn-Minuten-Takt noch unbeobachtet** — der Job
      `ai.whitestag.model-evict` wurde am 19.09. um 09:58 per `bootstrap`
      gestartet (Exit 0, ein sauberer Lauf im Log), der **erste Lauf aus dem
      `StartInterval` fiel aber noch nicht**. Beim naechsten Blick pruefen, ob
      regelmaessig Eintraege dazukommen:
      `grep -c "model-evict:" ~/.paperclip/logs/model-evict.log`
      *(2026-09-19, Chat: Nachtfehler und Modell-Wächter)*

## Kontaktrecherche-Agent (Clara Sound, R9)

**Stand 25.10.: Die Recherche wandert in den Booker** (Walters Entscheidung,
Spec `WHITESTAG Booker/docs/superpowers/specs/2026-10-25-recherche-im-booker-design.md`,
Umsetzung läuft in einer Booker-Session). R9 ist angehalten
(`heartbeat.enabled=false`, `wakeOnDemand=false`).

- [ ] **R9 stilllegen, CLAA-3376 schließen** — sobald die Recherche im Booker
      läuft. CLAA-3376 (Probelauf) steht `blocked`: R9 baute den Login selbst
      (`booker.clara.ai`, Feld `username` → `400 invalid`) trotz wörtlichem
      Rezept in seiner AGENTS.md. Danach Konto `agent-recherche@booker.local`
      prüfen — wird es noch gebraucht? *(2026-10-25, Chat: Recherche-Agent Booker)*

- [ ] **★Claras Passwort aus der Mail „Aufgabenbooker" (14.10.) — Hinweis
      schicken, Fundstellen ungeschwärzt** — Text für Clara steht im Chatverlauf
      (Walter schickt ihn). Das Passwort steht im Klartext in **20 Lauf-Logs**
      (seit 14.10., Clara-Agenten), **16 Zeilen `heartbeat_runs`** und **2
      Kommentaren an CLAA-3376**; Schwärzung am 25.10. bewusst nicht beauftragt.
      Ursache bleibt: Die Mail liegt in `Clara-Vault/E-Mails/` und wird von den
      Agenten gelesen. Werte nie in Protokolle übernehmen. *(2026-10-25, Chat: Recherche-Agent Booker)*

- [ ] **★Recovery-Owner darf Zugangsdateien überschreiben** — die Büroleitung
      schrieb als Recovery-Owner von CLAA-3376 per `shell_exec cat <<EOF >`
      ein Passwort aus einer Mail in `~/.booker-agent.env` (`fs_write_file` war
      gesperrt, die Shell nicht). Eine Regel in ihrer AGENTS.md („keine
      Zugangsdateien schreiben, Credential-Probleme an Walter") wurde am 25.10.
      nicht beauftragt — zu entscheiden. Gedächtnis:
      `project_recovery_agent_ueberschreibt_zugangsdaten`. *(2026-10-25, Chat: Recherche-Agent Booker)*

- [ ] **Fehlerklasse „wörtlich richtig, inhaltlich falsch"** — bei
      `meinbezirk.at` steht jetzt `info@rtr.at` im Bestand: die österreichische
      Regulierungsbehörde, die im Impressum als Aufsicht genannt ist. Wörtlich
      korrekt, nur nicht der Ansprechpartner. Die eiserne Regel verhindert
      **erfundene** Adressen, nicht **kontextuell falsche**, und weil nur eine
      Adresse auf der Seite stand, greift auch die Mehrdeutigkeitsprüfung nicht.
      Ob eine Ausschlussliste (Aufsichtsbehörden, Hoster, CMS-Agenturen) lohnt,
      an den Zahlen der großen Charge entscheiden.
      *(2026-09-11, Chat: Vorlauf Kontaktrecherche)*
      **Stand 25.10.:** Stichprobe bestätigt die Klasse (5 von 37). Ausschlussliste
      für Registrare/Hoster/`noreply`/`datenschutz`/`widerspruch` gebaut
      (`unsuitable-address.ts`), 17 Funde zurückgenommen; Aufsichtsbehörden wie
      `rtr.at` sind NICHT abgedeckt. Der Rest geht in den Nachprüfmodus der
      Booker-Spec (Modell prüft Zugehörigkeit). *(2026-10-25, Chat: Recherche-Agent Booker)*

- [ ] **Vorrangregel bei mehreren Adressen — bewusst nicht gebaut** — mit rund
      einem Drittel die größte Restgruppe, oft nur `info@` plus `datenschutz@`.
      Eine Rangfolge nach Rolle wäre deterministisch und würde einen guten Teil
      davon lösen; das Auftragsdokument weist die Auswahl unter mehreren
      Adressen aber ausdrücklich dem Agenten zu. Entscheidung vertagt, bis die
      Charge zeigt, wie groß der Anteil wirklich ist.
      *(2026-09-11, Chat: Vorlauf Kontaktrecherche)*
      **Stand 25.10.:** 1.160 mehrdeutige Reste. Teilweise gelöst: Ist die
      zweite Adresse `datenschutz@` o.ä., fällt sie per Ausschlussregel weg.
      Den Rest entscheidet künftig das Modell im Booker (Auswahl per Nummer,
      siehe Spec). *(2026-10-25, Chat: Recherche-Agent Booker)*

- [ ] **Die Instruktion des R9 ist nirgends versioniert** — der Agent steht
      **nicht** in `tools/agents-instructions/agents-manifest.json`, seine
      `AGENTS.md` existiert nur unter
      `~/.paperclip/instances/default/companies/0e426844…/agents/cd2a58ce…/instructions/`.
      Das ist einerseits gut (der nächtliche Generator überschreibt sie nicht,
      anders als bei der Sekretärin), andererseits gibt es keine Sicherung und
      keine Historie. Am 11.09. wurde dort die falsche Formular-Anweisung
      korrigiert — diese Änderung existiert genau einmal auf der Platte.
      *(2026-09-11, Chat: Vorlauf Kontaktrecherche)*

- [ ] **Ergebnis-Pruefer bauen (zweistufig)** — sobald echte Funde vorliegen.
      **Stufe 1 deterministisch:** Fundstelle abrufen, gemeldete Adresse als
      Zeichenkette suchen — steht sie nicht drin, ist es ein Fehltreffer. Das
      laeuft ueber *alle* Ergebnisse, kostet nichts und kann selbst nicht
      halluzinieren.
      **Stand 11.09.: als Einweg-Skript erprobt** (12 von 12 Adressen belegt),
      als dauerhaftes Werkzeug noch nicht gebaut. **Eine Falle dabei, die Stufe 1
      sonst unbrauchbar macht:** Vor dem Vergleich **HTML-Entities auflösen**.
      `artup.mannheim.de` liefert die Adresse als `&#x6b;&#x75;&#x6c;…`; ein
      `grep` über den Rohtext meldet dort einen Fehltreffer, wo keiner ist —
      und genau dieser Alarm gilt als Abbruchkriterium. **Stufe 2 mit Opus**, nur fuer die Reste: JS-gerenderte
      Seiten, Impressen in Bild/PDF und die Frage, ob von mehreren Adressen die
      *richtige* gewaehlt wurde. Wichtig beim Zuschnitt: Die Frage an Opus muss
      „steht diese Adresse in diesem Text?" lauten, nicht „ist das die richtige
      Adresse fuer X?" — die zweite Form laedt zum Plausibilisieren ein, also
      genau zu dem Fehler, den wir suchen. Nebennutzen: Opus einmal dieselben 50
      Zeilen bearbeiten lassen zeigt Gemmas **Treffer**quote im Vergleich, nicht
      nur seine Fehlerquote. *(2026-09-06, Chat: Kontaktrecherche-Agent Clara)*

- [ ] **Push im Booker-Repo** — `f5914e1` (Ausschlussregel + Rücknahme) und
      `cf1eb40` (Spec) liegen lokal auf `main`, dazu Commits der parallelen
      Booker-Session. Push ist Ansage-pflichtig. *(2026-10-25, Chat: Recherche-Agent Booker)*

- [ ] **Vier blockierte R2-Issues bei Clara** — „Akquise & Booking" haengt seit
      dem 03.09. mit `R2 Taegliche Akquise-Pflege`, `R2 Woechentliche
      Akquise-Welle`, `R2 Monatlicher Akquise-Report` und einem Tour-Routing-
      Subtask. Ursache ist **Kontextueberlauf** (`Context size has been
      exceeded`, danach `max_iterations`), nicht Fachliches — der Monatsreport
      zieht KPIs ueber die ganze Akquise-Datenbank in ein Fenster. Die
      Bueroleitung hat dreimal erfolglos auf `todo` zurueckgesetzt; blosses
      Zuruecksetzen hilft also nicht. Hebel waere, die KPI-Sammlung inkrementell
      zu machen. *(2026-09-06, Chat: Kontaktrecherche-Agent Clara)*

- [ ] **Entscheidungsqualitaet des Triage-Gates von Hand gegenpruefen, dann
      scharfschalten** — `tools/issue-triage-gate` (Commit `11ab3c1c8`) liest
      Option-Logprobs eines lokalen Modells und entscheidet typisiert mit
      Konfidenzschwelle: darueber automatisch, darunter an einen Menschen mit
      sichtbarer Neigung. Gemessen an 40 `blocked`-Issues gegen
      `google/gemma-4-12b-qat`: Schwelle 0,90 laesst **33 von 40** automatisch
      laufen, 0,95 laesst 28 von 40; Latenz median 120 ms; Masse auf erlaubten
      Optionen 1,000; **stabil** (40 Issues zweimal gelaufen, 0 Entscheidungen
      gekippt). **Was fehlt, ist der Qualitaetsnachweis** — es gibt keine
      gelabelten Faelle, belegt ist nur, dass das Verfahren traegt und klare von
      unklaren Faellen trennt, **nicht dass es richtig entscheidet**. Rezept:
      `python3 triage.py --limit 40` liefert genau die Liste fuer eine
      Handstichprobe; stimmen die Zuordnungen, kann das Gate an die
      Halden-Bereinigung (Eintrag im Abschnitt „Recovery-Mechanismus"). Es ist
      bewusst **nicht scharfgeschaltet**: kein launchd-Job, keine Spiegelung
      nach `~/.paperclip/`, `triage.py` schreibt nichts.
      **Fallen stehen im README** — ohne `reasoning_effort: "none"` liefert
      LM Studio gar keine Logprobs, und ein Cache-Busting-Zeitstempel im Zustand
      verschiebt die Konfidenz (0,82 → 0,89) genug, um an der Schwelle zu kippen.
      Hintergrund der Entscheidung gegen zugekaufte Modelle (Jev/TypeSafe:
      gehostet, geschlossen, dokumentierte Prompt-Injection) steht im Chatverlauf.
      *(2026-10-05, Chat: Strands und PII-Fallback)*

## Aufraeum-Rezept (fuer die naechste Runde)

- [ ] **Vor jeder Massenfreigabe pruefen** — `~/.lmstudio/bin/lms ps` (Modelle
      geladen?) **und** die Fehlerquote der letzten Stunde. Ueber ~30 % nicht
      freigeben. Am 02.09. wurde diese Regel verletzt und erzeugte aus 69
      Freigaben binnen zwei Stunden 24 neue Zirkel.
      *(2026-09-02, Chat: Paperclip Issue-Bereinigung)*

- [ ] **★★Die Drosselung gehoert an die LLM-Slots, nicht an die Run-Zahl** —
      `maxConcurrentRuns: 1` ist bei allen 27 Agenten gesetzt (verschachtelt
      unter `heartbeat`, **nicht** auf oberster Ebene von `runtime_config` — wer
      dort nachsieht, haelt es faelschlich fuer ungesetzt). Es schuetzt gegen
      Run-**Stuerme**, aber **nicht** gegen Slot-**Erschoepfung**: bei 27 Agenten
      koennen 27 parallele Runs auf ~12–16 geladene Slots treffen.
      **Gemessen am 09. vs. 11.09., gleiche Aufgabe:**
      Wellen zu **8** bei Schwelle 4 → Runs pendelten bei 8–10, `llm_error`
      (`fetch failed`) sprang von 0 auf **69/Tag**, Erfolgsquote fiel von 78 %
      auf **39 %**, und sie blieb zwei Tage unten. Drei Agenten fielen dabei in
      `error`.
      Wellen zu **4** bei Schwelle 6 → Runs blieben bei 3–6, **1** `llm_error`
      am ganzen Tag, dieselbe Menge Arbeit sauber abgeraeumt.
      **Rezept:** Wellen zu 4, erst nachlegen wenn < 6 Runs laufen, und als
      zweite Bremse die `llm_error` der letzten 10 Minuten mitpruefen (bei ≥ 3
      weiter warten). Schwelle 3 ist zu streng — der Lauf wartet dann fast nur
      noch. *(2026-09-11, Chat: WHITESTAG Agenten-Aufsicht)*
      **Ausreisser gefunden 19.09.: der SEO/GEO-Spezialist hat
      `maxConcurrentRuns: 20`**, nicht 1 — die Aussage „bei allen 27 Agenten
      gesetzt" stimmt also nicht mehr (oder stimmte nie fuer diesen Agenten).
      Steht in `runtime_config.heartbeat`. Nicht angefasst, weil ungeprueft ist,
      ob das eine bewusste Entscheidung war. Nachweis:
      `select name, runtime_config->'heartbeat'->>'maxConcurrentRuns' from agents order by 2 desc nulls last;`
      *(2026-09-19, Chat: Nachtfehler und Modell-Wächter)*

- [ ] **Beim Massen-Cancel niemals `comment` mitschicken** — weckt den Assignee
      trotz `status: cancelled` (436 Issues = 339 unnoetige Runs). Begruendung
      bei Bedarf vorher per `POST /issues/{id}/comments` setzen.
      *(2026-09-02, Chat: Paperclip Issue-Bereinigung)*
      **Gilt fuer JEDEN Status, nicht nur `cancelled`** — am 06.09. wurde ein
      Issue mit `status: backlog` **plus** `comment` geparkt; der Kommentar weckte
      den Agenten, der daraufhin brav bestaetigte und den Status selbst auf
      `blocked` setzte. Das Parken war damit sofort wieder aufgehoben. Ohne
      `comment` haelt es. *(2026-09-06, Chat: Kontaktrecherche-Agent Clara)*

## Berichte und Mails

- [ ] **Arbeitszeit-Mail: ersten automatischen Lauf prüfen** — launchd
      `de.whitestag.claude-arbeitszeit` feuert erstmals am 27.10. um 07:00. In
      `/tmp/claude-arbeitszeit.log` muss `mailhub 200` stehen; dabei prüfen, ob die
      Farblegende in Walters Mailprogramm erscheint. *(2026-10-26, Chat: Claude-Code Arbeitszeit-Mail)*

- [ ] **Arbeitszeit-Mail misst nur den Mac Studio** — Sitzungen auf MacBook und
      Windows-Rechner liefern keine Stunden (nur ihre Vault-Chats zählen). Optional deren
      `~/.claude/projects/` per `--quelle` einlesen. *(2026-10-26, Chat: Claude-Code Arbeitszeit-Mail)*

## Zeitplan und Lastverteilung

- [ ] **Wirkung der Entzerrung gegenmessen — fruehestens 25.09.** — am 11.09.
      wurden 11 Jobs verschoben, damit nachts nie zwei I/O-Schwergewichte
      gleichzeitig laufen (`ssd-backup` 18 min und `vault-nas-sync` 34 min ueber
      SMB haben jetzt eigene Fenster) und der Acht-Job-Pulk auf 08:00 auf
      95 Minuten gestreckt ist. **Ob das wirkt, ist noch nicht belegt** —
      gemessen wurde nur der Zustand davor. Gegenprobe nach zwei vollen Wochen:
      dieselbe Parallelitaets-Abfrage fahren und die SMB-/`fetch failed`-Fehler
      im Nachtfenster (02–06 Uhr) davor/danach vergleichen. Vergleichswerte vom
      11.09.: Ø parallel 02h=1,5 · 04h=1,1 · 05h=0,6 · 08h=1,6 · 10h=2,8.
      Der Fahrplan aller drei Systeme steht als Uebersicht unter
      `https://claude.ai/code/artifact/e1181fb5-4990-4e19-a6c3-0f20efdabd93`.
      *(2026-09-11, Chat: Routinen-Lastverteilung)*

- [ ] **★Die Abendspitze 17–21 Uhr ist ungeklaert** — die hoechste gemessene
      Gleichzeitigkeit der ganzen Flotte liegt **nicht** morgens oder nachts,
      sondern abends: max **29** parallele Runs um 17:00, danach 22 / 21 / 18 in
      den Folgestunden, gegen einen Tagesschnitt von 1–3. In diesem Fenster ist
      **keine einzige Routine** geplant (nach 16:00 feuert regulaer nur der
      n8n-Digest um 18:00). Die Spitze entsteht also vollstaendig aus Folgelast
      oder aus einem Ereignis, das nicht im Fahrplan steht. Solange die Ursache
      unbekannt ist, kann man abends nichts gefahrlos dazulegen. Einstieg:
      `select date_trunc('hour', started_at at time zone 'Europe/Berlin'), invocation_source, agent_id, count(*) from heartbeat_runs where started_at > now() - interval '14 days' and extract(hour from started_at at time zone 'Europe/Berlin') between 17 and 21 group by 1,2,3 order by 4 desc limit 20;`
      *(2026-09-11, Chat: Routinen-Lastverteilung)*

## Repo-Stand und Deploy

- [ ] **Heartbeat-Fix als Upstream-PR anbieten?** — der Fehler (`activeRunExecutions`
      je Service-Instanz → falsches „Process lost" bei Adaptern ohne Kindprozess)
      steckt im Upstream-Code. Branch `fix/heartbeat-active-runs-prozessweit`
      liegt im Fork. Fuer einen PR gilt die Regel aus dem Eintrag oben: von
      `origin/master` abzweigen, `git rev-list --count origin/master..HEAD`
      einstellig. Walters Entscheidung. *(2026-10-14, Chat: Agentenausfälle und Ursachen)*

- [ ] **★★Der Dev-Server laeuft im Watch-Modus und laedt trotzdem NICHT nach** —
      am 15.09. gemessen: `server/src/services/recovery/service.ts` um 09:39:05
      geaendert, der Serverprozess lief unveraendert **seit dem 13.09. 08:40**
      weiter. Das Kommando ist `pnpm dev` → `dev-runner.ts watch`, der Watcher
      ist also da — auf dem **SynologyDrive-CloudStorage-Mount** kommen die
      Dateisystem-Events aber offenbar nicht durch. **Folge: Ein Commit allein
      ist hier kein Deploy.** Ohne `launchctl kickstart -k gui/$UID/ing.paperclip.dev`
      waere der Recovery-Fix committet, gepusht und wirkungslos gewesen — genau
      die Klasse Fehler, die die Selbstheilung elf Tage lautlos abgeschaltet hat.
      **Merksatz:** nach jeder Serveraenderung die Prozess-Startzeit gegen die
      mtime der Datei pruefen (`ps -o lstart= -p <pid>` vs. `stat -f %Sm`), nicht
      auf den Watcher vertrauen. Zu klaeren, ob sich das per Polling-Watcher
      (`CHOKIDAR_USEPOLLING`) beheben laesst — sonst bleibt der Neustart Pflicht.
      **Nebenbefund:** Beim Neustart gehen laufende Runs als `process_lost`
      verloren (zwei am 15.09.); sie werden automatisch neu gestartet, aber ein
      Wartefenster auf `running = 0` ist die freundlichere Variante.
      *(2026-09-15, Chat: Mailhub und Recovery-Kaskade)*
      **★Stand 13.10. — das hat sich gedreht:** seit „Claude Code MAC" in Synology
      angeheftet ist (10.10.), kommen die Events durch. Kopieren nach
      `opensource/paperclip-adapter-lmstudio` loeste zwei Neustart-Wellen aus,
      4 Runs `process_lost`. Vor Deploys in den Cloud-Ordner jetzt `running = 0`
      abwarten und danach betroffene Agenten per `resume` zurueckholen. *(2026-10-14, Chat: Agentenausfälle und Ursachen)*

- [ ] **★★`tools/` hinkt der Live-Fassung hinterher — nicht umgekehrt** — in
      **allen acht** geprüften Dateien ist `~/.paperclip/scripts/` führend. Am
      deutlichsten `backup-waechter/waechter.py`: live **534** Zeilen, Repo
      **357**. Live enthält SSD-Sicherung, System-Secrets, NAS-Projektordner und
      ein eigenes n8n-Schlagwort („Seit 04.09.2026"). Ebenso `sekretaerin-mail-watcher`
      (5 Dateien, +12 bis +65 Zeilen) sowie `bild-service/config.py` und
      `engineering-report/engineering_report.py`, wo live die API-URL per
      Umgebungsvariable konfigurierbar ist statt hartkodiert.
      **Achtung: Ein Deploy aus dem Repo würde laufende Dienste zurückwerfen.**
      Die mtime des Repos ist irreführend (02.09. wirkt neuer, ist inhaltlich
      aber älter) — nur der Inhalt zählt. Richtung ist also *live → Repo*
      zurückspielen, Datei für Datei geprüft.
      Nachweis: `diff -rq ~/.paperclip/scripts tools | grep differ`
      *(2026-09-05, Chat: Release-Kette repariert)*
      **Gegenprobe 07.09.: 211 inhaltlich abweichende Dateien** (der Zaehler
      enthaelt auch `__pycache__`/`.pytest_cache`-Rauschen — die acht bekannten
      Quelldateien stehen unveraendert darunter). Nichts verschlechtert, aber
      auch nichts aufgeholt. *(2026-09-07, Chat: Kontext-Bedarf und MLX-Autofit)*
      **Gegenprobe 11.09.: der Hauptfall ist erledigt** — `waechter.py` steht
      live wie im Repo bei **534** Zeilen (nachgezogen mit `4bea151c7`
      „ops(tools): Live-Staende der Betriebsskripte ins Repo nachziehen").
      Offen sind noch **4 echte Quelldateien**, alle unter `seo-geo/`
      (`cli.py`, `seo_approvals.py` und die zwei zugehoerigen Tests). Der
      Restzaehler von 160 besteht fast vollstaendig aus `seo-geo/venv/` — ein
      virtuelles Environment, das ueberhaupt nicht ins Repo gehoert und den
      Nachweis-Befehl unbrauchbar macht. Filter dazunehmen:
      `diff -rq ~/.paperclip/scripts tools | grep differ | grep -vE '__pycache__|venv/'`
      *(2026-09-11, Chat: Vorlauf Kontaktrecherche)*
      **Korrektur 11.09. abends: es sind 21 Quelldateien, nicht 4** — der Filter
      muss `pytest_cache` mit ausschliessen, sonst bleibt Rauschen drin. Neben
      `seo-geo/` (4) betroffen: **`voice-echo-bot/` (10)**, `wake-satellite/` (4)
      und `websuche/` (3). Beim voice-echo-bot ist Drift allerdings **erwartbar**
      — er hat ein eigenes Repo und sein Deploy schliesst `test_*.py` aus; dort
      also nicht blind nachziehen, sondern erst die Richtung pruefen.
      Vollstaendiger Nachweis-Befehl:
      `diff -rq ~/.paperclip/scripts tools | grep differ | grep -vE '__pycache__|venv/|pytest_cache'`
      *(2026-09-11, Chat: WHITESTAG Agenten-Aufsicht)*
      **Konkreter Fall 06.10., Richtung bestaetigt:** In
      `wake-satellite/sat_config.py` gilt **live** `FOLLOWUP_START_FENSTER_SEC = 5.0`
      plus `ANREDE_START_FENSTER_SEC = 8.0` und `MIN_START_RUN_FRAMES`, im Repo
      steht noch `FOLLOWUP_WINDOW_SEC = 2.5`. **Ein Deploy aus dem Repo wuerde die
      Nachfrage-Fenster zurueckdrehen** — genau die Gefahr dieses Eintrags, nur in
      der anderen Richtung als der Repo-Kommentar vom 04.09. annimmt. Am 04.10.
      wurde dort **ausschliesslich** `CHAT_MODEL` angeglichen (die Modell-Aufsicht
      liest diese Repo-Datei), die Fenster-Drift blieb bewusst stehen: welches
      Verhalten gewollt ist, weiss nur Walter.
      *(2026-10-06, Chat: Tote Modell-ID)*
      **Stand 18.10.: `voice-echo-bot/` ist wieder deckungsgleich** — live war in allen
      Dateien führend, das Repo wurde komplett nachgezogen (Commit `5563226ed`).
      `diff -rq` zeigt dort nur noch `DEPLOY.md` und die plist, die nur im Repo liegen. *(2026-10-19, Chat: Kursideen per Jarvis)*
      **Stand 19.10.: `seo-geo/` ist wieder deckungsgleich** — Stand aus `feat/vorfall-abschluss`
      (`4d5510afa`, Telegram-Freigabe) auf `fix/backup-leere-ref-ordner` übernommen, Commit
      `a4fd769c9`, 136 Tests grün. Auf **master** fehlt er weiterhin. Offen in diesem Eintrag
      bleiben `wake-satellite/` und `websuche/`. *(2026-10-19, Chat: SEO-GEO neue Sites)*

- [ ] **★★Vor jedem lmstudio-Adapter-Build gegen `origin/main` abgleichen** — der Cloud-Ordner
      `opensource/paperclip-adapter-lmstudio` hatte den Header-Fix `e8b772a` nur als `dist/`, nie als Quellcode.
      Ein Build am 23.10. überschrieb ihn live (15 Minuten, ohne Folgen). Pflicht vor `npm run build`:
      `git fetch && git log HEAD..origin/main` muss leer sein. Dauerhaft wäre ein Hinweis in der README des
      Adapters oder ein `prebuild`-Check, der bei Rückstand abbricht. *(2026-10-23, Chat: Kurs-Import und CEO-Mail)*

- [ ] **`test_llm` im Jarvis-Bot ist veraltet** —
      `test_module_default_fallback_avoids_the_primary_model` erwartet ein vom
      Primärmodell verschiedenes Fallback. Seit 04.09. ist beides absichtlich
      `google/gemma-4-12b` (Kommentar in `llm.py`). Den Test an die Absicht anpassen,
      dann ist die Suite wieder komplett grün (heute 260 grün, 1 rot). *(2026-10-19, Chat: Kursideen per Jarvis)*

- [ ] **7 uncommittete Dateien im Worktree `agent-learning-tree`** — liegt unter
      `~/.paperclip/scripts/agent-learning-tree`, Branch
      `feat/health-insights-company`, Änderungen von Mai/Juni 2026 (22 Zeilen:
      2 brain-launchd-plists, `agent-learning-trigger.sh`, `lib/decay.sh`,
      3 Templates/Tests). Der Worktree war als Git-Worktree unbrauchbar und
      wurde am 05.09. mit `git worktree repair` wieder angebunden — die Dateien
      sind also jetzt erst wieder sichtbar. Zu klären: committen, verwerfen oder
      Worktree auflösen. Der Branch selbst ist auf `hetzner` gesichert und
      enthält 10+ Commits, die nicht in master sind.
      *(2026-09-05, Chat: Release-Kette repariert)*

- [ ] **★★Zwei Upstream-Fixes neu aufsetzen — von `origin/master`, nicht von
      `master`** — die PRs #12827 (Test-Mock-Fix: `broadcastBeforeAdapterExecute`
      in den plugin-env-Heartbeat-Mocks) und #12732 (Heartbeat: Continuation nach
      erschoepften transient-upstream-Retries blocken) enthielten je eine echte,
      gewollte Aenderung. Beide wurden am 12.09. **geschlossen**, weil sie
      versehentlich den kompletten Fork-Stand mitschleppten (723 bzw. 605
      Dateien, zusammen ueber 315k Zeilen) statt des jeweiligen Ein-Datei-Fixes.
      Die Fixes liegen damit nicht mehr im Upstream und muessen als **saubere
      Ein-Commit-Branches von `origin/master`** neu eroeffnet werden.
      **Ursache und Vermeidung:** #12827 war direkt vom eigenen `master`
      eroeffnet, #12732 von einem Branch, der von `master` abgezweigt war. Fuer
      Cherry-Picks gilt „nie von `origin/master` abzweigen" — **fuer Upstream-PRs
      gilt das Umgekehrte.** Vor jedem `gh pr create` gegenpruefen:
      `git rev-list --count origin/master..HEAD` muss einstellig sein.
      **Mail-Falle im Schlepptau:** Ein PR mit Head-Branch `master` wird durch
      jeden Push auf `master` aktualisiert — auch durch reine `docs(todo)`-
      Commits — und erzeugt bei Rot jedes Mal eine GitHub-Fehlermail. Kommen
      unerklaerliche Actions-Mails aus `paperclipai/paperclip`, ist das die erste
      Spur: `gh pr list --repo paperclipai/paperclip --author whitestagai
      --state open` und den `changedFiles`-Umfang pruefen; ein dreistelliger Wert
      ist der Befund. *(2026-09-12, Chat: GitHub-Fehlermails Upstream-PRs)*

- [ ] **Migrationsplan ist untracked** — `docs/superpowers/plans/2026-09-11-llm-farm-umzug-geforce-node.md`
      liegt uncommittet im Repo (ebenso `docs/superpowers/HANDOFF-upstream-rueckkehr-2026-08-22.md`).
      Beim Committen gleich vermerken, dass **Task 0 uebersprungen** wurde: der
      einwoechige Probelauf auf der Pro 6000 entfiel, es wurde direkt umgestellt.
      Hat funktioniert, aendert aber die Voraussetzung der spaeteren Aufgaben.
      *(2026-09-12, Chat: LLM-Farm GeForce-Umzug)*

- [ ] **DeepSeek V4 Flash liegt ungenutzt auf der Pro 6000** — 156,38 GB MXFP4.
      Laeuft dort nicht: `lms load --estimate-only` meldet **145,64 GiB**
      GPU-Bedarf bei 96 GB Karte, und die Metadaten melden
      `trainedForToolUse: false` — fuer einen Paperclip-Agenten damit doppelt
      disqualifiziert. Entweder loeschen (Plattenplatz) oder bewusst behalten.
      Empfohlener Ersatz als Coding-Modell: `qwen3-coder-next` (80B MoE, ~40 GB
      bei Q4, SWE-bench Pass@5 64,6 %), lag bis zum 21.08. schon auf der Karte.
      *(2026-09-12, Chat: LLM-Farm GeForce-Umzug)*

- [ ] **`drizzle-orm@^0.38.4` in `packages/brain` hat eine High-Advisory** —
      GHSA-gpj5-g38j-94v9 (SQL-Injection ueber unzureichend escapte
      Identifier). Aufgefallen, weil die Dependency Review des Upstream daran
      rot wurde. Betrifft ein **eigenes** Paket, ist also unabhaengig von den
      PRs zu bewerten: pruefen, ob `packages/brain` die verwundbaren Pfade
      ueberhaupt beruehrt, und ggf. auf eine gefixte Version heben.
      *(2026-09-12, Chat: GitHub-Fehlermails Upstream-PRs)*

- [ ] **n8n laeuft mit weniger erlaubten Modulen als die `.zshrc` vorgibt** —
      der laufende Prozess hat `NODE_FUNCTION_ALLOW_EXTERNAL=pg`, in
      `~/.zshrc` steht `pg,imapflow`. `NODE_FUNCTION_ALLOW_BUILTIN` stimmt
      dagegen ueberein. n8n wurde also gestartet, bevor `imapflow` ergaenzt
      wurde — beim naechsten Neustart faellt es von selbst zusammen, bis dahin
      scheitert jeder Code-Node, der `imapflow` importiert. Nachweis:
      `ps eww <n8n-pid> | tr ' ' '\n' | grep NODE_FUNCTION`
      *(2026-09-19, Chat: Nachtfehler und Modell-Wächter)*

- [ ] **★n8n-API-Key liegt doppelt — zweite Kopie in der VS-Code-History** — der
      vorgesehene Ort ist `~/.whitestag.env` (dort korrekt). Daneben liegt seit
      dem **26.07.2026** eine Sicherungskopie in
      `~/Library/Application Support/Code/User/History/-2d0a5efe/Fkn7.env` mit
      `N8N_API_KEY` im **Klartext** — VS Code legt sie beim Bearbeiten einer
      `.env` automatisch an. Genau **eine** solche Datei mit genau **einer**
      Variablen, sonst nichts (geprueft ueber die ganze History).
      Der Ort wird von niemandem gepflegt, bei einer Rotation nicht
      mitgezogen und kann in Backups landen.
      **Zu entscheiden:** History-Kopie loeschen (verlustfrei, es ist reine
      Editor-Historie) und/oder den Key rotieren. Nicht angefasst, weil ein
      Loeschen ausserhalb des Auftrags lag.
      Gegenprobe (zeigt nur Namen, keine Werte):
      `find ~/Library/Application\ Support/Code/User/History -name '*.env' -exec grep -hoE '^[A-Z0-9_]+(_KEY|_SECRET|_PASSWORD|_TOKEN)=' {} \;`
      **Unbedenklich gegengeprueft:** die Agenten-`run-logs` enthalten nur den
      Variablen*namen* in Shell-Kommandos, keinen Wert; `n8n_rest.py` liest aus
      der Umgebung bzw. `~/.whitestag.env`.
      *(2026-09-19, Chat: Nachtfehler und Modell-Wächter)*

## Fuer Walter (nur von Hand)

- [ ] **Zwei Commits auf `fix/backup-leere-ref-ordner` ungepusht** — `e5e948c7b` (seo-geo) und `569acb6af`
      (docs(todo) Arbeitszeit-Mail), beide aus anderen Sessions. Push ist Ansage-pflichtig. *(2026-10-27, Chat: ACADEMY Kurse Vorrang)*

- [ ] **RTX Pro 6000 aus LM Link abmelden** — traegt seit 21.10. keine Modelle mehr, keine
      Konfiguration zeigt auf sie. Am Filmrechner in LM Studio den Link trennen, dann ist
      die Karte frei fuer die Coding-LLM. *(2026-10-21, Chat: LLM-Farm ohne RTX)*
      **Stand 25.10.:** Die Karte ist inzwischen frei, Strata laeuft dort statt LM Studio.
      Uebrig ist nur der verwaiste Eintrag „RTX Pro 6000 — disconnected“ in `lms link status`. *(2026-10-25, Chat: Strata für Agenten)*

- [ ] **Proxy-Auto-Neustart auf dem Film-Rechner einrichten lassen** — Prompt fuer die
      Windows-KI (geplante Aufgabe „Claude-Proxy-1235“, alle 5 Min + bei Anmeldung, mit
      Absturz- und Doppelstarttest) steht im Chatverlauf vom 25.10. Danach vom Mac pruefen:
      `/health` 200, `/status` 403. Proxy UND Strata starten weiterhin nur bei Windows-Anmeldung. *(2026-10-25, Chat: Strata für Agenten)*

- [ ] **Gmail-Connector neu anmelden** — der claude.ai-Connector verlangt eine neue
      Anmeldung (claude.ai → Einstellungen → Connectors). Solange er fehlt, kann Claude
      keine Fehler- oder Alarm-Mails im Postfach nachlesen. *(2026-10-19, Chat: WHITESTAG-AI Fallback-Umstellung)*

- [ ] **`/hooks` einmal oeffnen oder Sitzung neu starten** — aktiviert die neue
      Deutsch-Pruefung (Stop-Hook `~/.claude/scripts/deutsch-pruefung.py`) und
      den PostToolUse-Hinweis in laufenden Sitzungen. *(2026-10-14, Chat: Agentenausfälle und Ursachen)*

- [ ] **Papierkorb leeren** — darin: Claras alter Ordner aus dem
      WHITESTAG-Vault (187 Dateien, Kopie im Clara-Vault per Pruefsumme
      bestaetigt), zwei `node_modules.kaputt-*`, ein defektes Git-Objekt. *(2026-10-14, Chat: Agentenausfälle und Ursachen)*

- [ ] **Test-Kopien einer Session loeschen** — in
      `~/.claude/projects/-Users-…-Paperclip/` die `.jsonl`-Dateien mit dem Inhalt
      „Antworte nur mit OK" (Gegenproben vom 07.10.); Loeschen war mir per
      Rechtepruefung verwehrt. *(2026-10-14, Chat: Agentenausfälle und Ursachen)*
