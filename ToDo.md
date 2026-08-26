# ToDo — Paperclip

Chatuebergreifende Aufgabenliste dieses Projekts. Wird von der
Feierabend-Routine gepflegt (Schritt 4): erledigte Eintraege werden entfernt,
neue offene Punkte aus der jeweiligen Session ergaenzt. Keine Zugangsdaten
hier hinein — nur den Fundort nennen.

## LLM-Farm

- [ ] **Timeout-Quote des PII-Proxys neu messen** — am 23.08. 61,4 % ueber 44
  Anfragen, mit steigender Tendenz im Messfenster (45 % → 75 % ueber 20 Minuten).
  Skript liegt als `tools/rtx-nachtbilanz.sh`. Erst nach einer vollen Nacht ist
  die Aussage belastbar — und die RTX laeuft seit 23.08. durch, das allein sollte
  die Quote deutlich druecken. **Reasoning scheidet als Ursache aus** (siehe
  Korrektur unten). **Achtung, Basis hat sich am 25.08. geaendert:** der
  Klassifikator `google/gemma-4-12b-qat` wurde beim RTX-Aufraeumen geloescht, der
  Proxy lief seither nur ueber seinen Fallback — also jede Anfrage mit einem
  Fehlversuch davor, was die alte Quote nach oben verfaelscht. Seit 25.08. steht
  `PII_PROXY_CLASSIFIER_MODEL` auf `google/gemma-4-12b` (Mac Studio, 65.536 × 6).
  Neu messen, nicht gegen die alten Zahlen halten.
  *(2026-08-23, ergaenzt 2026-08-25)*

  > **Korrektur zum entfernten Eintrag „Reasoning beim PII-Classifier abschalten":**
  > Die Praemisse war falsch gemessen. Ueber alle Vorhersagen der Server-Logs
  > (Anteil mit `reasoning_tokens > 0`) steht `google/gemma-4-12b-qat` bei
  > **0,1 % (22./23.08.) und 0,0 % (24./25.08., 2.598 Aufrufe)**. Die zitierten
  > „342/397/356 Denk-Token je Aufruf" sind die **Maximalwerte dieser seltenen
  > 0,1 %**, nicht der Normalfall. Umgekehrt stand der Studio-Zwilling
  > `google/gemma-4-12b` am 22.08. bei **10,3 %**, nicht bei 0 — er war der
  > Denker, nicht die RTX. Beide sind inzwischen bei 0,0 %. Lehre: eine
  > Stichprobe aus drei Einzelaufrufen taugt nicht fuer eine Quotenaussage; die
  > Zahl steht in den Logs. *(2026-08-25, Chat: LLM-Report Spalten und Kontext-Deckel)*

- [ ] **`maxPromptTokens` je Agent setzen, um die Slots zurueckzukaufen** — die
  Kontextueberlaeufe entstehen **beim Generieren von Tool-Calls**, nicht beim
  Einlesen des Prompts (ausgezaehlt 20.–26.08.: **316 gegen 9**). Der Prompt passt;
  was ueberlaeuft, ist Prompt + Ausgabe. `DEFAULT_PROMPT_BUDGET_RATIO = 0.8` laesst
  bei ctx 65.536 nur **13.108 Token** fuer die Antwort, bei 98.304 sind es 19.661 —
  daher lief 98.304 achtzehn Stunden fehlerfrei, waehrend 65.536 binnen einer Stunde
  bei 71 % Ueberlaeufen lag. **`maxPromptTokens` ist pro Agent konfigurierbar und
  ueberschreibt die 80-%-Regel**, also ein Hebel OHNE Codeaenderung: bei ctx 65.536
  und `maxPromptTokens: 40000` blieben 25.536 Token Luft, mehr als 98.304 heute
  bietet. Damit waeren 65.536 × 8/12 tragbar = rund **60 % mehr Bearbeitungsplaetze
  bei gleichem VRAM**. Vorher messen, wie gross die groessten legitimen
  Tool-Call-Argumente wirklich sind — die 40.000 sind hergeleitet, nicht gemessen.
  *(2026-08-25, korrigiert 2026-08-26, Chat: LLM-Farm Übergangskonzept)*

  > **Verworfen: „`BUDGET_LOOKUP_THRESHOLD_TOKENS` senken".** Die Praemisse war
  > falsch. Das Lauf-Log zeigt, dass der Schwellenwert ausloest und das Budget
  > korrekt auf 52.428 gesetzt wird — die Konstante zu senken haette nichts
  > geaendert. Zusaetzlich war die Begruendung veraltet: seit v1.3.2 wiegt der
  > Schaetzer nach Rolle (`chars/2` fuer Tool-Inhalte), die Unterschaetzung liegt
  > bei ~1,09 statt 2,19. *(2026-08-26)*

