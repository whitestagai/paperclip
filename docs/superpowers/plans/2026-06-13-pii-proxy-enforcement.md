# PII-Proxy-Durchsetzung Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Aller Cloud-LLM-Egress der Paperclip-claude_local-Agenten (und vorbereitet OpenAI) läuft anonymisiert über den lokalen PII-Proxy auf :4711, fail-closed bei Proxy-Ausfall.

**Architecture:** Den fertigen Passthrough-Server `@whitestag/pii-proxy-server` (Monorepo `opensource/pii-proxy`) als kanonischen :4711-Dienst in Betrieb nehmen (ersetzt den alten `paperclip-dpo-service`), die 3 claude_local-Agenten per `ANTHROPIC_BASE_URL` auf den `noAuth`-Passthrough zeigen, danach Enforcement über einen neuen Paperclip-Host-Hook (`onBeforeAdapterExecute` + Plugin-`required`-Mode) ergänzen und OpenAI vorbereiten.

**Tech Stack:** TypeScript, Fastify (DPO-Service), Node 22, launchd (macOS), Paperclip Control-Plane API (:3100), pnpm/tsc, vitest.

**Spec:** [docs/superpowers/specs/2026-06-13-pii-proxy-enforcement-design.md](../specs/2026-06-13-pii-proxy-enforcement-design.md)

---

## Stehende Regeln (für ALLE Tasks)

- **Opensource zuerst lesen.** Vor jeder Änderung die einschlägigen Quellen in
  `opensource/pii-proxy`, `opensource/paperclip-plugin-pii-proxy`, `opensource/paperclip-dpo`
  lesen. Jede Änderung an Plugin/Server wird **doppelt** gepflegt: kanonische opensource-Quelle
  (korrekter Branch) **und** installierte/laufende Kopie.
- **Live-Eingriffe einzeln bestätigen.** Jeder mit 🚦 **STOP** markierte Schritt (Dienst-Swap,
  Agent-Env, Server-Build, Neustarts) wird **vor** Ausführung dem User vorgelegt. Nichts blind
  überschreiben — vorher Backup/Version.
- **Secrets nie loggen / nie ins Issue oder in Git.** `PII_PROXY_SHARED_KEY`,
  `PII_PROXY_MAPPING_KEY_BASE64`, Anthropic-Keys.
- **Pfade (absolut):**
  - Neuer Server: `~/Library/CloudStorage/SynologyDrive-Mac/Claude Code MAC/opensource/pii-proxy`
  - Alter Dienst: `…/opensource/paperclip-dpo-service`
  - Plugin-Quelle: `…/opensource/paperclip-plugin-pii-proxy` (Branch `feat/openai-codex-provider`)
  - Plugin installiert: `~/.paperclip/plugins/whitestag.pii-proxy/`
  - Paperclip-Server: `…/Claude Code MAC/Paperclip/server`
  - Board-Token: `~/.paperclip/auth.json` → `credentials["http://localhost:3100"].token`
  - Company WHITESTAG: `9cebf3cf-efe8-4597-a400-f06488900a87`
  - claude_local-Agenten: `dfa8d0e2-d48a-4342-82c2-f7cf6de9d562` (n8n-Betriebsingenieur),
    `f4bf1c83-9c79-4864-87eb-dd8c22fa604d` (Bild & Video),
    `caaeb345-9db1-41ab-95a3-115d3c70cf34` (Link-Detektor)

---

## Task 1: Neuen Passthrough-Server bauen & smoke-testen (noch nicht installieren)

**Files:**
- Read: `opensource/pii-proxy/packages/server/src/{server,config}.ts`, `scripts/install-service.mjs`, `scripts/lib/paths.mjs`, `scripts/generate-shared-key.mjs`, `scripts/smoke.mjs`
- Build only (kein Live-Eingriff)

- [ ] **Step 1: Quellen lesen** — die obigen Dateien plus `routes/anthropic-passthrough.ts`, `routes/openai-chat-passthrough.ts`, `auth.ts`.

- [ ] **Step 2: Build**

```bash
cd "$HOME/Library/CloudStorage/SynologyDrive-Mac/Claude Code MAC/opensource/pii-proxy"
pnpm install
pnpm -r build   # baut packages/core + packages/server
```
Expected: `packages/server/dist/index.js` existiert, kein tsc-Fehler.

