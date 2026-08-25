# ToDo — Paperclip

Chatuebergreifende Aufgabenliste dieses Projekts. Wird von der
Feierabend-Routine gepflegt (Schritt 4): erledigte Eintraege werden entfernt,
neue offene Punkte aus der jeweiligen Session ergaenzt. Keine Zugangsdaten
hier hinein — nur den Fundort nennen.

## LLM-Farm

- [ ] **Reasoning beim PII-Classifier auf der RTX abschalten** — `google/gemma-4-12b-qat`
  ist das einzige Modell der Farm, das noch denkt: gemessen 342/397/356 Denk-Token
  je Aufruf, waehrend der Studio-Zwilling `google/gemma-4-12b` auf 0 steht. Bei
  18.703 Aufrufen im Monat ist das die verbliebene Ursache der Proxy-Timeouts —
  die Warteschlangen sind leer, die Einzelaufrufe sind langsam. Fix wie bei den
  beiden grossen Modellen: Jinja-Vorlage an der RTX, `enable_thinking`-Block im
  Generierungsanstoss entfernen. *(2026-08-23, Chat: LLM-Farm Umbau)*

- [ ] **Timeout-Quote nach dem Reasoning-Fix neu messen** — am Ende der Sitzung
  61,4 % ueber 44 Anfragen, mit steigender Tendenz innerhalb des Messfensters
  (45 % → 75 % ueber 20 Minuten). Skript liegt als `tools/rtx-nachtbilanz.sh`.
  Erst nach einer vollen Nacht ist die Aussage belastbar. *(2026-08-23, Chat: LLM-Farm Umbau)*

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
