# PII-Proxy-Durchsetzung in Paperclip — Design / Spec

- **Datum:** 2026-06-13
- **Status:** Design (genehmigt, Spec-Review ausstehend)
- **Geschäftsbereich:** WHITESTAG.AI — DPO / GDPR-Compliance
- **Ziel:** Kein un-anonymisierter Cloud-LLM-Egress. Alle ausgehenden LLM-Anfragen
  der Paperclip-Agenten (zuerst Anthropic/claude_local, dann OpenAI) laufen über den
  lokalen PII-Proxy und werden anonymisiert, **bevor** sie den Rechner verlassen —
  fail-closed bei Proxy-Ausfall.

---

## 1. Verifizierter IST-Zustand (Audit 2026-06-13, quellbasiert)

Belege wurden gegen den **laufenden** Code geprüft, nicht gegen Notizen:

1. **Kein Host-Hook.** `onBeforeAdapterExecute` existiert im laufenden Paperclip-Server
   (`server/src`, PID auf :3100) **nicht** (0 Treffer). Die scheinbaren `onBeforeForWakeup`-
   Treffer sind `resolveSessionBeforeForWakeup` in `server/src/services/heartbeat.ts` —
   eine Session-Helper-Funktion, **kein** Plugin-Hook. Das Plugin `whitestag.pii-proxy`
   kann also nie feuern.
2. **Kein `ANTHROPIC_BASE_URL`** wird serverseitig gesetzt.
3. **Alle 3 claude_local-Agenten** haben leeres `adapterConfig.env` und rufen heute
   **direkt** `api.anthropic.com`:
   - `dfa8d0e2-d48a-4342-82c2-f7cf6de9d562` — n8n-Betriebsingenieur
   - `f4bf1c83-9c79-4864-87eb-dd8c22fa604d` — Bild & Video
   - `caaeb345-9db1-41ab-95a3-115d3c70cf34` — Link-Detektor
4. **Der laufende :4711-Dienst ist der ALTE Codebase.** `paperclip-dpo-service`
   (`opensource/paperclip-dpo-service`) registriert nur `/health`, `/anonymize`,
   `/deanonymize`, `/safe-call` — **keinen** `/anthropic`-Passthrough. Das 401 auf
   `/anthropic/v1/messages` war nur der globale `X-DPO-Key`-Auth-Hook **vor** dem 404.
5. **Der NEUE Server hat alles fertig.** `opensource/pii-proxy` (Monorepo, Branch
   `feat/openai-chat-completions-passthrough`), Paket `@whitestag/pii-proxy-server`
   (`packages/server`) hat:
   - `POST /anthropic/v1/messages` — `noAuth`, anonymisiert system+messages, forwardet
     Anthropic-Auth (`x-api-key` **oder** `authorization`) **plus** SDK-Header
     (`user-agent`, `x-stainless-*`, `anthropic-version`) upstream, Streaming via
     `anthropic-sse-deanonymizer`, Art.9 → block.
     Quelle: `packages/server/src/routes/anthropic-passthrough.ts`.
   - `POST /openai/v1/chat/completions` — `noAuth`, analog, mit `openai-sse-deanonymizer`.
     Quelle: `packages/server/src/routes/openai-chat-passthrough.ts`.
   - `/health` `noAuth`; `/anonymize`, `/deanonymize`, `/safe-call` weiterhin
     `X-DPO-Key`-pflichtig. Quelle: `packages/server/src/server.ts`, `src/auth.ts`.
   - Eigenes Service-Tooling: `service:keygen`, `service:install` (launchd/systemd/
     Windows), `service:smoke`, `service:uninstall`.
     Config über `PII_PROXY_*`-Env (`packages/server/src/config.ts`), Port-Default 4711,
     Classifier-Default `http://localhost:1234 / gemma-4-26b` (= laufender LM-Studio-
     Classifier).

**Konsequenz:** Die Passthrough-Logik muss **nicht** neu geschrieben werden. Die Aufgabe
ist: den richtigen Server in Betrieb nehmen, die Agenten dranhängen, Enforcement ergänzen,
OpenAI abdecken — und alles quellsynchron halten.

---

## 2. Ziel-Architektur

