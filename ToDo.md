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
  Korrektur unten). *(2026-08-23, ergaenzt 2026-08-25)*

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

- [ ] **`gemma-4-12b-qat`: Kontextfenster auf 32768** — steht auf **16384**, das
  30-Tage-Maximum liegt bei **17.955**. Das Fenster liegt also UNTER der Spitze;
  p99 ist nur 2.089, es trifft die seltenen langen Anfragen. 32768 deckt sie mit
  1,8x Puffer und kostet bei einem 12B-Q4_0 (7,15 GB) fast nichts. Muss **an der
  Karte** gemacht werden (Default-Config liegt dort, kein SSH). Paperclip:
  **WHI-5064**. *(2026-08-25, Chat: LLM-Report Spalten und Kontext-Deckel)*

- [ ] **`abiray/qwen3.6-35b-a3b` steht auf 262144 / parallel 1** — war am 23.08.
  noch 98304 / parallel 4. Aendert die VRAM-Rechnung der Karte spuerbar.
  Rueckfrage an Walter offen, ob die Umstellung von ihm kam. Ebenso, ob
  `gemma-4-12b-qat` bei `parallel 8` bleiben soll (stand am 23.08. auf 2).
  Teil von **WHI-5064**. *(2026-08-25, Chat: LLM-Report Spalten und Kontext-Deckel)*

- [ ] **Kontext-Deckel v1.3.2: Wirksamkeit ueber einen vollen Tag pruefen** —
  `Context size has been exceeded` je Tag: 66 (21.08.) / 207 / 195 / **179**
  (24.08.) / 81 vor 09:00 + 38 danach am 25.08. Der Deckel im lmstudio-Adapter
  wurde zweimal nachgebessert (v1.3.1 Kalibrierung an `usage.prompt_tokens`,
  v1.3.2 Schaetzung nach Rolle) und laeuft erst seit 25.08. 10:50 in der
  endgueltigen Fassung. Tageszahl gegen die 179 halten, je Modell und Stunde.
  Erwartung: deutlicher Rueckgang, nicht null — `trimMessages` behaelt bewusst
  die juengste Austauschgruppe. Der ctx-Bericht zaehlt die Overflows seit 23.08.
  selbst. Paperclip: **WHI-5065**.
  *(2026-08-25, Chat: LLM-Report Spalten und Kontext-Deckel)*

- [ ] **`text-embedding-bge-m3` hatte 23 wartende Anfragen** — Ursache ungeklaert.
  Vermutlich ein Indexierungslauf, aber nicht verifiziert. Wenn es dauerhaft
  staut, gehoert das Modell groesser dimensioniert oder der Batch entzerrt.
  *(2026-08-23, Chat: LLM-Farm Umbau)*

- [ ] **`ornith-1.0-9b` auf dem Studio klaeren** — taucht mit `parallel 4` in
  `lms ps` auf, stammt nicht aus dieser Session und aus keiner bekannten
  Zuordnung. Pruefen, wer es nutzt, sonst entladen. *(2026-08-23, Chat: LLM-Farm Umbau)*

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