- [ ] **Kontextueberlaeufe nach einem vollen Tag neu bewerten** — Ursache ist seit
  25.08. bekannt (Schwellenwert oben), das Fenster steht wieder auf 98.304 und
  seit dem Rollback um 14:56 gab es **null** `Context size has been exceeded`
  (vorher ~19/h). Verlauf zum Vergleich: 0/Tag bis 20.08., dann 66 (21.08.) /
  139 / 101 / 73 / 114 (25.08.) — die Ueberlaeufe begannen am Tag des
  RTX-Aufraeumens. Tageszahl am 26.08. gegenpruefen. Paperclip: **WHI-5065**.
  *(2026-08-25, ergaenzt 2026-08-25, Chat: LLM-Farm Übergangskonzept)*

- [ ] **`deepseek/deepseek-v4-flash` auf der RTX klaeren** — 156,38 GB, MXFP4,
  256x8,4B MoE, max ctx 1.048.576, **nicht geladen**. Passt mit 156 GB nicht in
  96 GB VRAM und meldet **`trainedForToolUse: false`** — als Agentenmodell damit
  unbrauchbar, unabhaengig von seiner Qualitaet. Herkunft und Zweck ungeklaert;
  wenn es nicht gebraucht wird, sind 156 GB Plattenplatz auf der Karte frei.
  *(2026-08-26, Chat: LLM-Farm Übergangskonzept)*

- [ ] **`text-embedding-bge-m3` hatte 23 wartende Anfragen** — Ursache ungeklaert.
  Vermutlich ein Indexierungslauf, aber nicht verifiziert. Wenn es dauerhaft
  staut, gehoert das Modell groesser dimensioniert oder der Batch entzerrt.
  *(2026-08-23, Chat: LLM-Farm Umbau)*

- [ ] **Cloud-Rueckkehrer auf `lmstudio_local` umstellen** — n8n-Betriebsingenieur
  (39 Laeufe/Tag, **77 % seiner Fehler sind 429er**) und Social Media & Community
  laufen weiter auf `claude_local`. Der Wechsel des `adapter_type` ist der
  riskanteste Schritt des Konzepts und wurde bewusst nicht auf eine gerade erst
  stabilisierte Farm gestapelt. Ziel laut Spec: n8n-Betriebsingenieur auf
  `abiray/qwen3.6-35b-a3b`, Social Media & Community auf `gemma4-31b-it`.
  **VP Engineering bleibt auf `claude-sonnet-5`** (Entscheidung vom 25.08.).
  *(2026-08-25, Chat: LLM-Farm Übergangskonzept)*

- [ ] **`maxIterations`-Klemmung beobachten** — bei allen lmstudio-Agenten am 25.08.
  auf hoechstens 12 gesenkt (16 Agenten lagen zwischen 20 und 40); wer darunter
  lag, behielt seinen Wert. Begruendung war das damals aktive Ueberlaufproblem —
  mehr Iterationen heisst laengere Historie. Mit dem wieder groesseren Fenster ist
  dieser Grund schwaecher. Zwei Laeufe sind noch am selben Tag an
  „Max iterations (12) reached without final answer" gescheitert. Wenn sich das
  haeuft, fuer die betroffenen Agenten wieder anheben.
  *(2026-08-25, Chat: LLM-Farm Übergangskonzept)*

- [ ] **Timeout-Rest im Gemma-Pool nach einem vollen Tag bewerten** —
  `gemma4-31b-it` traegt mit ~29 Agenten mehr als die halbe Flotte auf **8 Slots**
  und ist das langsame dichte Modell (25 s Median-Prefill gegen 5 s bei der MoE).
  Am 25.08. nach dem Umbau: 4 Timeouts in 20 Minuten, **alle** auf diesem Modell
  (Akquise & Booking, CMO, Label Manager). Naechster Schritt laut Spec, falls es
  bleibt: analytische Agenten auf die MoE ziehen — Vitals-Monitor,
  LLM-Konfigurationsanalyst, Label Manager brauchen kein kreatives Deutsch.
  *(2026-08-25, Chat: LLM-Farm Übergangskonzept)*

