# Übergabe-Prompt: SEO/GEO-Agent & -Dienst weiterführen

*Stand 2026-07-17. In neuen Chat kopieren, um nahtlos weiterzumachen.*

---

Wir arbeiten seit mehreren Tagen an einem **SEO/GEO-System für WHITESTAGs WordPress-Sites**. Hintergrund + Gotchas stehen in der Memory `project_seo_geo_agent.md` (bitte zuerst lesen). Kurzfassung des Setups:

**Was existiert:**
- **`seo-geo-dienst`** (Python): Repo unter `tools/seo-geo/`, deployt nach `~/.paperclip/scripts/seo-geo/`. Kommandos: `audit`, `resolve`, `validate`, `approve`, `apply` (+`--dry-run`). ~58 Tests, venv unter `tools/seo-geo/venv` (Python 3.11 — System-python3 ist 3.9 und bricht `str|None`). Deploy: `rsync -a --exclude venv --exclude __pycache__ --exclude .pytest_cache tools/seo-geo/ ~/.paperclip/scripts/seo-geo/`.
- **Freigabe-Kette:** `audit → SEO-Agent formuliert → resolve (URL→WP-ID) → validate (hart) → Lektorat (Sprache) → Walter gibt frei → apply → verifizieren`.
- **Zwei Paperclip-Agenten** (WHITESTAG, beide idle): SEO/GEO-Spezialist `9d279c4d-99d6-4797-b28c-cbe5fad996d6` (qwen3.6-35b), Lektorat `3deca5b4-af4b-43a3-93f4-2cc4fc1bd08d` (claude-sonnet-4-6, Prüfprofil `seo-meta` im Vault). Rollen-Quellen: `~/.paperclip/scripts/agents-instructions/roles/{seo-geo-spezialist,lektorat}.role.md`.
- **4 Sites in `sites.json`** (film crawl_limit hoch), Credentials in `~/.whitestag.env` (`WHITESTAG_AI_WP_*`, `WHITESTAG_FILM_WP_*`, `WHITESTAG_DE_WP_*`, `VIRTUELLE_LAUSITZ_WP_*`, Bot-User überall `seo-geo-bot`, Redakteur). mu-Plugin v0.1.0 auf allen 4 Sites installiert (Yoast-Meta REST + /llms.txt).
- Paperclip-Token: `~/.paperclip/auth.json` → `credentials['http://localhost:3100'].token`. Report-Root: `~/.paperclip/seo-geo/<site>/`.
- Git-Branch: `feat/academy-lektor` (die SEO-Commits liegen dort).

**Was ERLEDIGT ist:**
- whitestag.ai: 17 Meta-Änderungen + 32 Alt-Texte **live & verifiziert** (87→47 Findings). H1 Gruppe 1 (Avada-Müll noindex) auf ai+vl erledigt; Gruppe 2/3 bewusst verworfen (Layout-Builder, marginal — Beweis in Chat).
- **Sicherheit:** Alle 4 Sites gehärtet — XML-RPC überall geblockt (403), Kadence Security + Anti-Malware aktiv, IP-Erkennung hinter Cloudflare (nur .ai) repariert. Einbruch bei .ai (Casino-Spam via Konto ID 2) bereinigt.
- **Recherche** SEO/GEO-Monitoring-OSS → `Dokumente/WHITESTAG.AI/Report SEO-GEO Monitoring OSS V1.docx`.

## OFFENE AUFGABEN

**1. whitestag.film-Changeset fertigstellen (am weitesten)**
- Liegt: `~/.paperclip/seo-geo/whitestag.film/pending/changeset-01-resolved.json` (79 Änderungen, `resolve` gelaufen, `validate` **sauber**).
- Nächster Schritt: **Lektorat** darüberlaufen lassen (Issue an Agent 3deca5b4… mit Profil `seo-meta`, Betonung: **zweisprachig DE/EN — Sprache muss zur Seite passen**). Danach Walter-Freigabe → `approve` → `apply` → verifizieren.
- Offen: 1 Startseiten-Änderung (`/`, leerer Slug) ließ sich nicht per resolve zuordnen — separat behandeln.

**2. virtuelle-lausitz.de-Changeset**
- `~/.paperclip/seo-geo/virtuelle-lausitz.de/pending/changeset-01-resolved.json`: nur 5/8 aufgelöst, **4 Descriptions zu kurz** (validate schlägt fehl). Braucht Agent-Korrekturrunde (verlängern) + die 3 unauflösbaren prüfen. Dann Lektorat/Freigabe/apply.

**3. whitestag.de-Changeset**
- Agent hat es NIE gebaut (`pending/` leer). Neu beauftragen (nur 3 Descriptions). Dann resolve/validate/Lektorat/Freigabe/apply.

**4. Alt-Texte für whitestag.film (24 Bilder)**
- Agenten können keine Bilder (Adapter `400 Could not process image`). Für whitestag.ai hat *Claude selbst* die Bilder angesehen und Alt-Texte geschrieben. Für film genauso: Bilder laden (media-IDs aus report), ansehen, Alt-Texte, validate, Lektorat (Profil erlaubt „2b nicht prüfbar"), Freigabe, apply.

**5. Monitoring aufbauen (aus dem Report, empfohlene Reihenfolge)**
- a) **Google Search Console API** anbinden → Wochenbericht-Ampel (größter Hebel, gratis, DSGVO-sauber).
- b) **Audit-Historie + Diff** in den `seo-geo-dienst` einbauen (Momentaufnahme → echtes Monitoring/Alerting).
- c) **GEO-Citation-Check** als Paperclip-Routine (lokale Agenten fragen ChatGPT/Claude/Perplexity Marken-Prompts + KI-Bot-Log-Auswertung GPTBot/ClaudeBot/PerplexityBot).
- d) Backlink-/SERP-Bausteine (Oxylabs-Skript, SerpBear) bei Bedarf.

**6. Wöchentliche Audit-Routine** (Paperclip-Routine, launchd) — noch nicht angelegt.

## WICHTIGE GOTCHAS
- **resolve** ist nötig, weil der Agent `wordpress_id:null` liefert und `page/post` unzuverlässig labelt. `resolve` löst per Slug auf (post/page-Fallback) UND **korrigiert das target** auf den Fundtyp. Portfolio-Einträge (`avada_portfolio`) sind NICHT schreibbar (mu-Plugin deckt nur post+page).
- **validate** macht Live-Check (existiert ID? editierbar?) — fängt u.a. die WP-geschützte Datenschutzseite (403).
- Immer `./venv/bin/python` nutzen, nie System-python3.
- launchd/Hintergrundprozesse können SynologyDrive/CloudStorage nicht lesen → Laufzeit-Code in `~/.paperclip/scripts/`.
- Nach Änderungen an Agenten-Rollen: AGENTS.md **chirurgisch nur für den einen Agenten** neu erzeugen (nicht Fleet-weit `--apply`).

**Bitte zuerst den Ist-Stand verifizieren (pending-Ordner, Agenten-Status, validate) statt aus diesem Text zu schließen — er kann veraltet sein.**