```
Paperclip claude_local-Agent (Heartbeat)
  └── claude-CLI   [ANTHROPIC_BASE_URL=http://localhost:4711/anthropic]
        └── POST :4711/anthropic/v1/messages   (noAuth; Anthropic-Auth + SDK-Header → upstream)
              ├── anonymize(system+messages); Art.9 → block(400)
              │       └── api.anthropic.com/v1/messages
              └── SSE/JSON zurück, per-Token deanonymisiert → CLI sieht echte Namen
Proxy down ⇒ Base-URL tot ⇒ KEIN Pfad zu api.anthropic.com ⇒ inhärent fail-closed
```

OpenAI/codex_local analog über `OPENAI_BASE_URL=http://localhost:4711/openai/v1`.
Lokale Adapter (`lmstudio_local`, 22 Agenten) werden **nie** angefasst — kein Cloud-Egress.

---

## 3. Workstreams

> **Stehende Regel (für jeden Workstream):** Vor und während jeder Änderung die
> einschlägigen **opensource-Quellen** lesen (`opensource/pii-proxy`,
> `opensource/paperclip-plugin-pii-proxy`, `opensource/paperclip-dpo`). Jede Änderung an
> Plugin oder Server wird **doppelt** gepflegt: in der kanonischen opensource-Quelle (auf
> dem korrekten Branch) **und** in der installierten/laufenden Kopie. Keine Divergenz.

### W1 — Richtigen Server in Betrieb nehmen (ersetzt den alten Dienst)

**Ziel:** :4711 liefert die Passthroughs aus `@whitestag/pii-proxy-server`.

- Quelle lesen: `packages/server/src/{server,config}.ts`, `scripts/install-service.mjs`,
  `scripts/lib/*.mjs`, `scripts/generate-shared-key.mjs`, `scripts/smoke.mjs`.
- `packages/core` + `packages/server` bauen (`pnpm build` / `tsc`).
- Secrets erzeugen (nie loggen, nie ins Issue):
  - `PII_PROXY_SHARED_KEY` via `service:keygen` (≥32 Zeichen).
  - `PII_PROXY_MAPPING_KEY_BASE64` via `randomBytes(32).toString('base64')`.
- **Vorher:** alten Dienst sichern — laufenden Startweg/Plist von `paperclip-dpo-service`
  und dessen `DPO_*`-Env dokumentieren und sichern (kein Überschreiben). Alten Dienst
  stoppen/deaktivieren.
- `service:install` ausführen → schreibt `~/Library/LaunchAgents/<service>.plist` mit
  eingebetteter Env, Daten-Dir mit `mappings.db` + `audit`. Port 4711, Bind nur lokal
  (`PII_PROXY_BIND=127.0.0.1` erwägen statt Default `0.0.0.0`).
- Verifikation: `service:smoke` grün, `GET /health` → `{"status":"ok",
  "classifier":"reachable"}`, `POST /anthropic/v1/messages` ohne Key liefert **nicht** mehr
  „missing X-DPO-Key", sondern den erwarteten Auth-/Body-Pfad (401 nur bei fehlender
  Anthropic-Auth, nicht bei fehlendem DPO-Key).
- Mapping-DB: per-Request + TTL → **keine** Migration der alten DB nötig.

**Done:** Neuer Server läuft als kanonischer :4711-Dienst, alter Dienst stillgelegt &
gesichert, Passthrough-Route erreichbar.

### W2 — Die 3 claude_local-Agenten verdrahten (Option A)

**Ziel:** Anthropic-Egress der 3 Agenten läuft anonymisiert über :4711, fail-closed.

- Quelle lesen: `server/src/adapters/process/execute.ts` (Env-Merge Zeile 22–26 bestätigt:
  `adapterConfig.env` wird in die Child-Env gemerged), `provider-map.ts` im Plugin.
- **Backup:** aktuelle `adapterConfig` aller 3 Agenten per API exportieren und ablegen.
- Pro Agent in `adapterConfig.env` setzen:
  `ANTHROPIC_BASE_URL=http://localhost:4711/anthropic`
  (**kein** Key-Header nötig — Passthrough ist `noAuth`; CLI-Auth wird durchgereicht).
