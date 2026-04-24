# E2E-Test Paperclip ↔ DPO ↔ Anthropic — Befund-Protokoll

**Datum:** 2026-04-24, Spätabend
**Tester:** Walter + Claude
**Scope:** Erstmaliger End-to-End-Roundtrip nach M0–M3-Implementierung
**Ergebnis:** Infrastruktur steht, PII-Schutz **scheiterte beim Upstream-Forward** (401 → Fallback-Umgehung)
**Ausgangs-Spec:** [2026-04-24-paperclip-dpo-integration.md](2026-04-24-paperclip-dpo-integration.md)

---

## 1. Test-Setup

| Komponente | Branch / Version | Status |
|---|---|---|
| Paperclip (`feat/lmstudio-dynamic-models`) | M0 via merge `worktree-paperclip-dpo-m0-hook` | ✅ läuft auf `:3100` |
| `paperclip-dpo-service` | M1-Passthrough + Streaming-Deanonymizer lokal portiert | ✅ läuft auf `:4711`, `/health=ok, classifier=reachable` |
| `paperclip-plugin-pii-proxy` | installiert aus `~/.paperclip/plugins/whitestag.pii-proxy/`, `v0.1.0` | ✅ Status `ready`, Worker aktiv |
| Plugin-Config | `defaultMode: required`, `dpoUrl: http://localhost:4711`, `providers: [anthropic]` | ✅ |
| Buchhalter-Agent | vorübergehend `claude_local` + `adapterConfig.env.ANTHROPIC_API_KEY` aus Keychain | ✅ danach **1:1 restored** |
| Test-Issue | [WHI-104](/WHI/issues/WHI-104) mit Mustermann-Datensatz | `todo` → nach Test wieder `blocked` |

---

## 2. Was im Run passiert ist

**Paperclip-Heartbeat** (`run 0c680c54-06c4-4857-bdb3-3aa3f99d6726`):
- Status `succeeded`, Dauer normal
- Token-Consumption: `in=10 out=2908 cached=173611 cost=$0.220151` → **echter Anthropic-API-Call erfolgt**

**DPO-Service-Log** (`~/Library/Logs/paperclip-dpo/out.log`):
```
req-1 GET  /health                         200 (39 ms)     ← Plugin-Ping (pingDpo)
req-2 POST /anthropic/v1/messages          401 (2603 ms)   ← Claude-CLI erreichte die Passthrough-Route
```
- 2603 ms Latenz passt zu einer echten Classifier-Roundtrip (Ollama/LM Studio `gemma-4-26b` braucht ~2-3 s)
- **Anonymisierung fand also statt**, der Request wurde weitergereicht
- **Aber Anthropic (oder der weitergereichte Request) lieferte 401**

**Debug-Trail** (`~/Library/Logs/paperclip-dpo/debug-trail/dpo-debug-trail-2026-04-24.jsonl`):
- **Leer.** Die portierte Streaming-Route hat keine `debugTrail`-Aufrufe mehr (der alte Non-Streaming-Port hatte sie; beim Austausch wurde sie nicht mitgezogen).

**Paperclip-Heartbeat-Log**:
- ANTHROPIC_API_KEY war in der Subprozess-Env gesetzt (als `***REDACTED***` sichtbar — das ist nur Log-Maskierung)
- Kein expliziter Log-Eintrag zur Hook-Invocation sichtbar (Plugin loggt über seinen eigenen `ctx.logger`)
- Run-Ergebnis: Buchhalter hat WHI-104 auf `done` gesetzt mit einem „ich habe die Verarbeitung abgelehnt"-Kommentar — **das heißt: das Issue wurde abgearbeitet, Claude hat geantwortet, der Agent hat nur selbst entschieden, nicht weiterzumachen**. Aber der API-Call hat stattgefunden.

---

## 3. Der Befund in einem Satz

