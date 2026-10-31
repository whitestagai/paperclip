# Vault-Prüfer Clara — Strukturprüfung für den Clara-Vault

Stand: 2026-10-31 · Status: Entwurf, nicht freigegeben

## Warum

Der Vault-Maintainer von Clara Sound (Agent `500a1656`) prüft heute genau eine
Sache: ob Notizen **ohne** Frontmatter existieren. Alles andere sieht niemand.
Am 2026-10-31 zeigte sich, was das kostet:

- 432 Notizen fehlten seit Wochen im Brain-Index, ohne dass es jemand merkte —
  der Indexer meldete 0 Fehler (behoben in `7ea6843b4`).
- 6 Notizen haben **ungültiges** YAML-Frontmatter. Der Tagger hält sie für
  in Ordnung, weil Frontmatter vorhanden ist; der Indexer kann sie nicht lesen.

Ziel ist ein Maintainer, der die Struktur des Vaults **überwacht** und
**Verbesserungen vorschlägt** — mit Belegen, nicht mit Behauptungen.

## Leitplanke aus dem Oktober

Vom 22.08. bis 03.10.2026 hat der Agent 35 Erfolge erfunden. Daraus folgt die
Architektur, die schon beim Tagger trägt und hier übernommen wird:

- **Ein Skript prüft, der Agent berichtet.** Der Agent durchsucht den Vault
  nicht, er liest eine Status-Datei und zitiert deren Rohwerte.
- **Belegpflicht.** Jede Zahl im Issue-Kommentar stammt aus der Status-Datei
  dieses Laufs. Ein Kommentar ohne Rohwerte ist ungültig.

## Ist-Stand (Scan des Spiegels am 2026-10-31)

| Befund | Anzahl | Herkunft (vermutet) |
|---|---:|---|
| YAML-Frontmatter ungültig | 6 | n8n-Kontakte/Termine-Workflow schreibt `\,` und bricht Zeilen falsch |
| `typ` nicht in der Vorlage | 1.677 | Dokumenten-Import schrieb den Ordnerpfad in `typ`, den Typ in `subtyp`; ChatGPT-Import nutzt `typ: Chat` (374) |
| `tags` außerhalb 2–6 Einträge | 1.699 | gemischt |
| `status` nicht in der Vorlage | 12 | Hand-Notizen im Buchprojekt (`Offen`) |
| Wikilinks ohne Ziel | 819 | überwiegend Import-Reste (`[[Bearbeiten`, `[[mailto:`, `[[http`), Rest unklar |
| Gleicher Dateiname in mehreren Ordnern | 64 | Kopien zwischen Buchprojekt-Ordnern |
| Notizen > 2 MB (nicht indiziert) | 16 | E-Mails mit eingebetteten Anhängen |
| Leere Notizen | 1 | — |
| Notizen ohne Frontmatter | 1 | — |
| Dateien in der Vault-Wurzel | 1 | `_status.md`, bekannt |

Gesamt: 17.542 Notizen. Die großen Zahlen sind **wenige systematische Muster**,
keine tausend Einzelfehler. Der Bericht muss sie deshalb nach Muster gruppieren.

## Ziele

1. Jede Nacht ein vollständiger Strukturbefund mit Zahlen pro Prüfung.
2. Befunde nach **Ursache** gruppiert, mit dem Werkzeug, das sie erzeugt
   (n8n-Workflow, Import, Hand). Behoben wird an der Quelle, nicht im Vault.
3. **Änderungen** gegenüber dem Vortag stehen vorn — ein neuer Fehler fällt auf,
   auch wenn 1.677 alte daneben stehen.
4. Verbesserungsvorschläge als Liste, die Walter freigibt, bevor irgendetwas
   im Vault geändert wird.

## Nicht-Ziele

- Der Agent ändert keine Dateien, verschiebt nichts, löscht nichts.
- Keine Bewertung von Inhalten (Songtexte, Buchprojekt) — nur Struktur.
- Keine Umorganisation der Ordner.
- Kein LLM im Prüfpfad. Alle Prüfungen sind deterministisch.
- Vorerst nur Claras Vault; der WHITESTAG-Vault folgt, wenn sich das bewährt.

## Anti-Ziele (wäre ein Fehlschlag, auch wenn es läuft)

- Ein Bericht mit „alles in Ordnung", der die Status-Datei nicht gelesen hat.
- Alarmmüdigkeit: täglich dieselben 1.677 Zeilen, in denen ein neuer Fehler
  untergeht.
- Massenänderungen an Claras Texten ohne Liste und Freigabe.

## Aufbau

```
01:30  de.whitestag.vault-tagger-clara     (besteht)  setzt fehlendes Frontmatter
01:45  de.whitestag.vault-pruefer-clara    (neu)      prüft, schreibt Status + Bericht
02:00  Vault-Maintainer, Routine           (besteht)  liest beide Status-Dateien, berichtet
```

### Der Prüfer (`tools/vault-pruefer-clara/`)

- **node**, wie der Tagger und aus demselben Grund (launchd-zsh kommt nicht an SMB).
- **Liest den lokalen Spiegel** `~/.paperclip/clara-vault-mirror`, nicht das NAS:
  schnell, keine SMB-Timeouts, und der Spiegel ist höchstens 15 Minuten alt.
  Vorher prüfen, dass der letzte Sync in `clara-mirror-sync.log` `OK` meldet und
  jünger als 60 Minuten ist — sonst `exit_code` 3.
- **Frontmatter mit `gray-matter` parsen**, also mit derselben Bibliothek wie der
  Brain-Indexer. „Gültig" heißt damit genau „vom Index lesbar".
