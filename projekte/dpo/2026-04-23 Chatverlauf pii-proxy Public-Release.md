# 2026-04-23 Chatverlauf — pii-proxy Public-Release + DPO-Gate Deployment

## Ausgangslage

Am Vortag (2026-04-21/22) war der DPO-Gate als interner Feature-Branch `feature/dpo-gate-wiring` auf `master` gemerged:
- `paperclip-dpo` (Library) + `paperclip-dpo-service` (Fastify-Server) produktiv
- launchd-Service auf dem Mac Studio, lauscht auf `:4711`, health grün, Smoke-Test OK
- n8n: DPO-Proxy V1 + Luna V11 + CEO V4 importiert, Credentials angelegt, aber Node-Swap in V11/V4 noch UI-Arbeit
- Policy-Doku (`projekte/dpo/DPO-Policy.md`) geschrieben

Offene Fragen zu Session-Beginn: Ist das Ganze OSS-tauglich? Wenn ja, wie?

## Was gemacht wurde

### 1. Brainstorming zum Public-Release
- **Strategie:** Kombination aus Standalone-Repo + Paperclip-Plugin — Standalone erreicht LangChain-/GDPR-Community, Plugin bleibt als Paperclip-Marketing-Vehikel.
- **Weichen gestellt:** b2 (WHITESTAG zurückhaltend als Maintainer), Name `pii-proxy`, d3 (voller Release-Scope inkl. Docker + Python + Blog).
- Spec-Plan geschrieben: [`docs/superpowers/plans/2026-04-22-pii-proxy-release.md`](../../docs/superpowers/plans/2026-04-22-pii-proxy-release.md) — 23 Tasks in 9 Phasen.

### 2. Plan-Execution via Subagent-Driven Development
Alle 23 Tasks durchgezogen:
- **Phase 1–5:** Monorepo-Scaffold (`~/.../opensource/pii-proxy/`) mit `@whitestag/pii-proxy-core` + `@whitestag/pii-proxy-server`, Migration aus `paperclip-dpo*` mit Namespace-Rename (`Dpo` → `PiiProxy`, `DPO_*` → `PII_PROXY_*`, `x-dpo-key` → `x-pii-proxy-key`).
- **Phase 3:** Dockerfile + docker-compose + systemd-Unit + `PII_PROXY_MAPPING_KEY_BASE64`-Fallback für Container (keine Keychain).
- **Phase 4:** Python-Client `pii-proxy` (TDD, 6 Tests, `httpx` sync).
- **Phase 5:** Dokumentation — README, CONFIG, MODELS, INTEGRATIONS, ARCHITECTURE, SECURITY, CoC, CONTRIBUTING.
- **Phase 6:** GitHub Actions CI (TS + Python 3.11–3.13 + Docker-build) + Release-Workflow (changesets + npm + GHCR + PyPI).
- **Phase 7:** Plugin-Repo `paperclip-plugin-pii-proxy` scaffolded (Stub, wartet auf Paperclip-Plugin-SDK).
- **Phase 8:** GitHub-Orgs, Initial-Push beider Repos public.

### 3. CI-Härtung
Iterativ debug + fix:
- pnpm double-version (`packageManager` + action-`version: 9`) → nur `packageManager` nutzen
- Python `F401` in `__init__.py` → `from x import y as y` explicit-reexport pattern
- Python `UP037` (quoted self-type) + `I001` (isort) im Client/Tests
- Dockerfile-Layer-Konflikt: server-node_modules zuerst, Workspace-Symlink entfernen, core-Dist an die Stelle
- npm-Publish 404 → Walter hat Scope von `@whitestag-ai` auf `@whitestag` umgestellt (User-Scope statt Org-Scope; Org existierte nicht unter diesem Namen)
- Release-Workflow-Gate: `published == 'true'` griff nicht nach PR-Merge → auf `publishedPackages != '[]'` umgestellt

### 4. Release v0.2.0 → v0.2.1
- **v0.2.0:** npm erfolgreich, Docker + PyPI wegen falschem Gate skipped
- **v0.2.1 Patch-Bump:** `@whitestag/pii-proxy-core@0.2.1` + `@whitestag/pii-proxy-server@0.2.1` auf npm ✓, `ghcr.io/whitestag-ai/pii-proxy:0.2.1 + :latest` auf GHCR ✓, PyPI self-skipped (kein Token gesetzt)
- GitHub-Releases für beide Versionen automatisch erzeugt