**Der DPO hat anonymisiert, Anthropic hat den weitergereichten Request mit 401 abgelehnt, die Claude-CLI hat daraufhin offenbar auf Subscription-Auth zurückgegriffen und direkt `api.anthropic.com` kontaktiert — wodurch die Klartext-PII Anthropic erreicht hat.**

**DSGVO-Klassifikation:** Unkritisch für diesen Lauf, weil WHI-104 **Test-Daten (Max Mustermann)** enthielt, keine echten Kundendaten. Aber der Code-Pfad ist **produktiv nicht sicher**.

---

## 4. Hypothesen zur 401-Ursache (priorisiert)

### 4.1 Header-Whitelist zu schmal (wahrscheinlichste Ursache)

In [`paperclip-dpo-service/src/routes/anthropic-passthrough.ts`](../../paperclip-dpo-service/src/routes/anthropic-passthrough.ts):

```ts
function buildUpstreamHeaders(req: FastifyRequest): Record<string, string> {
  const headers: Record<string, string> = { "content-type": "application/json" };
  if (req.headers["x-api-key"]) headers["x-api-key"] = ...;
  if (req.headers["authorization"]) headers["authorization"] = ...;
  headers["anthropic-version"] = ...;
  if (req.headers["anthropic-beta"]) headers["anthropic-beta"] = ...;
  return headers;
}
```

**Nicht durchgereicht werden:** alles andere. Claude-CLI schickt möglicherweise:
- `x-api-key-auth-method` (Subscription vs. api-key discrimination)
- `user-agent` mit CLI-Version
- `x-stainless-*` (Anthropic-SDK-Metadaten)
- `x-request-id` / Trace-Header
- Weitere Proprietary-Header

Manche dieser Header könnte Anthropic für die Auth-Klassifikation brauchen.

### 4.2 Claude-CLI nutzt Subscription-Auth trotz gesetztem ANTHROPIC_API_KEY

Wenn `ANTHROPIC_BASE_URL` auf einen Non-anthropic.com-Host zeigt, könnte die CLI "das ist ein Custom-Proxy → Subscription-Session durchreichen" machen statt "API-Key-Auth". Das würde zu Session-Cookies im Header führen, die unser Upstream-Forward filtert.

### 4.3 URL-Pfad-Variante

Der erste DPO-Log-Eintrag einer früheren Session zeigte `/anthropic/v1/messages?beta=true`. Anthropic könnte bei Query-Params strenger sein. Meine Route akzeptiert den Query, reicht ihn aber nicht explizit weiter.

### 4.4 Unwahrscheinlich: API-Key ungültig

Beim Fallback-Call ging `cost=$0.22` durch — also ist der Key grundsätzlich gültig. Damit ausgeschlossen.

---

## 5. Reproduktions-Rezept für die nächste Session

### 5.1 Vorbereitung

```bash
# Paperclip läuft auf :3100 — falls down, neu starten:
cd "/Users/walterschoenenbroecher.de/Library/CloudStorage/SynologyDrive-Mac/Claude Code/Paperclip"
pnpm dev > /tmp/paperclip-dev.log 2>&1 &

# DPO-Service läuft via launchd auf :4711 — verifizieren:
curl http://localhost:4711/health
# → {"status":"ok","classifier":"reachable"}

# Plugin ist persistent installiert — verifizieren:
TOKEN="pcp_board_985880896179574eedaddb10a734d3a65f1306778501e4f1"
curl -s http://localhost:3100/api/plugins -H "Authorization: Bearer $TOKEN" \
  | node -e 'let s="";process.stdin.on("data",c=>s+=c).on("end",()=>{const p=JSON.parse(s);for(const x of p)console.log(x.pluginKey,x.status);})'
# → whitestag.pii-proxy ready
```

### 5.2 Debug-Strategie

