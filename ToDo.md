# ToDo — Paperclip

Chatuebergreifende Aufgabenliste. Was hier steht, ist noch offen.

## Farm-Stabilitaet

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

- [ ] **`Process lost -- server may have restarted`** — 9 Treffer in einer
      Stunde am Abend des 02.09., Muster war vorher nicht da. Ursache offen:
      Dev-Server-Neustart, Adapter-Absturz oder OOM? *(2026-09-02, Chat: Paperclip Issue-Bereinigung)*

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

## Selbstheilung und Agenten-Aufsicht

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

- [ ] **Zwei zurueckgeholte Agenten haben gar keine Arbeit** — Buchhaltung haengt
      nur an **drei blockierten** Issues, Recherche an **keinem**. Beide stehen
      nach dem Resume auf `idle` und laufen mangels `todo` nicht an; ein Resume
      allein bringt sie also nicht zurueck in den Betrieb. Zu klaeren, ob ihre
      Routinen noch feuern oder ob die Arbeit anderswo haengt.
      *(2026-09-13, Chat: Selbstheilung wiederhergestellt)*

## Recovery-Mechanismus

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

## WHITESTAG.ACADEMY

- [ ] **Pfad-Falle entschaerft — zweiten Kurszyklus gegenpruefen** — die Routine
      produzierte 20 Kurse, aber **kein Zyklus lief je sauber zu Ende**. Zwei
      Ursachen, beide am 11.09. behoben: (1) Der CEO erfand beim Delegieren einen
      Ablagepfad (`Paperclip/Projekte/WHITESTAG.ACADEMY/content/`), weil die Spec
      den Platzhalter `<ACADEMY>` nirgends aufloeste — der Kurs vom 08.09. lag
      dort und war fuer den Lektor unauffindbar. (2) Der **Lektoratsauftrag
      enthielt gar keinen Dateipfad**, also verbrauchte der Lektor sein
      Iterationsbudget mit Suchen und endete fuenfmal in `max_iterations`.
      Geaendert: absoluter Pfad in `_KURS-SPEC.md` § 9 verankert, Routine-
      Beschreibung (Revision 8) um die Pflicht ergaenzt, den vollen Pfad in jeden
      Auftrag zu schreiben; der verirrte Kurs wurde in den kanonischen Ordner
      verschoben. **Belegt wirksam fuer einen Durchlauf:** WHI-6997 lief danach
      durch, Urteil GRUEN, alle 10 Pruefpunkte. Ob der naechste Zyklus (Di/Do
      06:00) ohne Eingriff durchlaeuft, ist noch offen.
      *(2026-09-11, Chat: WHITESTAG Agenten-Aufsicht)*

- [ ] **Zwei ACADEMY-Auftraege ohne Ergebnis — Muster pruefen** — WHI-5016 wurde
      mit **leerer Beschreibung** angelegt; der Autor meldete daraufhin dreimal
      `No work assigned, exiting heartbeat` und das Issue lag 15 Tage auf `todo`.
      Abgebrochen, weil Thema und Slug nicht rekonstruierbar waren. Falls das
      wieder auftritt: Der CEO erzeugt den Auftrag offenbar gelegentlich ohne
      Rumpf — dann gehoert eine Mindestpruefung in die Routine.
      *(2026-09-11, Chat: WHITESTAG Agenten-Aufsicht)*

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

- [ ] **★Primaermodelle stehen auf toten Eintraegen, solange die WHITESTAG-AI
      fehlt** — die 37 lmstudio-Agenten zeigen weiter auf `gemma-4-31b-it` bzw.
      `qwen3.6-35b-a3b`, die mit dem Node weg sind. Der Fallback
      `google/gemma-4-12b` (Studio) traegt, aber **jeder Lauf zahlt vorher einen
      Fehlversuch**. Auf dem MacBook liegt `gemma-4-31b-it-mlx` (31B) geladen und
      ungenutzt — deutlich staerker als das 12B und waehrend des Ausfalls die
      bessere Wahl. Zweimal angeboten, **Entscheidung steht aus**. Gegenargument:
      MLX auf dem MacBook ist langsam (gemessen ~16 tok/s, 85 s Prefill bei 18k),
      und das Geraet war zwischenzeitlich selbst tagelang aus der Flotte.
      *(2026-09-22, Chat: LLM-Farm und Netzausfall)*

