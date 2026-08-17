# Übergabe-Prompt: Websuche-Dienst & Recherche-Agenten weiterführen

*Stand 2026-08-17. In neuen Chat kopieren, um nahtlos weiterzumachen.*

---

Wir haben einen **lokalen Websuche-Dienst** gebaut, damit die Recherche-Agenten
von `claude_local` auf lokale Modelle wechseln konnten. Der Bau ist fertig und
live, die Migration ist durch. Es bleiben drei Punkte.

## Was existiert

**`tools/websuche/`** (Python 3.11, eigenes venv), deployt nach
`~/.paperclip/scripts/websuche/` per `zsh deploy.sh`. **145 Tests**, laufen ohne
Netz: `cd tools/websuche && ./venv/bin/pytest -q`.

Module: `backends.py` (Suchquelle, `SearxngBackend`), `abruf.py` (Seite holen,
robots.txt, Textextraktion), `websuche.py` (Orchestrierung, Domain-Dedup,
Deadline), `cli.py` (für Agenten), `server.py` (HTTP `127.0.0.1:7789` für n8n und
die Sprachbots). Dazu `rauchtest.sh` gegen die echten Dienste und `DEPLOY.md`.

**SearXNG** liegt als gepinnter Checkout unter `~/.paperclip/dienste/searxng`,
läuft auf `127.0.0.1:8888`, JSON-API in `settings-whitestag.yml` freigeschaltet.

**Zwei LaunchAgents:** `de.whitestag.searxng`, `de.whitestag.websuche`.
Logs unter `~/.paperclip/logs/`.

**Zweig:** `feat/websuche-dienst` (aus `feat/wake-word-jarvis-satellite`
herausgelöst, beide synchron mit `fork` = whitestagai).

**Spec und Plan:** `docs/superpowers/specs/2026-08-10-websuche-design.md`,
`docs/superpowers/plans/2026-08-10-websuche.md`.

## Was erledigt ist

- **Migration:** Online-Rechercheur (WHITESTAG, `d80fe6b9-b2ac-4d58-8525-8bbbb1d0caf7`)
  und Recherche (Clara Sound, `f2d73a54-dce9-493a-998a-71e7c127f61e`) laufen auf
  `lmstudio_local` / `qwen3.6-35b-a3b-mlx`, Fallback `gemma-4-31b-it-mlx`.
  Zusammen ~1,2 Mio. Output-Token im Monat, die kein Abo-Kontingent mehr ziehen.
- **Aufrufanleitung:** für WHITESTAG in `_common.md` des Generators (also für
  **alle** lokalen Agenten), für Clara direkt in deren `AGENTS.md`.
- **Modellvergleich** über zehn Recherchefragen:
  `docs/superpowers/2026-08-17-recherchemodell-vergleich.md`. Ergebnis: qwen3.6
  bleibt, qwen3.8-27b bringt nichts.
- **Lektorat** (`3deca5b4-af4b-43a3-93f4-2cc4fc1bd08d`) läuft seit 10.08. auf
  `gemma-4-31b-it-mlx`.

## OFFENE AUFGABEN

**1. Kontextfenster von qwen3.6 (Walters Entscheidung, dann messen)**

Das Modell läuft mit **262144** statt der gewünschten 98304. Ursache ist belegt:
`defaultContextLength` in `~/.lmstudio/settings.json` steht auf `{"type": "max"}`.
LM Studios Auto-Anpassung liest den angeforderten Wert beim Laden **gar nicht** —
weder aus dem Modell-Dialog, noch aus der gespeicherten Modellvorgabe
(`~/.lmstudio/.internal/user-concrete-model-default-config/unsloth/Qwen3.8…json`
enthält korrekt 98304), noch aus `lms load -c`. Im Log steht bei jedem Laden
`Model context auto-fit: max=262,144 fitted=262,144`.

Die Einstellung sitzt in den **App-Einstellungen**, nicht im Modell-Dialog. Nicht
in der laufenden App per Datei ändern — LM Studio schreibt `settings.json` beim
Beenden neu.

Danach: qwen3.6 einmal neu laden (13 Agenten hängen dran, also in einer ruhigen
Minute) und nachmessen, ob 98304 stehenbleiben. Der A/B-Aufbau im Scratchpad ist
weg; die Messmethode steht im Vergleichsdokument.