- Umstellung **erst nach** W1 + erfolgreichem End-to-End-Test (gewählte Posture:
  „funktional lassen, dann hart umstellen" — kein vorzeitiger Betriebsausfall des
  n8n-Betriebsingenieur-Recovery-Agenten).
- Fail-closed-Eigenschaft: Da die Base-URL auf den Proxy gepinnt ist, gibt es bei
  Proxy-Ausfall **keinen** Pfad zu `api.anthropic.com`.

**Done:** Alle 3 claude_local-Agenten zeigen auf den Proxy; verifizierter Test-Call (s. W5).

### W3 — Enforcement / Host-Hook (Option B) — letzter, separater Schritt

**Ziel:** Kein claude_local-Agent (auch künftige) kann den Proxy umgehen; Block bei Ausfall.

- Quelle lesen: Paperclip-Plugin-Host (`server/src/services/plugin-loader.ts`,
  `plugin-registry.ts`, `plugin-worker-manager.ts`, `plugin-tool-dispatcher.ts`) +
  Adapter-Execute-Pfad (`server/src/adapters/process/execute.ts`, `registry.ts`); im
  Plugin die bereits vorhandene reine Logik `src/hook-logic.ts`
  (`handleBeforeAdapterExecute`), `mode-resolver.ts`, `provider-map.ts`, `worker.ts`.
- **Neuer Host-Erweiterungspunkt:** `onBeforeAdapterExecute` im Adapter-Execute-Pfad
  einführen — wird einmal pro Agent-Run **vor** dem Spawn aufgerufen, ruft die
  capability-gated Plugin-Worker-Handler (Worker↔Host-RPC) und wendet deren Ergebnis an:
  `env`-Injektion (`ANTHROPIC_BASE_URL`) bzw. `block` (Run abbrechen).
- Plugin-Worker an den neuen Hook anbinden (`worker.ts` → `handleBeforeAdapterExecute`).
- Plugin-Config: `defaultMode=required` + `failClosedOnUnreachable=true` →
  kein Opt-out, Block bei Proxy-Ausfall, automatische Abdeckung **neuer** claude_local-Agenten.
- Paperclip-Server-Build + **kontrollierter** Neustart (Env-Var-Falle beachten; Neustart
  vorab bestätigen lassen).
- Konsistenz: Sobald W3 steht, ist die per-Agent-Env aus W2 redundant, bleibt aber als
  fail-closed-Doppelung bewusst bestehen (kein Rückbau).

**Done:** Host feuert den Hook, `required`+failClosed aktiv, ein neu angelegter
Test-claude_local-Agent ohne Env wird automatisch über den Proxy geroutet bzw. bei
Proxy-Stop geblockt.

### W4 — OpenAI/ChatGPT (Option C)

**Ziel:** OpenAI-Egress abgedeckt bzw. nachweislich nicht vorhanden.

- Quelle lesen: `packages/server/src/routes/openai-chat-passthrough.ts` (Route schon
  registriert), Plugin `provider-map.ts` (Phase-2-Kommentar
  `codex_local → OPENAI_BASE_URL → /openai/v1`).
- **Inventur:** prüfen, ob aktuell ein `codex_local`/OpenAI-Adapter-Agent existiert und ob
  n8n-Workflows **direkt** OpenAI rufen (Plugin/Proxy deckt n8n **nicht** ab).
- Falls OpenAI-Agenten existieren: Plugin-`provider-map` um `codex_local` erweitern
  (Host + opensource), `OPENAI_BASE_URL=http://localhost:4711/openai/v1` analog zu W2
  verdrahten; `providers` in der Plugin-Config auf `["anthropic","openai"]`.
- Falls keine existieren: als „derzeit kein OpenAI-Egress" dokumentieren, Mechanik
  trotzdem bereitstellen.

**Done:** OpenAI-Pfad entweder verdrahtet+verifiziert oder dokumentiert als nicht vorhanden;
n8n-Direkt-Calls als bekannte Lücke benannt.

### W5 — Source-Sync, Verifikation, Dokumentation