- [ ] **`cheap`-Profil von zehn Agenten zeigt auf ein totes Modell** — in
      `runtime_config.modelProfiles.cheap.adapterConfig.model` steht weiterhin
      `gemma-4-31b-it` (CTO, CEO, Bueroleitung, CPO, CRO, SEO/GEO, Blender, CHO,
      Sekretaerin, Trainingscoach). **Nicht kaputt** — der Profil-Fallback steht
      schon auf `google/gemma-4-12b` —, kostet aber je cheap-Lauf einen
      Fehlversuch. Beim Umstellen daran denken: `runtime_config` wird per PATCH
      **ersetzt**, nicht gemerged, also die volle Struktur mitsenden.
      *(2026-09-22, Chat: LLM-Farm und Netzausfall)*

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
      *(2026-09-22, Chat: LLM-Farm und Netzausfall)*

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

- [ ] **MacBook seit 03.09. aus der Flotte** — `lms ls` kennt nur noch zwei
      Geraete (Local, RTX Pro 6000). `qwen3.6-35b-a3b-mlx` steht im Bericht als
      „anderes Geraet, seit 03.09. keine Calls", `gemma-4-31b-it-mlx` ist von
      `MacbookM5Mx128` (Stand KW35) nach `Local` gewandert. Der als „rund um die
      Uhr komplett" geplante Drei-Node-Betrieb laeuft damit auf zwei Knoten.
      Ursache ungeklaert — LM Link getrennt, Geraet aus oder bewusst umgezogen?
      *(2026-09-07, Chat: Kontext-Bedarf und MLX-Autofit)*
      **Ersetzt seit 12.09.:** neuer Node **WHITESTAG-AI** (RTX 5090 + RTX 3090,
      56 GB, 24/7, kostet keinen Strom) traegt jetzt den Primaerpfad. Die Pro 6000
      laeuft wieder nur tagsueber und ist als Coding-Node vorgesehen.
      *(2026-09-12, Chat: LLM-Farm GeForce-Umzug)*
      **Stand 22.09.: das MacBook ist zurueck** — `MacbookM5Mx128` ist wieder als
      LM-Link-Peer verbunden und haelt `gemma-4-31b-it-mlx` (33,80 GB, ctx
      262144) sowie drei qwen3.8-27b-Varianten und eine zweite coder-next-Kopie
      (84,67 GB). Es traegt derzeit **keinen Agentenverkehr**, waere aber waehrend
      des WHITESTAG-AI-Ausfalls das staerkste verfuegbare Modell.
      *(2026-09-22, Chat: LLM-Farm und Netzausfall)*