- **Erwartete Werte aus der Vorlage** `obsidian-tagger/templates/frontmatter-template-clara.yaml`
  lesen (`typen`, Status-Werte, Tag-Grenzen), nicht im Code fest verdrahten.

### Prüfungen

| ID | Prüfung | Stufe |
|---|---|---|
| P1 | Frontmatter vom Index nicht lesbar | hoch |
| P2 | Notiz fehlt im Brain-Index oder hat dort keine Chunks (Abgleich mit `paperclip_brain_clara`, abzüglich bewusster Ausschlüsse und > 2 MB) | hoch |
| P3 | `typ` nicht in der Vorlage — gruppiert nach Wert | mittel |
| P4 | `status` nicht in der Vorlage | mittel |
| P5 | `tags` fehlt oder außerhalb 2–6 | niedrig |
| P6 | Wikilink ohne Ziel — getrennt in *echt* und *Import-Rest* (`http`, `mailto`, `Bearbeiten`) | mittel / niedrig |
| P7 | Gleicher Name in mehreren Ordnern — getrennt in *inhaltsgleich* (Hash) und *nur namensgleich* | niedrig |
| P8 | Notiz > 2 MB, leere Notiz, Datei in der Wurzel | niedrig |

Jede Prüfung trägt im Code eine Zuordnung zur vermuteten Quelle, z. B.
P1 → „n8n Clara-Kontakte-Workflow", damit der Bericht sagt, wo zu reparieren ist.

### Ausgaben

1. **Status-Datei** `~/.paperclip/logs/vault-pruefer-clara-last.json`:
   `timestamp`, `exit_code`, `notizen_gesamt`, je Prüfung `anzahl` und
   `delta_vortag`, plus `neu_hoch` (Summe neuer Befunde der Stufe hoch) und
   `report_path`. Das ist alles, was der Agent liest.
2. **Bericht** im Vault unter `Paperclip/_Meta/Vault-Pruefer-Reports/<datum>.md`:
   oben die Änderungen zum Vortag, dann je Prüfung Anzahl, Quelle und bis zu
   10 Beispielpfade. Schreiben auf das NAS wie der Tagger.
3. **Vollständige Listen** lokal unter `~/.paperclip/state/vault-pruefer-clara/<datum>/P<n>.txt`
   — Grundlage für jede spätere Korrektur (Regel „nur nach Liste").
4. **Vortags-Stand** `~/.paperclip/state/vault-pruefer-clara/letzter-stand.json`
   für die Deltas. Der erste Lauf setzt die Baseline; `delta_vortag` ist dann `null`.

`exit_code`: 0 ok · 3 Spiegel veraltet oder nicht lesbar · 4 Index-DB nicht
erreichbar (P2 übersprungen, Rest läuft) · 124 Timeout. Bei ≠ 0 eine Mail an
ws@ über den Mailhub, wie beim Tagger.

### Der Agent

Die bestehende Routine „Clara-Vault Frontmatter-Pflege" wird zu
„Clara-Vault-Pflege" und liest **beide** Status-Dateien. Die AGENTS.md bekommt
einen zweiten Block mit derselben Belegpflicht:

- Rohwerte zitieren: `timestamp`, `exit_code`, je Prüfung `anzahl` und
  `delta_vortag`, `report_path`.
- `done`, wenn beide Läufe von heute sind, `exit_code` 0 und `neu_hoch` = 0.
- `blocked`, wenn ein Lauf fehlt, `exit_code` ≠ 0 oder `neu_hoch` > 0 —
  im letzten Fall mit den Prüfungen, die gestiegen sind.
- Weiterhin verboten: Vault auflisten, Dateien ändern, Skripte starten.

## Verbessern — zweite Ausbaustufe

Überwachen kommt zuerst; Korrekturen erst, wenn die Befunde ein paar Nächte
stabil aussehen. Dann gilt:

1. **An der Quelle zuerst.** P1 wird im n8n-Workflow behoben (neue Version nach
   Versionierungsregel), nicht in den sechs Dateien.
2. **Mechanische Korrekturen nur nach Liste und Freigabe.** Kandidat Nr. 1 ist
   P3: `typ: <Ordnerpfad>` + `subtyp: <Typ>` → `typ: <Typ>`, Ordnerpfad bleibt in
   `projekt`. Ablauf: Prüfer erzeugt die Liste → Agent legt ein Issue mit
   Approval an → nach Walters Freigabe arbeitet ein Skript genau diese Liste ab,
   mit Sicherung unter `_Backup_<datum>_<zweck>/` auf dem NAS.
3. **Nie automatisch:** Dubletten zusammenführen, Dateien verschieben oder
   löschen, Inhalte umschreiben. Das bleibt Vorschlag im Bericht.

## Was der Builder entscheidet

- Interne Struktur des Skripts, Ausgabeformat der Listen, Wortlaut des Berichts.
- Genaue Regeln für „Import-Rest" bei P6, sofern `http`, `mailto` und
  `Bearbeiten` abgedeckt sind.
- Tests: mindestens je Prüfung ein Fixture-Fall, plus Baseline/Delta.

## Eigene Entscheidungen in diesem Entwurf (von Walter noch nicht bestätigt)

- Spiegel statt NAS als Lesequelle.
- Startzeit 01:45 und Erweiterung der bestehenden Routine statt einer neuen.
- Einstufung hoch/mittel/niedrig und dass nur neue „hoch"-Befunde `blocked` auslösen.
- P3-Typ-Normalisierung als erste Korrektur der zweiten Stufe.