### 5. Auffindbarkeit
- Check: Repo taucht in GitHub-Suche nicht auf
- Grund: Topics-Feld leer
- Fix: 16 Topics auf `pii-proxy` (`gdpr`, `dsgvo`, `pii`, `llm`, `fastify`, `docker` …), 10 Topics auf `paperclip-plugin-pii-proxy`, Homepage-Link beim Plugin

### 6. Mac-Studio-Deployment (Vortag, aber nachgepflegt)
- DPO-Service läuft unter launchd (PID bekannt), health+smoke grün
- n8n-Workflows: DPO-Proxy V1 mit echten Credential-IDs (`dpo-shared-key-cred`, `SDybjlRK1mMEUdG1` für OpenAI), localhost:4711-URL statt Platzhalter
- V11 + V4: Name-Feld korrigiert, aber Node-Swap bleibt Walter-UI-Arbeit

### 7. paperclip-adapter-lmstudio — Status-Check
Walter hat gebeten, den Adapter-Stand zu prüfen:
- Version 1.0.0, **83 Tests grün**
- 14 relevante Commits seit DPO-Wiring-Merge (Fallback-Endpoint mit sticky switch, URL-basierte Models-UI, timeoutSec-honouring, allowedWriteRoots, wallclock run-deadline)
- Produktionsreif, keine Loose Ends

## Relevante geänderte/neue Dateien

### Neu: pii-proxy-Repo (`~/Library/CloudStorage/SynologyDrive-Mac/Claude Code/opensource/pii-proxy/`)
- `packages/core/` + `packages/server/` (migriert aus `paperclip-dpo*`)
- `python/` (neu, TDD)
- `docs/` (CONFIG, MODELS, INTEGRATIONS, ARCHITECTURE, announcements)
- `.github/workflows/ci.yml`, `.github/workflows/release.yml`
- `packages/server/Dockerfile`, `deploy/systemd/`, `deploy/launchd/`

### Neu: `~/.../opensource/paperclip-plugin-pii-proxy/`
Stub mit `src/manifest.ts`, `src/worker.ts`, README

### Geändert im Paperclip-Repo
- `docs/superpowers/plans/2026-04-22-pii-proxy-release.md` (neuer Plan)
- Worktree `.worktrees/dpo-gate-wiring` wurde am Vortag gemerged + entfernt

## Offene Punkte

| Punkt | Status | Wer |
|---|---|---|
| n8n Luna V11 + CEO V4 Node-Swap (OpenAI → Execute-Workflow DPO-Proxy V1) | offen, UI-Arbeit | Walter |
| Windows-CFO-Host Shared-Key-Verteilung | offen | Walter, nur wenn CFO externe LLMs will |
| Telegram-Alerts für DPO-Service | optional | Walter, Bot-Token + `launchctl reload` |
| PyPI-Publish `pii-proxy` | PYPI_TOKEN fehlt | Walter, dann Patch-Bump |
| Social-Preview-Bild für GitHub-Repos | offen | Walter, optional |
| Show-HN / r/LocalLLaMA / LinkedIn-Post | offen | Walter, Blog-Draft liegt in `docs/announcements/2026-04-22-release.md` |
| npm-Debug-Step in `release.yml` | noch drin, kann raus | kleiner Cleanup |

## Live-Links
- https://github.com/whitestag-ai/pii-proxy (16 Topics, public)
- https://github.com/whitestag-ai/paperclip-plugin-pii-proxy (10 Topics, public, Homepage→pii-proxy)
- https://www.npmjs.com/package/@whitestag/pii-proxy-core (0.2.0, 0.2.1)
- https://www.npmjs.com/package/@whitestag/pii-proxy-server (0.2.0, 0.2.1)
- `ghcr.io/whitestag-ai/pii-proxy:0.2.1` + `:latest`

## Memory-Updates dieser Session
- `user_npm_accounts.md` — User `whitestag`, Org `whitestag-ai` (hostet `@whitestag-ai/*` Pakete)