- [ ] **Spec-Review Farm-Uebergangskonzept** — `docs/superpowers/specs/2026-08-25-farm-uebergangskonzept-design.md`
  wurde geschrieben, umgesetzt und viermal nachkorrigiert, aber von Walter nie
  durchgesehen. Enthaelt den Abschnitt „Was bei der Umsetzung anders kam" mit
  vier belegten Abweichungen vom Entwurf.
  *(2026-08-25, Chat: LLM-Farm Übergangskonzept)*

- [ ] **RTF-Betriebsuebersicht um archivierte Modelle ergaenzen** —
  `docs/LLM-Farm Betriebsuebersicht 2026-08-22.rtf` listet nur geladene
  Instanzen. Die auf der NAS liegenden (u.a. die beiden Coder-Modelle, 111 GB)
  fehlen, ebenso die auf Platte vorhandenen, nicht geladenen.
  *(2026-08-23, Chat: LLM-Farm Umbau)*

## Betrieb

- [ ] **Adapter-Build und -Reload nur im Drain-Fenster** — `npm run build` im
  `paperclip-adapter-lmstudio` und `POST /api/adapters/:type/reload` toeten
  **laufende lmstudio-Heartbeats**, obwohl der Server durchlaeuft (25.08.: sechs
  Laeufe um 08:30, acht um 10:50). Die Meldung `Process lost -- server may have
  restarted` fuehrt in die Irre — sie ist in `services/heartbeat.ts:2197` blosser
  Fallback fuer Laeufe **ohne** `processPid`, und genau das sind in-process
  laufende lmstudio-Runs. Kuenftig vorher auf null laufende Heartbeats warten,
  wie bei einem Neustart. Ein Deploy-Skript mit eingebautem Drain-Fenster waere
  die saubere Loesung. *(2026-08-25, Chat: LLM-Report Spalten und Kontext-Deckel)*

- [ ] **`~/Desktop/n8n.sh` bei Aenderungen doppelt pflegen** — die Datei ist seit
  23.08. unter `tools/n8n-start/n8n.sh` versioniert, wird aber weiterhin vom
  Desktop ausgefuehrt. Ohne `cp` nach jeder Aenderung driftet der Repo-Stand weg.
  Besser waere ein Symlink oder ein Deploy-Schritt. *(2026-08-23, Chat: LLM-Farm Umbau)*

- [ ] **`~/bin/nas-mount-keepalive.sh` auf `nas-mount.sh` umstellen** — der
  Keepalive fuer `/Volumes/homes` hat dieselbe Haenger-Anfaelligkeit, die den
  Archiv-Waechter am 24.08. 28 Stunden lahmgelegt hat: kein Timeout um
  `osascript mount volume`. Seine Lebendpruefung (`[ -d … ]`) ist korrekt,
  deshalb blieb er unangetastet. Umstellbar ohne Codeaenderung:
  `nas-mount.sh --freigabe homes --probe "cw/Obsidian/Clara-Vault/Kontakte"`.
  *(2026-08-25, Chat: Sicherungsalarm NAS-Mount)*

- [ ] **Pruefung des Claude-Code-Spiegels im Sicherungs-Waechter verschaerfen** —
  `ordner_stand()` liest nur die mtimes der OBERSTEN Ebene, die bei
  verschachtelten Aenderungen nicht mitziehen. Am 25.08. meldete der Waechter
  „vor 43 Stunden", waehrend Dateien von vor Minuten auf der NAS lagen. Bei
  7 Tagen Grenze faellt ein Totalausfall von Synology Drive erst sehr spaet auf.
  *(2026-08-25, Chat: Sicherungsalarm NAS-Mount)*

- [ ] **Erste Nacht unter dem neuen Mount-Waechter nachsehen** — `nas-mount.sh`
  hat `mount-whitestag-archiv.sh` am 25.08. abgeloest und lief tagsueber sauber
  (25 Laeufe Exit 0, null Zwangs-Ummountungen). Der Beweis steht aber erst aus,
  wenn DB-Sicherung (02:30), HDD-Katalog (02:30) und Vault-Spiegel (04:00)
  einmal komplett durchgelaufen sind: `~/.paperclip/logs/nas-mount.log`
  (muss ohne neue Zeile bleiben), `paperclip-db-backup.log`, `hdd-katalog.log`
  und `vault-nas-sync.log` am Morgen des 26.08. pruefen.
  *(2026-08-25, Chats: Mount-Waechter Katalogausfall + Sicherungsalarm NAS-Mount)*