Nebenbefund: `load()` in `~/Desktop/n8n.sh` bricht bei bereits geladenem Modell
ab (`schon geladen`) und wendet sein `-c` nie an. Das Preload-Log
(`~/.whitestag-logs/lmstudio-preload.log`) zeigt in 13 Läufen **keine einzige**
`lade:`-Zeile — der als „Root-Cause-Fix 2026-07-18" kommentierte Block hat seine
Kontextwerte vermutlich nie angewendet. Letzter Lauf: 29.07.

**2. Kopfzeilen-Phase im Seitenabruf härten**

`abruf.py` hat einen Socket-Wächter, der aufgegebene Abrufe im Rumpf zuverlässig
abbricht (gemessen: gzip-Leerblöcke 30,0 → 1,01 s, chunked-Größenzeile
20,1 → 1,01 s). **Die Kopfzeilen-Phase ist ausgenommen**, weil sie in
`requests.get` läuft und dort noch kein Socket zum Zuklappen existiert. Ein
Server, der gültige Kopfzeilen tröpfelt, kommt auf **20,54 s bei 1,0 s Budget**
(begrenzt nur durch `http.client._MAXHEADERS`).

Messwerte und Grenze stehen im Modul-Docstring von `abruf.py` und im Kommentar in
`websuche.py`. Solange das offen ist, trägt auch die Begründung nicht, warum es
keinen Wächter über die Abruf-Threads gibt — im Dienst (nicht im CLI, dort räumt
`os._exit` auf) kann ein hängender Thread bestehen bleiben. Sichtbarkeit ist
hergestellt: Zähler, stderr-Meldung mit URL und Laufzeit, Ausweis unter
`GET http://127.0.0.1:7789/`.

**3. Lektorat: erstes echtes Prüf-Issue**

Läuft seit 10.08. lokal, **ohne dass je ein Prüfauftrag durchgelaufen wäre**. Die
Rolle lädt ihr Prüfprofil aus dem Vault (`Paperclip/_Meta/lektorat/pruefprofile/
<typ>.md`, Typen `kurs`, `angebot`, `pressemitteilung`, `newsletter`, `webtext`,
`seo-meta`) und postet ein Urteil als Issue-Kommentar. Ein Auftrag mit einem
echten Deliverable würde zeigen, ob gemma das Profil sauber abarbeitet — beim
Websuche-Test hat erst der reale Durchlauf die interessanten Fehler zutage
gefördert.

## Gotchas, die Zeit sparen

- **`python3` ist 3.9 und hat kein `bs4`.** Die verbindliche Aufrufzeile für
  Agenten steht in `DEPLOY.md` und lautet
  `~/.paperclip/scripts/websuche/venv/bin/python ~/.paperclip/scripts/websuche/cli.py "<frage>"`.
- **Der Instruktions-Generator** (`~/.paperclip/scripts/agents-instructions/`)
  braucht `PCP_TOKEN` und `PCP_CID` in der Umgebung, und seine Modi haben je ein
  eigenes `return` — `--backup --apply` führt **nur** das Backup aus. Einzeln
  fahren: `--backup`, `--dry-run`, `--apply`, `--verify`.
- **Das Manifest kennt nur WHITESTAG.** Mit Claras Company-ID zeigt der
  Generator im Probelauf dieselben WHITESTAG-Agenten, teils schrumpfend — ein
  `--apply` würde gültige Instruktionen beschädigen. Claras `AGENTS.md` sind
  handgepflegt.
- **`qwen3.6` legt die Antwort oft in `reasoning_content`**, `content` bleibt
  leer — auch bei `finish_reason: stop`. Wer nur `content` liest, hält das für
  einen Ausfall.
- **Denkende Modelle brauchen viel `max_tokens`.** qwen3.6 kam auf 2127 Token,
  qwen3.8-27b auf bis zu 16.581. Der lmstudio-Adapter setzt in der Produktion
  **kein** `max_tokens` — das betrifft nur eigene Testaufbauten.
- **Testskripte mit Schleife auf Modulebene sind eine Falle.** Jeder Import
  startet einen zweiten Lauf gegen dasselbe Modell; Laufzeiten werden wertlos
  und Ergebnisdateien überschrieben. Immer hinter `if __name__ == "__main__"`.
- **`~/.paperclip/scripts/` ist kein Repo.** Quelle ist `tools/<name>/` plus
  `deploy.sh`. Vor jeder Änderung am Live-Stand diffen.
- **`.superpowers/`** ist der git-ignorierte Arbeitsbereich der
  Subagenten-Ausführung (Ledger, Briefs, Review-Pakete). Für diesen Plan:
  `.superpowers/sdd/2026-08-10-websuche/progress.md` — dort steht der komplette
  Verlauf mit allen Funden und Entscheidungen.