- [ ] **Step 3: Unit-/Route-Tests des Servers laufen lassen**

```bash
cd "$HOME/Library/CloudStorage/SynologyDrive-Mac/Claude Code MAC/opensource/pii-proxy/packages/server"
pnpm test
```
Expected: PASS (inkl. anthropic-/openai-passthrough Tests).

- [ ] **Step 4: Secrets generieren (nur erzeugen, sicher ablegen, NICHT loggen)**

```bash
SHARED_KEY=$(node scripts/generate-shared-key.mjs)          # base64url, 32 Bytes
MAPPING_KEY=$(node -e "console.log(require('crypto').randomBytes(32).toString('base64'))")
```
In eine 0600-Env-Datei schreiben, z.B. `~/.pii-proxy.env` (nicht in Git, nicht ins Vault):
`PII_PROXY_SHARED_KEY`, `PII_PROXY_MAPPING_KEY_BASE64`, `PII_PROXY_BIND=127.0.0.1`.
Expected: `chmod 600 ~/.pii-proxy.env`; Datei nicht in einem Git-Repo.

- [ ] **Step 5: Server lokal probeweise starten (Fremd-Port, kollidiert nicht mit :4711)**

```bash
PII_PROXY_PORT=4712 PII_PROXY_BIND=127.0.0.1 \
PII_PROXY_SHARED_KEY="$SHARED_KEY" PII_PROXY_MAPPING_KEY_BASE64="$MAPPING_KEY" \
node dist/index.js &
sleep 1
curl -s http://127.0.0.1:4712/health
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://127.0.0.1:4712/anthropic/v1/messages \
  -H "content-type: application/json" -d '{"model":"x","messages":[]}'
kill %1
```
Expected: `/health` → `{"status":"ok",...}`; `/anthropic/v1/messages` ohne Anthropic-Auth → **401 mit `authentication_error`** (NICHT „missing X-DPO-Key") → beweist: Passthrough ist `noAuth`, Auth ist Anthropic-seitig.

- [ ] **Step 6: Commit (opensource-Repo)**

```bash
cd "$HOME/Library/CloudStorage/SynologyDrive-Mac/Claude Code MAC/opensource/pii-proxy"
git add -A && git commit -m "chore: build + verify passthrough server before service swap"
```

---

## Task 2: 🚦 Dienst-Swap — alten DPO-Dienst sichern & stilllegen, neuen installieren

**Files:**
- Backup: aktueller Startweg/Plist des alten `paperclip-dpo-service`
- Create (via Script): `~/Library/LaunchAgents/io.piiproxy.server.plist`

- [ ] **Step 1: 🚦 STOP — User bestätigen lassen** (Dienst-Swap auf :4711, betrifft laufende Anonymisierungs-Infra).

- [ ] **Step 2: Alten Dienst identifizieren & sichern**

```bash
lsof -nP -iTCP:4711 -sTCP:LISTEN          # PID des alten Dienstes
ls ~/Library/LaunchAgents | grep -iE "dpo|pii|4711"   # alte plist finden
# gefundene plist + zugehörige Start-/Env-Dateien nach ~/pii-proxy-backup-2026-06-13/ kopieren
```
Expected: alte plist gesichert; Notiz, wie der alte Dienst gestartet wurde (`DPO_*`-Env).

- [ ] **Step 3: Alten Dienst stoppen**

```bash
launchctl unload ~/Library/LaunchAgents/<alte-dpo>.plist   # exakter Name aus Step 2
# Fallback falls kein launchd: den in Step 2 gefundenen PID-Prozess gezielt beenden
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:4711/health   # erwartet: 000 (down)
```
Expected: :4711 nicht mehr erreichbar.

- [ ] **Step 4: Neuen Dienst installieren (launchd, Port 4711, lokal gebunden)**

```bash
cd "$HOME/Library/CloudStorage/SynologyDrive-Mac/Claude Code MAC/opensource/pii-proxy/packages/server"
set -a; source ~/.pii-proxy.env; set +a   # lädt SHARED_KEY, MAPPING_KEY, BIND
PII_PROXY_PORT=4711 npm run service:install
```
Expected: `Installed … io.piiproxy.server.plist`, `launchctl load -w` ok.

- [ ] **Step 5: Verifizieren**

```bash
sleep 1
curl -s http://localhost:4711/health
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:4711/anthropic/v1/messages \
  -H "content-type: application/json" -d '{"model":"x","messages":[]}'
cd "$HOME/…/opensource/pii-proxy/packages/server" && npm run service:smoke
```
Expected: `/health` ok+classifier reachable; `/anthropic/v1/messages` → 401 `authentication_error`; smoke grün.

- [ ] **Step 6: Update Memory** — `project_n8n_*`/neuen Memory-Eintrag: „:4711 ist jetzt
  `io.piiproxy.server` (pii-proxy Monorepo), alter `paperclip-dpo-service` stillgelegt; Passthrough `noAuth`."

---

## Task 3: 🚦 Die 3 claude_local-Agenten auf den Proxy verdrahten (Option A)

**Files:**
- Read: `server/src/adapters/process/execute.ts:22-26` (Env-Merge bestätigt), `server/src/routes/agents.ts:2538-2633` (PATCH /agents/:id merged adapterConfig; `env` erlaubt)
- Mutate (API): `PATCH http://localhost:3100/agents/:id`

- [ ] **Step 1: 🚦 STOP — User bestätigen** (Live-Agent-Env-Änderung; n8n-Betriebsingenieur betroffen).

- [ ] **Step 2: Backup der 3 Agent-Configs**

```bash
TOKEN=$(python3 -c "import json,os;print(json.load(open(os.path.expanduser('~/.paperclip/auth.json')))['credentials']['http://localhost:3100']['token'])")
mkdir -p ~/pii-proxy-backup-2026-06-13
for ID in dfa8d0e2-d48a-4342-82c2-f7cf6de9d562 f4bf1c83-9c79-4864-87eb-dd8c22fa604d caaeb345-9db1-41ab-95a3-115d3c70cf34; do
  curl -s -H "Authorization: Bearer $TOKEN" "http://localhost:3100/agents/$ID" \
    > ~/pii-proxy-backup-2026-06-13/agent-$ID.json
done
```
Expected: 3 JSON-Backups vorhanden.

- [ ] **Step 3: `ANTHROPIC_BASE_URL` je Agent setzen (merged PATCH, env ersetzt — aktuell leer)**

```bash
for ID in dfa8d0e2-d48a-4342-82c2-f7cf6de9d562 f4bf1c83-9c79-4864-87eb-dd8c22fa604d caaeb345-9db1-41ab-95a3-115d3c70cf34; do
  curl -s -X PATCH -H "Authorization: Bearer $TOKEN" -H "content-type: application/json" \
    "http://localhost:3100/agents/$ID" \
    -d '{"adapterConfig":{"env":{"ANTHROPIC_BASE_URL":"http://localhost:4711/anthropic"}}}'
  echo
done
```
Expected: je 200; Antwort zeigt `adapterConfig.env.ANTHROPIC_BASE_URL` gesetzt.

- [ ] **Step 4: Verifizieren (read-back)**

```bash
for ID in dfa8d0e2-… f4bf1c83-… caaeb345-…; do
  curl -s -H "Authorization: Bearer $TOKEN" "http://localhost:3100/agents/$ID" \
    | python3 -c "import sys,json;a=json.load(sys.stdin);print(a['id'], a.get('adapterConfig',{}).get('env'))"
done
```
Expected: jeder Agent zeigt `{'ANTHROPIC_BASE_URL': 'http://localhost:4711/anthropic'}`.

---

## Task 4: End-to-End-Verifikation + Fail-Closed-Test (DoD-Kern)

**Files:** PII-Proxy-Audit-Log unter `dataDir("pii-proxy")/audit/`

- [ ] **Step 1: Realen Agent-Lauf auslösen** (kleinster sicherer Trigger)

```bash
curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  "http://localhost:3100/agents/caaeb345-9db1-41ab-95a3-115d3c70cf34/heartbeat/invoke"
```
Expected: Lauf startet (200/202).

- [ ] **Step 2: Audit-Log prüfen — anonymisiert raus, deanonymisiert rein**

```bash
ls -t "$HOME/Library/Application Support/pii-proxy/audit/" 2>/dev/null | head
# jüngsten Audit-Eintrag öffnen; verifizieren: Klarnamen→Pseudonym vor Egress, Rückrichtung deanonymisiert
```
Expected: Eintrag zeigt einen `/anthropic`-Call mit Pseudonymisierung; kein Klartext-Name im Upstream-Payload.

- [ ] **Step 3: Fail-Closed-Test**

```bash
launchctl unload ~/Library/LaunchAgents/io.piiproxy.server.plist   # Proxy stoppen
curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  "http://localhost:3100/agents/caaeb345-9db1-41ab-95a3-115d3c70cf34/heartbeat/invoke"
# Agent-Run-Log prüfen: claude-CLI scheitert an toter Base-URL → KEIN api.anthropic.com-Egress
launchctl load -w ~/Library/LaunchAgents/io.piiproxy.server.plist   # Proxy wieder hoch
```
Expected: Lauf schlägt mit Connection-Refused auf :4711 fehl; **kein** direkter Anthropic-Call.

- [ ] **Step 4: Ergebnis dokumentieren** — kurzer Verifikations-Vermerk (Pfade, Audit-Auszug ohne Klarnamen) im Spec-Ordner.

---

## Task 5: OpenAI-Inventur & Vorbereitung (Option C)

**Files:**
- Read: `opensource/pii-proxy/packages/server/src/routes/openai-chat-passthrough.ts`, `opensource/paperclip-plugin-pii-proxy/src/provider-map.ts`
- Modify (falls OpenAI-Agenten existieren): `provider-map.ts` (Quelle + installierte Kopie)

- [ ] **Step 1: Inventur** — gibt es `codex_local`/OpenAI-Agenten oder n8n-Workflows mit direktem OpenAI-Call?

```bash
curl -s -H "Authorization: Bearer $TOKEN" "http://localhost:3100/companies/9cebf3cf-efe8-4597-a400-f06488900a87/agents" \
  | python3 -c "import sys,json;[print(a.get('id'),a.get('name'),a.get('adapterType')) for a in (json.load(sys.stdin) or [])]" | grep -iE "codex|openai" || echo "kein OpenAI-Agent"
grep -rilE "api.openai.com|OPENAI_API_KEY|chat/completions" ~/.n8n 2>/dev/null | head || echo "kein n8n-OpenAI-Direktcall gefunden"
```
Expected: Liste vorhandener OpenAI-Egress-Pfade (oder „keiner").

- [ ] **Step 2 (nur falls OpenAI-Agent existiert): Provider-Map erweitern — TDD**

Test in `opensource/paperclip-plugin-pii-proxy/tests/` ergänzen:
```ts
it("maps codex_local to OPENAI_BASE_URL /openai/v1", () => {
  const m = resolveAdapterProviderMapping("codex_local", ["openai"]);
  expect(m).toEqual({ envVar: "OPENAI_BASE_URL", path: "/openai/v1", provider: "openai" });
});
```
Run: `pnpm test` → erst FAIL.

- [ ] **Step 3 (falls Step 2): Implementieren** — in `src/provider-map.ts` den Phase-2-Kommentar aktivieren:
```ts
codex_local: { envVar: "OPENAI_BASE_URL", path: "/openai/v1", provider: "openai" },
```
Run: `pnpm test` → PASS. Build, dann in installierte Kopie `~/.paperclip/plugins/whitestag.pii-proxy/dist/` spiegeln.

- [ ] **Step 4: Doku** — Coverage-Matrix-Eintrag: OpenAI verdrahtet **oder** „derzeit kein OpenAI-Egress; Mechanik bereit".

---

## Task 6: 🚦 Enforcement — Host-Hook `onBeforeAdapterExecute` + `required`-Mode (Option B)

> Letzter, separater Schritt. Einziger echter Neubau im Paperclip-Server. Plugin-Seite ist
> fertig: `worker.ts` exportiert bereits `onBeforeAdapterExecute(input,…)` → `handleBeforeAdapterExecute`.

**Files:**
- Read: `server/src/services/plugin-loader.ts`, `plugin-worker-manager.ts`, `plugin-registry.ts`, `plugin-tool-dispatcher.ts`; `server/src/adapters/process/execute.ts`, `server/src/adapters/registry.ts`; `opensource/paperclip-plugin-pii-proxy/src/{worker,hook-logic,mode-resolver}.ts`
- Modify: Adapter-Execute-Pfad (`server/src/adapters/process/execute.ts` + Aufrufer in `heartbeat.ts`/`registry.ts`), Plugin-Worker-Manager (neuer RPC-Aufruf)
- Test: neue Integrationstests im Paperclip-Server

- [ ] **Step 1: 🚦 STOP — User bestätigen** (Server-Build + kontrollierter Neustart; Env-Var-Falle).

- [ ] **Step 2: Spike (≤30 min) — Worker-RPC-Kontrakt kartieren.** Konkretes Deliverable: kurze
  Notiz, **wo** im Execute-Pfad (vor `runChildProcess` in `execute.ts:47`) der Hook aufgerufen wird
  und **wie** der Worker-Handler `onBeforeAdapterExecute` via `plugin-worker-manager` erreichbar ist
  (Handler-Registrierung + Capability). Ablage: `docs/superpowers/specs/2026-06-13-host-hook-notes.md`.

- [ ] **Step 3: Failing-Test — Hook injiziert env**

Integrationstest: Adapter-Execute mit aktivem pii-proxy-Plugin (Mode `required`, Proxy erreichbar)
→ erwartet, dass `ANTHROPIC_BASE_URL` in der Child-Env landet. Run → FAIL (Hook existiert nicht).

- [ ] **Step 4: Failing-Test — Hook blockt bei Proxy-Ausfall (`required`)**

Integrationstest: Proxy unreachable + Mode `required` → erwartet Run-`block` (`pii_proxy_unreachable`),
kein Spawn. Run → FAIL.

- [ ] **Step 5: Implementieren** — `onBeforeAdapterExecute`-Aufrufpunkt in `execute.ts` vor
  `runChildProcess`; Ergebnis anwenden: `env`-Merge in `env`-Objekt (Zeile 22-25) bzw. bei `block`
  Abbruch mit Fehler. Worker-Manager: RPC zum Plugin-Worker-Handler. Run Step 3+4 → PASS.

- [ ] **Step 6: Plugin-Config auf `required` + `failClosedOnUnreachable=true`**
  (installierte Instanz **und** opensource-Default-Doku). Verifizieren via Plugin-Config-Read.

- [ ] **Step 7: 🚦 Kontrollierter Server-Neustart** (Env-Vars Pflicht — siehe Memory
  `project_n8n_versioning_and_restart`/Paperclip-Startweg). Danach: neuer Test-`claude_local`-Agent
  **ohne** env anlegen → Heartbeat → verifizieren, dass er automatisch über :4711 geroutet wird;
  Proxy-Stop → Run wird geblockt. Test-Agent danach entfernen.

- [ ] **Step 8: Commit** (Paperclip-Server-Branch + opensource-Plugin synchron).

---

## Task 7: Source-Sync-Audit & Abschluss-Dokumentation

- [ ] **Step 1: Sync-Audit** — diff zwischen `opensource/paperclip-plugin-pii-proxy/dist` und
  `~/.paperclip/plugins/whitestag.pii-proxy/dist`; sicherstellen, dass keine Divergenz bleibt.
- [ ] **Step 2: README-Korrektur** — in der installierten Plugin-README den Passthrough-Auth-Hinweis
  an die Realität (`noAuth`) anpassen; gleiche Korrektur in opensource.
- [ ] **Step 3: Coverage-Matrix schreiben** (in den Spec-Ordner): abgedeckt = claude_local ✅,
  codex_local/OpenAI (✅ oder „keiner"); **offen** = n8n-Direkt-LLM-Calls, andere Provider (Gemini …).
  Plus nächste Schritte für vollständige „ALLE"-Abdeckung.
- [ ] **Step 4: Memory aktualisieren** — neuer/aktualisierter Memory-Eintrag zum PII-Proxy-Stand.

---

## Self-Review (Plan ↔ Spec)

- **Spec-Coverage:** W1→Task 1-2, W2→Task 3, W5-Verifikation→Task 4, W4→Task 5, W3→Task 6,
  W5-Sync/Doku→Task 7. Alle Spec-Abschnitte abgedeckt.
- **Reihenfolge:** entspricht Spec §5 (W1→W2→Verifikation→W4→W3).
- **Fail-Closed:** Task 4 Step 3 (Base-URL-Pinning) + Task 6 Step 4/7 (`required`-Block) — beide getestet.
- **Secrets:** nur generiert/in 0600-Env, nie geloggt — Task 1 Step 4.
- **Live-Gates:** Tasks 2, 3, 6 mit 🚦 STOP markiert.