- [ ] **★★qwen passt nicht neben gemma auf den GeForce-Node** — beide Q4_K_M
      zusammen 40,76 GB von 56 GB, rechnerisch bleibt Platz. Praktisch laeuft
      **gemma sauber** (98304 × 4, **35 tok/s**, Prefill 1.510 tok/s, 8 parallele
      Anfragen fehlerfrei), waehrend **qwen bei 7–9 tok/s** haengt — also im
      System-RAM statt im VRAM. Gegengeprueft und **nicht** die Ursache:
      Kontextfenster (98304 / 65536 / 49152 / 32768 alle gleich langsam),
      Slot-Zahl (4 und 2) und Ladereihenfolge (beide Richtungen). Es liegt an den
      **Gewichten**, nicht am KV-Cache.
      **Verdacht: LM Studio nutzt nur die 5090.** 18,69 GB gemma + 22,07 GB qwen
      passen nicht zusammen auf eine 32-GB-Karte. Ob die 3090 in den
      Multi-GPU-Einstellungen aktiv ist, laesst sich **nur in der GUI am Node**
      pruefen (`Ctrl+Shift+H`) — per CLI gibt es dafuer nichts, und eine
      Per-Modell-GPU-Zuweisung kennt LM Studio ueberhaupt nicht (offener
      Feature-Request lmstudio-bug-tracker#2300).
      **Aktueller Zustand:** qwen ist **entladen**, die 12 Agenten laufen im
      Fallback `gemma-4-31b-it-mlx` (Mac Studio, ~16 tok/s — immer noch doppelt
      so schnell wie die 8 tok/s auf dem Node).
      *(2026-09-12, Chat: LLM-Farm GeForce-Umzug)*
      **Stand 13.09.: qwen ist wieder geladen und traegt den Primaerpfad** —
      `qwen3.6-35b-a3b`, 22,07 GB, ctx 98304 x 4 auf WHITESTAG-AI; der
      Mac-Studio-Fallback bekam seit dem 12.09. 19:14 **keinen einzigen Call**
      mehr. Die Langsamkeit besteht aber fort: gemessen **12,9–18,7 tok/s gegen
      33,6–40,7 tok/s bei gemma** (je zwei Laeufe, 150-Wort-Prompt). Das bleibt
      verkehrt herum — qwen ist ein MoE mit 3B aktiven Parametern und muesste
      ein 31B-Dense **schlagen**, nicht halb so schnell sein. Der Verdacht
      „LM Studio nutzt nur die 5090" ist damit **nicht ausgeraeumt**; pruefbar
      nur in der GUI am Node (`Ctrl+Shift+H`).
      *(2026-09-13, Chat: Selbstheilung wiederhergestellt)*
      **Stand 22.09.: unabhaengig nachgemessen, Bild unveraendert** — qwen TTFT
      **56–62 s** bei 17k Prompt (~300 tok/s Prefill) und Decode 15,6–17,7 tok/s
      gegen gemma TTFT 1,67 s, Prefill ~1.780 tok/s, Decode 33–39 tok/s. Auch die
      Rueckstellung des Fensters von 131.328 auf 98.304 aenderte **nichts**
      (61,9 / 54,3 s gegen 56,6 / 55,9 s vorher) — deckt sich mit der
      Gegenprobe vom 12.09., dass alle Fenstergroessen gleich langsam sind.
      **Null Kontext-Ueberlaeufe in acht Tagen**, das Fenster war nie der
      Engpass. Betriebsfolge: qwen-Agenten 33,9 % Fehlerquote gegen 17,0 % bei
      den gemma-Agenten (5 Tage, 354 gegen 323 Laeufe).
      **Loesungsweg steht: Kartentausch** (siehe eigener Eintrag unten).
      *(2026-09-22, Chat: LLM-Farm und Netzausfall)*

- [ ] **★★Kartentausch RTX Pro 6000 ↔ 5090 + 3090 — geplant, nicht umgesetzt** —
      Walters Vorschlag, die Pro 6000 aus dem Filmrechner in die WHITESTAG-AI zu
      bauen und die beiden GeForce-Karten dorthin. Loest den Eintrag darueber an
      der Wurzel: 40,76 GB Gewichte + ~33 GB KV = **~74 GB Bedarf** gegen die
      heutigen **56 GB** auf zwei ungleichen Karten; mit 96 GB auf **einer** Karte
      entfaellt der Layer-Offload, der PCIe-Split und das Experten-Springen ueber
      Kartengrenzen. Der Filmrechner braucht die 96 GB nicht — Schnitt ist
      encoder- und bandbreitenlimitiert.
      **Vor dem Schrauben pruefen:** (1) GPU-Offload in der LM-Studio-GUI am Node
      (`x von y Layer` bei qwen) — bestaetigt oder widerlegt die Diagnose in
      zehn Sekunden; (2) Netzteil und Gehaeuselaenge, die Pro 6000 zieht je nach
      Variante 300 W (Max-Q) oder 600 W.
      **Q8-Empfehlung danach:** `gemma-4-31B-it Q8_0` (32,64 GB) +
      `Qwen3.6-35B-A3B Q6_K` (28,51 GB) = 61,15 GB — entspricht der im August auf
      genau dieser Karte belegt laufenden Konstellation. **Beide auf Q8**
      (69,54 GB) liesse nur 26,5 GB fuer KV, also 6,5 GB weniger als damals, wo
      es schon ohne Reserve-Nachweis lief. Sauberer Weg: erst mit den jetzigen
      Q4-Quants tauschen, Offload und Prefill messen, dann Q8 gezielt nachziehen.
      Fenster und Slots bleiben bei 98.304 × 4 (65.536 ist zweimal belegt
      gescheitert). Nach dem Laden die **Gemma-Denkfalle** gegenpruefen (Q8-GGUF
      oeffnet den Denk-Kanal ueber die Jinja-Vorlage, `content` bleibt leer) —
      ein einzelner sauberer Lauf beweist dabei nichts.
      *(2026-09-22, Chat: LLM-Farm und Netzausfall)*

- [ ] **RTX-Karteileichen aufraeumen — Restpunkte** — **Die Praemisse „arbeitslos"
      ist ueberholt (04.10.2026):** die Karte traegt jetzt `qwen3.6-35b-a3b` und
      als **Primaer-Klassifikator des PII-Proxys** `google/gemma-4-12b-qat`.
      Urspruenglich am 22.09. aufgenommen, weil kein Agent (39 geprueft), kein
      aktiver n8n-Workflow (21 geprueft) und kein Dienst auf ein Modell dort
      zeigte. Offen sind noch:
      (1) `~/Desktop/n8n.sh` laedt beim Start
      `mistral-small-3.2-24b-instruct-2506@q4_k_m` auf die RTX — **das Modell
      existiert auf keiner Maschine mehr**, der Wake-Satellit steht laengst auf
      `gemma-4-31b-it` (`tools/wake-satellite/sat_config.py:85`);
      (2) **teilweise erledigt (04.10.2026):** `google/gemma-4-12b-qat` ist
      nicht mehr gelöscht, sondern der Primaer-Klassifikator des PII-Proxys —
      Eintrag in `resident-set.json` auf `when: always` gehoben, begruendet und
      das ctx-Soll auf die geladenen 32768 angeglichen. **Offen bleibt
      `qwen/qwen3-coder-next`:** es existiert wieder im Modellindex der Karte,
      ist aber nicht geladen und steht weiter auf `day-only` — pruefen, ob es
      noch gebraucht wird (es ist zugleich der 48,49-GB-Posten im
      Archivierungs-Eintrag unten);
      (3) `tools/modell-wacht/soll-laufzeit.json` bewertet die alten RTX-IDs
      `abiray/qwen3.6-35b-a3b` und `gemma4-31b-it`, die es nicht mehr gibt;
      (4) **WHITESTAG-AI deckt gar kein Waechter ab** — der Entlade-Waerter fasst
      nur `studio` an, obwohl dort die ganze Flotte liegt.
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

- [ ] **Wirkung des PII-Classifier-Rollentauschs unter Last gegenpruefen** — seit
      04.10.2026 ist `google/gemma-4-12b-qat` auf der RTX der Primaer-Klassifikator,
      `google/gemma-4-12b` (Studio) nur noch Fallback. End-to-End durch den Proxy
      fiel damit von 11,2 s auf **1,71 s**. **Gemessen wurde aber morgens bei
      leerer Farm** — dieselbe Studio lag im Ruhezustand bei 4,20 s statt 11,45 s
      unter Last. Der Vorteil der RTX ist real, der Faktor haengt an der Last.
      In 24 h gegenpruefen, ob `classifier_unavailable` und die Proxy-Latenzen
      tatsaechlich gefallen sind; Zaehler:
      `select count(*) from heartbeat_runs where error like '%classifier_unavailable%' and started_at > now() - interval '24 hours';`
      Rueckweg: `~/.paperclip/piiproxy-plist-backup-20261004-082417-vor-rollentausch.plist`.
      *(2026-10-04, Chat: Strands und PII-Fallback)*

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

- [ ] **★Große Charge läuft — Ergebnis prüfen** — der deterministische Vorlauf
      ist seit dem 08.09. gebaut (Booker-Commit `4958d35`, 801 Tests grün) und
      läuft seit dem **11.09. 20:01 über alle 5.299 Zeilen**, rund vier Stunden,
      per `nohup`. Protokoll:
      `~/Library/Logs/booker-research-prefetch-20260911-2001.log`.
      Sicherung davor: `Backup/booker-2026-09-11.dump` (32,7 MB).
      Erstlauf über 50 Zeilen zum Vergleich: 25 Funde (davon 14 triviale
      `mailto:`), Stichprobe **12 von 12 wörtlich belegt, kein Fehltreffer**.
      Nach dem Durchlauf: Zahlen aus dem Protokoll auswerten und eine **zweite
      Stichprobe** ziehen — die erste war klein. *(2026-09-11, Chat: Vorlauf Kontaktrecherche)*

- [ ] **★CLAA-2568 auf `todo` setzen — der Agent ist wach, hat aber keine
      Arbeit** — `heartbeat.enabled` steht seit dem 11.09. wieder auf `true`,
      das Issue aber weiterhin auf `backlog` und wird deshalb nicht ausgecheckt.
      Bewusst so: Er soll erst ran, wenn die Charge durch ist und die Reste
      vollständig vorliegen (erwartet rund 2.600 statt bisher 25). **Beim
      Umsetzen kein `comment` mitschicken** — siehe Aufräum-Rezept unten.
      *(2026-09-11, Chat: Vorlauf Kontaktrecherche)*

- [ ] **Fehlerklasse „wörtlich richtig, inhaltlich falsch"** — bei
      `meinbezirk.at` steht jetzt `info@rtr.at` im Bestand: die österreichische
      Regulierungsbehörde, die im Impressum als Aufsicht genannt ist. Wörtlich
      korrekt, nur nicht der Ansprechpartner. Die eiserne Regel verhindert
      **erfundene** Adressen, nicht **kontextuell falsche**, und weil nur eine
      Adresse auf der Seite stand, greift auch die Mehrdeutigkeitsprüfung nicht.
      Ob eine Ausschlussliste (Aufsichtsbehörden, Hoster, CMS-Agenturen) lohnt,
      an den Zahlen der großen Charge entscheiden.
      *(2026-09-11, Chat: Vorlauf Kontaktrecherche)*

- [ ] **Vorrangregel bei mehreren Adressen — bewusst nicht gebaut** — mit rund
      einem Drittel die größte Restgruppe, oft nur `info@` plus `datenschutz@`.
      Eine Rangfolge nach Rolle wäre deterministisch und würde einen guten Teil
      davon lösen; das Auftragsdokument weist die Auswahl unter mehreren
      Adressen aber ausdrücklich dem Agenten zu. Entscheidung vertagt, bis die
      Charge zeigt, wie groß der Anteil wirklich ist.
      *(2026-09-11, Chat: Vorlauf Kontaktrecherche)*

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

- [ ] **Routine fuer den Regelbetrieb anlegen** — bewusst noch nicht geschehen.
      Erst muss eine Stichprobe von 50 Ergebnissen sauber sein (ueber null
      Fehltreffer = Alarmzeichen). **Für den Vorlauf ist diese Hürde am 11.09.
      genommen** (12 von 12 belegt) — für den *Agenten* steht sie weiter aus, er
      hat bis heute keine verwertbaren Funde geliefert. Wichtig: `heartbeat.enabled: false` heisst
      **kein Zeitplan** — die anderen Clara-Agenten laufen nur, weil ihre
      Routinen Issues anlegen und **das Anlegen** das weckende Ereignis ist. Fuer
      Einzelanstoesse: `POST /api/agents/:id/heartbeat/invoke`.
      *(2026-09-06, Chat: Kontaktrecherche-Agent Clara)*

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

- [ ] **Entscheidung vertagt: wie VP Engineering an den lokalen Coder kommt** —
      die Pro 6000 soll Coding-Node werden, VP Engineering damit lokale Projekte
      bearbeiten. Drei Wege, keiner entschieden: (1) **eigener neuer Agent** fuer
      den Coder, VP Engineering bleibt `claude_local` — seine 13 Skills und die
      Nachtschicht bleiben unangetastet; (2) **Anthropic-kompatibler Proxy** vor
      LM Studio, Adaptertyp bleibt; (3) **voller Wechsel auf `lmstudio_local`** —
      kostet die 13 Skills doppelt: technisch faellt `paperclipSkillSync` beim
      Adaptertyp-Wechsel heraus, und konzeptionell erreicht einen
      `lmstudio_local`-Agenten ohnehin nur seine `AGENTS.md`.
      **Empfehlung aus dem Chat:** erst eine Woche mit funktionierendem PII-Proxy
      abwarten — bei 1,1 % Erfolgsquote war jede Bewertung Blindflug. Gegen
      lokal spricht die Nacht (968 Nacht-Runs in 14 Tagen, Karte laeuft nur
      tagsueber), fuer lokal spricht der Wegfall der Classifier-Abhaengigkeit.
      Kosten sind **kein** Argument: ~350 Calls/30 Tage, nach Erfahrungsregel
      35–95 €/Monat. *(2026-09-12, Chat: LLM-Farm GeForce-Umzug)*

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

- [ ] **Zwei Commits vom 19.09. sind nicht gepusht** — `bb8e91cbf`
      (`fix(tagger)`: WHITESTAG-Tagger auf den neuen Modell-Identifier) und
      `0883d9b1c` (`feat(model-warden)`: Entlade-Waerter). Der Branch
      `fix/backup-leere-ref-ordner` hat **keinen Upstream**, ein Push muesste
      ihn also erst setzen — Ziel waere `fork` (whitestagai), **nicht** `origin`
      (paperclipai, fremd). *(2026-09-19, Chat: Nachtfehler und Modell-Wächter)*

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
