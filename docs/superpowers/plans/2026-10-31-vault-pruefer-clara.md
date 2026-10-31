# Vault-Prüfer Clara Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ein nächtlicher launchd-Dienst prüft die Struktur von Claras Vault (P1–P8) und schreibt Status-Datei, Bericht und Listen; der Vault-Maintainer berichtet daraus mit Belegpflicht.

**Architecture:** Reine Prüf-Funktionen in kleinen CommonJS-Modulen unter `tools/vault-pruefer-clara/lib/`, ein dünner Runner für launchd, der Spiegel und Index liest und die Ausgaben schreibt. Nur Stufe 1 (Überwachen) — die Korrekturen der zweiten Ausbaustufe sind ein eigener Plan.

**Tech Stack:** node 22 (CommonJS), `gray-matter` ^4.0.3 und `postgres` ^3.4.5 (gleiche Versionen wie `packages/brain`), Tests mit `node --test`.

**Spec:** `docs/superpowers/specs/2026-10-31-vault-pruefer-clara-design.md`

## Global Constraints

- Lesequelle ist der Spiegel `~/.paperclip/clara-vault-mirror`, nie das NAS. Geschrieben wird nur der Bericht, und zwar auf das NAS unter `/Volumes/homes/cw/Obsidian/Clara-Vault/Paperclip/_Meta/Vault-Pruefer-Reports/<YYYY-MM-DD>.md`.
- Der Prüfer ändert, verschiebt oder löscht keine Notiz.
- Frontmatter wird mit `gray-matter` geparst — „gültig" heißt „vom Brain-Indexer lesbar".
- Erwartete Werte (`typen`, Status-Werte) kommen aus `obsidian-tagger/templates/frontmatter-template-clara.yaml`; Tag-Grenzen 2–6.
- Größengrenze 2 MB (`2 * 1024 * 1024`) und Index-Ausschlüsse exakt wie `packages/brain/src/indexer/watcher.ts` (`attachments`, `.obsidian`, `.trash`, `Analysen/Link-Erkennung`, `Analysen/Link-Erkennung-Shadow`, `Analysen/LLM-Nutzung`).
- Stufen: P1, P2 hoch · P3, P4, P6-echt mittel · P5, P6-Import, P7, P8 niedrig.
- `exit_code`: 0 ok · 3 Spiegel veraltet (letztes `OK` in `clara-mirror-sync.log` älter als 60 min) oder nicht lesbar · 4 Index-DB nicht erreichbar (P2 = `null`, Rest läuft) · 124 Timeout (30 min). Bei ≠ 0 Mail über den Mailhub wie in `vault-tagger-clara.js`.
- Status: `~/.paperclip/logs/vault-pruefer-clara-last.json`. Listen: `~/.paperclip/state/vault-pruefer-clara/<datum>/P<n>.txt`. Vortag: `~/.paperclip/state/vault-pruefer-clara/letzter-stand.json`.
- Datum im Dateinamen in `Europe/Berlin`. Kommentare und Texte auf Deutsch, im Stil von `vault-tagger-clara.js`.

## Review Focus

1. **Unicode-Normalform der Pfade:** Dateinamen vom Mac/SMB können NFD sein, DB-Pfade NFC → P2 und P7 melden sonst falsche Treffer. Erwartet: Vergleich immer auf `normalize('NFC')`. Test in Task 3.
2. **Frontmatter, das kein Objekt ist** (Liste, String, `null`): darf nicht abstürzen. Erwartet: P1, wenn gray-matter wirft; sonst wie „leeres Frontmatter" behandeln. Test in Task 1.
3. **Wikilink-Varianten** `[[Ziel|Alias]]`, `[[Ziel#Abschnitt]]`, `![[bild.png]]`, `[[Ordner/Ziel]]`: dürfen nicht als tot gelten, wenn das Ziel existiert; Anhänge (Bild/PDF/Audio/Canvas) zählen nie. Test in Task 2.
4. **`tags` als String** statt Liste (`tags: Musik`): zählt als P5, kein Absturz. Test in Task 2.
5. **Kaputte oder fehlende Sync-Log-Zeile:** kein `OK`-Eintrag lesbar → `exit_code` 3, kein Lauf auf altem Spiegel. Test in Task 5.

---

### Task 1: Gerüst, Vorlage und Notizen laden