**Schritt A — Header-Transparenz erhöhen.** Patch `paperclip-dpo-service/src/routes/anthropic-passthrough.ts`:
- Statt Whitelist: **alle** Request-Headers durchreichen, NUR `host`, `content-length`, `connection`, `x-pii-proxy-key` filtern
- Debug-Log zusätzlich: welche Headers werden geschickt, welcher Status kommt zurück, erste 500 Bytes Response-Body

**Schritt B — Debug-Trail-Support in Streaming-Route zurückportieren.** Der alte Non-Streaming-Port hatte `debugTrail.write(...)` an jeder Stage. In der neuen OSS-Route fehlt das komplett. Rückbauen, damit wir in `dpo-debug-trail-*.jsonl` die vier Stages sehen können (request / anonymized / external_response_raw / deanonymized) und nicht nur auf Pino-Logs angewiesen sind.

**Schritt C — Claude-CLI HTTP-Trace.** Die CLI startet Paperclip als Subprozess; man kann `NODE_DEBUG=http` in die adapterConfig.env injizieren, dann erscheinen die HTTP-Requests der CLI in stderr → Paperclip's `onLog`. So sieht man, welche URL/Headers die CLI wirklich verwendet und ob sie nach dem 401 einen Retry ohne BASE_URL macht.

### 5.3 Daten-Snapshots, auf denen wir wieder aufsetzen

- **Buchhalter-adapterConfig-Snapshot** liegt in `/tmp/paperclip-e2e-test/buchhalter-original.json` — darf über Reboots hinweg verloren gehen, dann aus Plugin-Settings-UI reproduzieren (aktuelle `adapterType: lmstudio_local`, `defaultModel: google/gemma-4-26b-a4b`, `fallbackModel: qwen/qwen3.6-35b-a3b`, `fallbackUrl: http://localhost:1234`).
- **DPO-Shared-Key** im Keychain `ai.whitestag.paperclip-dpo-key`.
- **Anthropic-API-Key** im Keychain `anthropic-api-key`.
- **Plugin-Config-ID**: `301fe2f3-d842-4ade-9544-6eddb84124c2` (Paperclip-internal UUID).
- **Plugin-Code** in `~/.paperclip/plugins/whitestag.pii-proxy/` — Symlink zu `packages/plugins/sdk` muss existieren:
  ```
  ~/.paperclip/plugins/whitestag.pii-proxy/node_modules/@paperclipai/plugin-sdk
    → /Users/walterschoenenbroecher.de/Library/CloudStorage/SynologyDrive-Mac/Claude Code/Paperclip/packages/plugins/sdk
  ```

---

## 6. Was in den 3 OSS-Repos stabil ist

Trotz E2E-Fehler: die **Code-Artefakte** sind alle grün und committed:

| Repo | Branch | Commits | Tests |
|---|---|---|---|
| Paperclip | `worktree-paperclip-dpo-m0-hook` + gemerged in `feat/lmstudio-dynamic-models` | 6 M0 | 12 neu + 1174 Full-Suite grün |
| `whitestag-ai/pii-proxy` | `feat/anthropic-passthrough-streaming` | 4 M1 + 1 M3 | 96 core, 92 server, 161-fuzz grün |
| `whitestag-ai/paperclip-plugin-pii-proxy` | `feat/before-adapter-execute-hook` | 1 M2 + 1 M3 | 30 grün |

Der Upstream-PR an Paperclip ist ready to merge, die npm-Publishes sind bereit sobald der 401-Bug fixed ist.

---

## 7. To-Do für die nächste Session