- **Source-Sync:** Plugin-Änderungen in `opensource/paperclip-plugin-pii-proxy` (korrekter
  Branch) **und** `~/.paperclip/plugins/whitestag.pii-proxy/`. Server-Änderungen in
  `opensource/pii-proxy`. README-Widerspruch der installierten Plugin-Doku korrigieren
  („passthrough braucht keinen sharedKey" — stimmt für den NEUEN Server, der Passthrough
  ist `noAuth`; alte Aussage im Kontext des alten Dienstes war irreführend).
- **DoD-Verifikation (echter Test-Call):**
  1. Über einen der 3 Agenten einen realen Lauf auslösen.
  2. Im PII-Proxy-`audit`-Log nachweisen: Prompt wurde anonymisiert (Pseudonyme statt
     Klarnamen), Antwort deanonymisiert zurück.
  3. **Fail-closed-Test:** Proxy stoppen → Agent-Lauf erreicht `api.anthropic.com` **nicht**
     (W2: Connection-Refused; nach W3: sauberer `pii_proxy_unreachable`-Block).
- **Abschluss-Doku** (Coverage-Matrix): claude_local ✅; codex_local/OpenAI ✅/„keiner
  vorhanden"; **nicht abgedeckt:** direkte LLM-Calls aus n8n-Workflows, andere Provider
  (Gemini …). Nächste Schritte für vollständige „ALLE"-Abdeckung.

---

## 4. Sicherheit & Fail-Closed-Semantik

- **W2 (Base-URL-Pinning):** Proxy-Ausfall ⇒ kein Egress (Verbindung zur toten Base-URL
  schlägt fehl). Fail-closed „by construction", aber pro Agent konfiguriert.
- **W3 (required + failClosed):** Proxy-Ausfall ⇒ expliziter `block`. Zentrale Policy,
  deckt auch neue Agenten. Beide Mechanismen koexistieren bewusst.
- **Art.9-Daten** werden vom Proxy hart geblockt (400 `blocked_by_pii_proxy`).
- **Secrets:** `PII_PROXY_SHARED_KEY`, `PII_PROXY_MAPPING_KEY_BASE64`, Anthropic-Keys —
  nie loggen, nie ins Issue/Spec schreiben. Bind möglichst `127.0.0.1`.
- **Bekannte Restlücken (dokumentiert, nicht in Scope):** n8n-Workflows mit direktem
  LLM-Call; Provider außer Anthropic/OpenAI; nicht-`/v1/messages`-Anthropic-Endpunkte.

---

## 5. Reihenfolge & Rollback

1. W1 (Server-Swap) → smoke/health grün.
2. W2 (3 Agenten verdrahten) → **W5-Verifikation** (echter Call + fail-closed).
3. W4 (OpenAI-Inventur + ggf. verdrahten).
4. W3 (Host-Hook + required) als separater, bestätigter Schritt inkl. Server-Neustart.

**Rollback je Schritt:** W1 → alten Dienst-Startweg reaktivieren (gesichert). W2/W4 →
Agent-`adapterConfig` aus Backup zurückspielen (`ANTHROPIC_BASE_URL` entfernen). W3 →
Server-Build zurücksetzen, Plugin auf `default-off`.

**Live-Eingriffe** (Agent-Env, Dienst-Swap, Server-Build, Neustarts) werden **einzeln
vorab bestätigt**; nichts blind überschreiben, alles versioniert/gesichert.

---

## 6. Definition of Done

- [ ] Neuer Passthrough-Server kanonisch auf :4711, alter Dienst gesichert & stillgelegt (W1).
- [ ] 3 claude_local-Agenten über `:4711/anthropic`, verifiziert per echtem Test-Call:
      anonymisiert raus, deanonymisiert rein (W2/W5).
- [ ] Fail-closed bei Proxy-Ausfall nachgewiesen (W5).
- [ ] Enforcement `required`+failClosed via Host-Hook, neuer Agent automatisch abgedeckt (W3).
- [ ] OpenAI-Pfad verdrahtet oder als nicht vorhanden dokumentiert (W4).
- [ ] Alle Änderungen quellsynchron (opensource + installiert) (W5).
- [ ] Coverage-Doku: abgedeckte vs. offene Egress-Pfade + nächste Schritte (W5).