**Files:**
- Create: `tools/vault-pruefer-clara/package.json` (`"type": "commonjs"`, deps `gray-matter` ^4.0.3, `postgres` ^3.4.5, script `"test": "node --test test/"`)
- Create: `tools/vault-pruefer-clara/lib/lesen.js`
- Create: `tools/vault-pruefer-clara/test/fixtures/vault/…` (kleine Notizen, je Fall eine), `test/fixtures/vorlage.yaml` (Ausschnitt der echten Vorlage mit `typen: {Notiz, Songtext, Chat?}` — `Chat` bewusst NICHT, damit P3 greift)
- Test: `tools/vault-pruefer-clara/test/lesen.test.js`

**Interfaces:**
- Produces: `ladeVorlage(pfad: string): { typen: Set<string>, status: Set<string>, tagsMin: 2, tagsMax: 6 }` — `status` aus dem Kommentar der `basis.status`-Zeile (`Entwurf | In Bearbeitung | Abgeschlossen | Archiviert`), da die Vorlage ihn nur dort nennt.
- Produces: `ladeNotizen(wurzel: string): Notiz[]` mit `Notiz = { pfad: string /* relativ, '/', NFC */, groesse: number, gross: boolean, fm: object|null, fmFehler: string|null, body: string, hash: string|null /* sha256 des Rohtexts */ }`. Ordner mit führendem Punkt überspringen, nur `.md`. Bei `gross` wird die Datei nicht gelesen (`fm=null, body='', hash=null`).

- [ ] **Step 1: Failing tests** in `test/lesen.test.js`:
  - `ladeVorlage liest Typen und Status` — `typen.has('Songtext')`, `!typen.has('Chat')`, `status.has('In Bearbeitung')`, `status.size === 4`.
  - `ladeNotizen liefert NFC-Pfade mit Schrägstrich` — Fixture `Kontakte/Müller.md`, als NFD angelegt: `pfad === 'Kontakte/Müller.md'.normalize('NFC')`.
  - `ungültiges YAML landet in fmFehler` — Fixture mit `organisation: "Fa. X\, Y"`: `fm === null`, `fmFehler` enthält `escape`.
  - `Frontmatter als Liste stürzt nicht ab` — Fixture `---\n- a\n---\nText`: `fmFehler === null`, `fm` ist `{}`.
  - `Dateien über 2 MB werden nicht gelesen` — im Test zur Laufzeit erzeugt (nicht eingecheckt): `gross === true`, `hash === null`.
- [ ] **Step 2:** `cd tools/vault-pruefer-clara && npm install && npm test` → FAIL (`Cannot find module '../lib/lesen'`).
- [ ] **Step 3:** `lib/lesen.js` implementieren; YAML der Vorlage mit `require('gray-matter').engines.yaml.parse` (js-yaml aus gray-matter, keine weitere Abhängigkeit). Nicht-Objekt-Frontmatter → `{}`.
- [ ] **Step 4:** `npm test` → PASS.
- [ ] **Step 5:** Commit `feat(vault-pruefer-clara): Vorlage und Notizen aus dem Spiegel lesen` (`package.json`, `package-lock.json`, `lib/`, `test/`).

### Task 2: Prüfungen P1, P3–P8

**Files:**
- Create: `tools/vault-pruefer-clara/lib/pruefungen.js`
- Test: `tools/vault-pruefer-clara/test/pruefungen.test.js` (Notizen als Objekte im Test gebaut, kein Dateisystem)

**Interfaces:**
- Consumes: `Notiz`, Vorlage aus Task 1.
- Produces: `pruefe(notizen: Notiz[], vorlage): Befunde` mit `Befunde = { P1, P3, P4, P5, P6_echt, P6_import, P7_gleich, P7_name, P8: Eintrag[] }`, `Eintrag = { pfad: string, detail: string }`.
- Produces: `PRUEFUNGEN: Record<string, { titel: string, stufe: 'hoch'|'mittel'|'niedrig', quelle: string }>` für alle Schlüssel inkl. `P2` — `quelle` z. B. P1 → `n8n Clara-Kontakte/Termine-Workflow`, P3 → `Dokumenten-Import (typ = Ordnerpfad) / ChatGPT-Import (typ: Chat)`.
- Produces: `gruppiere(eintraege: Eintrag[]): Array<{ detail: string, anzahl: number, beispiele: string[] }>` (absteigend nach Anzahl, max. 10 Beispiele).