1. ~~**Header-Whitelist entfernen** + Debug-Logging in der Passthrough-Route (Schritt A).~~ ✅ commit `b022bdb6` — Blacklist-Ansatz, strippt nur hop-by-hop + proxy-internal + accept-encoding; user-agent/x-stainless-*/anthropic-beta werden jetzt durchgereicht.
2. ~~**Debug-Trail zurückportieren** in die Streaming-Route (Schritt B).~~ ✅ `b022bdb6` — vier Stages (request/anonymized/external_response_raw/deanonymized) plus blocked/error; `forwardedHeaderNames` im request-Eintrag macht Header-Set sichtbar; smoketest gegen `/anthropic/v1/messages` mit Fake-Key liefert {request,anonymized,error:httpStatus=401} wie erwartet.
3. **`NODE_DEBUG=http`** im Buchhalter für einen diagnostischen Run.
4. ~~**Re-Test** mit Mustermann-Datensatz.~~ ⚠️ 2026-04-24 ~19:31 CEST durchgeführt — Buchhalter auf `claude_local` + `adapterConfig.env.ANTHROPIC_API_KEY` via PATCH, WHI-104 assign-basierter Wakeup, Run `5456dfd1-1dc9-4ebf-b133-d1f53dd1d2b0` abgeschlossen `succeeded`, `total_cost_usd=0.20198`, `apiKeySource: ANTHROPIC_API_KEY`. **Debug-Trail nach dem Run: 0 Einträge.** Keine "pii-proxy active — injecting provider base URL" / "pii-proxy skipped" / "pii-proxy unreachable" im Paperclip-Log. → Hook `onBeforeAdapterExecute` wurde **nicht invoked**, Claude-CLI lief direkt gegen `api.anthropic.com`. PII (Mustermann) ist durch. Buchhalter + Issue wurden 1:1 aus Snapshot restored.
5. **Neue Haupthypothese — Broadcaster nicht verdrahtet im Wake-Pfad.** Es gibt im Server mehrere `heartbeatService()`-Instanzen (`server/src/index.ts:659` mit broadcaster, aber `routes/agents.ts:133`, `routes/issues.ts:389`, `routes/approvals.ts:32`, `services/plugin-host-services.ts:469`, `services/routines.ts:362` ohne broadcaster). Queue ist zwar DB-shared, aber `enqueueWakeup` könnte einen Code-Pfad haben der `executeRun` direkt aus der broadcaster-losen Instanz triggert. Prüfen:
   - In `services/heartbeat.ts` ab `enqueueWakeup` (Zeile 6466) tracen, wann/wo nach dem insert `executeRun` gestartet wird.
   - Temporär ein `logger.info` vor `broadcastBeforeAdapterExecute` in heartbeat.ts:5603 setzen und Re-Test — damit sichtbar wird, ob der Code-Pfad überhaupt erreicht wird.
   - Alternativ Plugin-Worker-seitig: `ctx.logger.info` als erste Zeile in `onBeforeAdapterExecute` einbauen, um RPC-Empfang zu verifizieren.
6. **Falls Hook greift und 401 weiter**: Claude-CLI-Source anschauen, wie sie den Auth-Modus bestimmt (Pfad-Info: `/opt/homebrew/bin/claude` → `which claude`, dann Quelle finden).
7. **Fallback-Umgehung verhindern**: Wenn der DPO 502 o.ä. zurückgibt, darf die CLI nicht auf direkte anthropic.com schwenken. Vermutlich durch Env-Var wie `ANTHROPIC_DISABLE_API_KEY_FALLBACK=1` — recherchieren, ob die CLI so was unterstützt.

---

## 8. Kostenhinweis

Dieser Test hat **~$0.22** an Anthropic-API-Kosten verursacht (eigenes Account). Der Run war allerdings großteils Cache-Hit (173k cached tokens), in einem Normalbetrieb ohne Cache wäre der Call teurer gewesen.

**Keine Kunden-PII exponiert** — Test verwendete Mustermann-Daten.

**Re-Test 2026-04-24 19:31:** weitere **$0.20** auf eigenes Account — ebenfalls keine Kunden-PII. Muster-Daten desselben WHI-104-Issues. Der Hook griff nicht, Claude-CLI ging direkt an api.anthropic.com (siehe Abschnitt 7, Punkt 4–5).