- [ ] **Step 1: Failing tests:**
  - `P1 meldet fmFehler` — `detail` = erste Zeile des Fehlers.
  - `P3 meldet typ außerhalb der Vorlage mit Wert als detail` — `typ: 'Kreativität/Songwriting/Blogtexte'` → `detail === 'Kreativität/Songwriting/Blogtexte'`; `typ: 'Songtext'` → kein Eintrag; fehlendes `typ` → kein Eintrag.
  - `P4 meldet status Offen`.
  - `P5: tags als String, 1 Tag, 7 Tags, fehlend` → je ein Eintrag; 2 und 6 Tags → keiner.
  - `P6 löst Alias, Abschnitt, Einbettung und Ordnerpfad auf` — Ziele `Ziel`, `Ordner/Ziel` existieren: `[[Ziel|x]]`, `[[Ziel#h]]`, `![[Ziel]]`, `[[Ordner/Ziel]]` → keine Einträge; `[[bild.png]]` → keiner; `[[Gibtsnicht]]` → `P6_echt`; `[[mailto:a@b.de` …`]]`, `[[http://x.de]]`, `[[Bearbeiten]]` → `P6_import`. Auflösung case-insensitiv über Basisname oder relativen Pfad ohne `.md`.
  - `P7 trennt inhaltsgleich und nur namensgleich` — zwei Notizen gleichen Basisnamens mit gleichem `hash` → beide in `P7_gleich`; mit verschiedenem `hash` → `P7_name`; `detail` = Basisname klein.
  - `P8: gross, leerer body, Datei in der Wurzel` — `_status.md` in der Wurzel wird gemeldet (bewusst, die Liste ist kurz).
  - `gruppiere zählt nach detail` — drei Einträge, zwei gleiche Details → `[{detail, anzahl: 2, …}, {…, anzahl: 1}]`.
- [ ] **Step 2:** `npm test` → FAIL.
- [ ] **Step 3:** `lib/pruefungen.js` implementieren. Linkmuster: `/!?\[\[([^\]|#^]+)/g`; Import-Rest, wenn das Ziel mit `http`, `mailto:` oder `[` beginnt oder genau `Bearbeiten` ist; Anhang, wenn Endung `png|jpe?g|gif|webp|svg|pdf|mp3|wav|m4a|canvas`.
- [ ] **Step 4:** `npm test` → PASS.
- [ ] **Step 5:** Commit `feat(vault-pruefer-clara): Strukturprüfungen P1, P3–P8`.

### Task 3: Index-Abgleich P2

**Files:**
- Create: `tools/vault-pruefer-clara/lib/index-abgleich.js`
- Test: `tools/vault-pruefer-clara/test/index-abgleich.test.js`

**Interfaces:**
- Consumes: `Notiz` aus Task 1.
- Produces: `vergleicheIndex(notizen: Notiz[], index: Array<{ path: string, chunks: number }>): Eintrag[]` — `detail` ist `fehlt im Index` oder `keine Chunks`. Übersprungen werden `gross`, leerer `body`, Notizen mit `fmFehler` (stehen schon in P1) und die Index-Ausschlüsse aus den Global Constraints (Segment-Präfix-Abgleich wie `isExcluded` in `watcher.ts`).
- Produces: `async ladeIndex(url: string): Array<{ path, chunks }>` — eine Abfrage `select n.path, count(c.id)::int as chunks from brain.notes n left join brain.chunks c on c.note_id = n.id group by n.path`; `postgres(url, { max: 1, connect_timeout: 10 })`, danach `sql.end()`.

- [ ] **Step 1: Failing tests** (nur `vergleicheIndex`, `ladeIndex` wird im Lauf in Task 5 geprüft):
  - `fehlt im Index` und `keine Chunks` werden erkannt.
  - `NFD-Pfad im Index passt zu NFC-Notiz` — Index-Pfad `'Kontakte/Müller.md'.normalize('NFD')`, `chunks: 2` → kein Eintrag.
  - `Ausschlüsse, gross, leer und fmFehler werden nicht gemeldet` — u. a. `Analysen/Link-Erkennung-Shadow/2026-05-29.md`; `Analysen/Meta.md` dagegen schon.
- [ ] **Step 2:** `npm test` → FAIL.
- [ ] **Step 3:** implementieren; beide Seiten mit `normalize('NFC')` vergleichen.
- [ ] **Step 4:** `npm test` → PASS.
- [ ] **Step 5:** Commit `feat(vault-pruefer-clara): Abgleich mit dem Brain-Index (P2)`.

### Task 4: Status, Delta, Bericht und Listen

**Files:**
- Create: `tools/vault-pruefer-clara/lib/ausgabe.js`
- Test: `tools/vault-pruefer-clara/test/ausgabe.test.js`

**Interfaces:**
- Consumes: `Befunde` + `P2: Eintrag[] | null`, `PRUEFUNGEN`, `gruppiere` aus Task 2.
- Produces: `baueStatus({ befunde, vorher, notizenGesamt, exitCode, reportPath, zeit: Date }): Status` mit `Status = { timestamp /* ISO ohne ms, Z */, exit_code, notizen_gesamt, pruefungen: Record<schluessel, { anzahl: number|null, delta_vortag: number|null, stufe }>, neu_hoch: number, report_path }`. `delta_vortag` = `null` ohne Vortag oder wenn eine Seite `null` ist. `neu_hoch` = Summe der positiven Deltas der Stufe hoch.
- Produces: `baueBericht(status, befunde, datum: string): string` (Markdown, Frontmatter `title`, `datum`, `typ: Notiz`, `status: Abgeschlossen`, `tags: [Vault-Pflege, Bericht]` — damit der Bericht selbst P3/P5 besteht).
- Produces: `schreibeListen(befunde, verzeichnis: string): void` — je Schlüssel `P<n>.txt`, eine Zeile `pfad<TAB>detail`, sortiert.

- [ ] **Step 1: Failing tests:**
  - `erster Lauf hat delta_vortag null und neu_hoch 0`.
  - `Delta und neu_hoch` — vorher `P1: 6`, jetzt 8 → `delta_vortag: 2`, `neu_hoch: 2`; `P3` von 10 auf 12 zählt nicht in `neu_hoch`.
  - `P2 null bleibt null, ohne Absturz`.
  - `Bericht nennt Änderungen zuerst und je Prüfung die Quelle` — die erste `##`-Überschrift ist `## Änderungen zum Vortag`; Abschnitt P1 enthält `PRUEFUNGEN.P1.quelle`; maximal 10 Beispielpfade je Gruppe.
  - `Bericht-Frontmatter besteht P3 und P5` — `pruefe([berichtAlsNotiz], vorlage)` liefert keine P3/P5-Einträge.
- [ ] **Step 2:** `npm test` → FAIL.
- [ ] **Step 3:** implementieren.
- [ ] **Step 4:** `npm test` → PASS.
- [ ] **Step 5:** Commit `feat(vault-pruefer-clara): Status mit Vortags-Delta, Bericht und Listen`.

### Task 5: Runner, launchd und README

**Files:**
- Create: `tools/vault-pruefer-clara/vault-pruefer-clara.js` (Einstieg für launchd)
- Create: `tools/vault-pruefer-clara/lib/spiegel.js`
- Create: `tools/vault-pruefer-clara/de.whitestag.vault-pruefer-clara.plist` (wie der Tagger-Plist, `StartCalendarInterval` 01:45, Programm `~/.paperclip/scripts/vault-pruefer-clara/vault-pruefer-clara.js`, Env `BRAIN_DATABASE_URL=postgres://walterschoenenbroecher.de@localhost:5432/paperclip_brain_clara`)
- Create: `tools/vault-pruefer-clara/README.md` (Tabelle wie beim Tagger, `exit_code`-Liste, Deploy-Befehle inkl. `npm ci --omit=dev` im Live-Ordner)
- Test: `tools/vault-pruefer-clara/test/spiegel.test.js`

**Interfaces:**
- Consumes: alles aus Task 1–4.
- Produces: `spiegelAktuell(logText: string, jetzt: Date, maxMinuten = 60): { ok: boolean, grund: string }` — letzte Zeile `YYYY-MM-DD HH:MM:SS  OK (node): …` (Zeit Europe/Berlin) auswerten.
- Produces: `main(opts?: { spiegel, vorlage, logDatei, statusDatei, stateDir, berichtDir, dbUrl, jetzt })` — Pfade überschreibbar für den Test; Standardwerte aus den Global Constraints.

- [ ] **Step 1: Failing tests:**
  - `spiegelAktuell`: OK-Zeile 10 min alt → `ok: true`; 90 min alt → `ok: false`; Log nur mit `FEHLER`-Zeilen, leer oder Müll → `ok: false`.
  - `main gegen Fixtures` — Fixture-Vault, frisches Fake-Log, `dbUrl` auf einen nicht erreichbaren Port: Status hat `exit_code: 4`, `pruefungen.P2.anzahl === null`, `pruefungen.P1.anzahl === 1`, Bericht und `P1.txt` existieren in den Temp-Verzeichnissen, `letzter-stand.json` geschrieben. Mail wird über `opts.mail` (Stub) ausgelöst.
  - `main mit veraltetem Spiegel` → `exit_code: 3`, kein Bericht.
- [ ] **Step 2:** `npm test` → FAIL.
- [ ] **Step 3:** implementieren. Ablauf: Spiegel prüfen → Vorlage + Notizen → `pruefe` → `ladeIndex`/`vergleicheIndex` (bei Fehler P2 `null`, `exit_code` 4) → Listen, Bericht, Status, Vortag → Mail bei ≠ 0. Gesamter Lauf mit Watchdog 30 min (`exit_code` 124, Status trotzdem schreiben). Mail-Funktion aus `vault-tagger-clara.js` übernehmen (gleicher Absender/Empfänger).
- [ ] **Step 4:** `npm test` → PASS.
- [ ] **Step 5:** Echter Probelauf ohne launchd, Ausgaben in Temp-Verzeichnisse: `node -e "require('./vault-pruefer-clara.js').main({ statusDatei: '/tmp/…/s.json', stateDir: '/tmp/…/state', berichtDir: '/tmp/…/bericht' })"`. Erwartet: `exit_code` 0, `P1.anzahl` 6, `P3.anzahl` um 1.677, `notizen_gesamt` um 17.500. Abweichungen gegen den Ist-Stand der Spec klären, bevor es weitergeht.
- [ ] **Step 6:** Commit `feat(vault-pruefer-clara): launchd-Runner mit Spiegel-Prüfung und Index-Abgleich`.

### Task 6: Agent, Routine und Deploy

**Files:**
- Modify: `tools/vault-tagger-clara/AGENTS.clara-vault-maintainer.md` — neuer Schritt 3b „Prüfer-Status lesen" (`cat ~/.paperclip/logs/vault-pruefer-clara-last.json` im selben `shell_exec` wie Schritt 3), Kommentar-Vorlage um einen Block „Strukturprüfung" mit `timestamp`, `exit_code`, je Prüfung `anzahl`/`delta_vortag`, `neu_hoch`, `report_path` erweitern; `done`/`blocked`-Regeln aus der Spec; Verbote unverändert.
- Modify: `tools/vault-tagger-clara/README.md` — Verweis auf den Prüfer.

- [ ] **Step 1: Deploy Dienst:**
  ```bash
  mkdir -p ~/.paperclip/scripts/vault-pruefer-clara
  cp -R tools/vault-pruefer-clara/{vault-pruefer-clara.js,lib,package.json,package-lock.json} ~/.paperclip/scripts/vault-pruefer-clara/
  (cd ~/.paperclip/scripts/vault-pruefer-clara && npm ci --omit=dev)
  cp tools/vault-pruefer-clara/de.whitestag.vault-pruefer-clara.plist ~/Library/LaunchAgents/
  launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/de.whitestag.vault-pruefer-clara.plist
  launchctl kickstart gui/$(id -u)/de.whitestag.vault-pruefer-clara
  ```
  Erwartet: `vault-pruefer-clara-last.json` mit heutigem `timestamp`, `exit_code` 0, Bericht im Vault unter `Paperclip/_Meta/Vault-Pruefer-Reports/`. Das ist die Baseline (`delta_vortag` überall `null`).
- [ ] **Step 2:** AGENTS.md ändern und per `PUT /api/agents/500a1656-be93-4e79-a01c-e33cba023815/instructions-bundle/file` einspielen (wie im Tagger-README); Routine `f5f8ba14-7e25-4bc1-a3a3-ebe0d97e21ee` in „Clara-Vault-Pflege" umbenennen. Gegenprobe: Bundle per GET lesen, Inhalt = Repo-Datei (`diff`).
- [ ] **Step 3:** Routine einmal manuell auslösen. Erwartet: Issue-Kommentar enthält die Rohwerte beider Status-Dateien; Status `done` (Baseline, `neu_hoch` 0). Fehlt ein Rohwert → Anleitung nachschärfen, nicht weiter.
- [ ] **Step 4:** Commit `feat(vault-maintainer-clara): Strukturprüfung in den Nachtbericht aufnehmen`.
- [ ] **Step 5:** Nach dem ersten echten Nachtlauf (01:45 / 02:00) prüfen: `delta_vortag` ist gefüllt, Issue sauber. Ergebnis an Walter melden.
