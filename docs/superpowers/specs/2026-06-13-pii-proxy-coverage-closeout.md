# PII-Proxy-Durchsetzung — Coverage & Closeout

- **Datum:** 2026-06-13
- **Status:** Abgeschlossen (A+B+C live + verifiziert)
- **Spec:** [2026-06-13-pii-proxy-enforcement-design.md](2026-06-13-pii-proxy-enforcement-design.md) ·
  **Plan:** [../plans/2026-06-13-pii-proxy-enforcement.md](../plans/2026-06-13-pii-proxy-enforcement.md)

## Erreichter Zustand

| Egress-Pfad | Status | Mechanismus |
|---|---|---|
| **Anthropic / claude_local — WHITESTAG (3 Agenten)** | ✅ anonymisiert + fail-closed | `ANTHROPIC_BASE_URL=:4711/anthropic` (Base-URL-Pinning) **+** Host-Hook `required` |
| **Anthropic / claude_local — Clara Sound (3 Agenten)** | ✅ anonymisiert + fail-closed | dito |
| **Künftige claude_local-Agenten (alle Companies)** | ✅ automatisch abgedeckt | Host-Hook `onBeforeAdapterExecute`, Plugin `required`+`failClosedOnUnreachable` → injiziert Base-URL bzw. blockt bei Proxy-Ausfall |
| **Health Insights (5 Agenten)** | ✅ kein Cloud-Egress | nur `lmstudio_local` (lokal) |
| **OpenAI / codex_local** | 🟡 Route live, kein Agent | `/openai/v1/chat/completions` (noAuth) bereit; Plugin `providers=[anthropic,openai]`; **provider-map** braucht noch `codex_local`-Eintrag für Auto-Wiring, sobald ein OpenAI-Agent existiert |
| **n8n Cloud-OpenAI** | 🟡 außerhalb Scope, derzeit sauber | „DPO-Proxy V1" (aktiv) anonymisiert selbst vor `api.openai.com`; „Artikel2Blog" (inaktiv). Kein aktiver un-anonymisierter Egress. n8n hängt **nicht** am Paperclip-Adapter-Hook. |
| **Agent-eigene direkte HTTP/LLM-Calls aus Tool-Code** | ❌ nicht abgedeckt (Architektur-Grenze) | Der Host-Hook deckt nur den **Adapter-Subprozess**-Egress (Claude-CLI) ab, nicht selbstgeschriebene Outbound-Calls eines Agenten. Vgl. CFO-Doc WHI-570 „Umgehung". |

## Infrastruktur (IST nach Rollout)

- **:4711 = `io.piiproxy.server`** (launchd), läuft aus `opensource/pii-proxy/packages/server/dist`.
  Der alte `paperclip-dpo-service` (`ai.whitestag.paperclip-dpo`) ist gestoppt+disabled, Backup in
  `~/pii-proxy-backup-2026-06-13/`.
- **Passthrough:** `POST /anthropic/v1/messages` & `/openai/v1/chat/completions` sind **`noAuth`** —
  die Anthropic/OpenAI-Auth der CLI wird mitsamt SDK-Headern upstream geforwardet; `/anonymize`,
  `/deanonymize`, `/safe-call` bleiben `X-PII-Proxy-Key`-pflichtig.
- **Classifier:** `gemma-4-31b-it-mlx` (LM Studio :1234). Code-Fix in `pii-proxy/packages/core`:
  **Chunking + per-Chunk-Hash-Cache** (statischer System/Skills-Kontext wird 1× klassifiziert, dann
  Cache-Hit) + **`reasoning_content`-Fallback**. Timeout `PII_PROXY_CLASSIFIER_TIMEOUT_MS=60000`.
  Verworfen (Genauigkeit): qwen3.6 (Reasoning-Output), qwen2.5-coder (verfehlt PERSON/ORT, Art.9
  nicht-deterministisch). gemma ist der einzig validiert-genaue Classifier.
- **Art. 9** wird hart geblockt (Confidence ≥ high). Regex-Detektoren (EMAIL/PHONE/IBAN/PLZ) laufen
  weiter auf dem Volltext; nur der LLM-Pass (PERSON/FIRMA/ORT/ART_9) ist gechunkt.
- **Host-Hook:** `onBeforeAdapterExecute` in Paperclip-`master` (Commit `628e72000`, 6 Commits ff-merged).
  Plugin `whitestag.pii-proxy` (Instanz `301fe2f3`) auf `required` + `failClosedOnUnreachable=true`.

## Verifikation (DoD)

- ✅ Echter Live-Round-Trip (Link-Detektor): 7× `anthropic-passthrough`, 0 blockiert, PII anonymisiert
  → Anthropic → deanonymisiert.
- ✅ Fail-closed: Proxy gestoppt → ConnectionRefused, **null** Anthropic-Egress, 0 Tokens.
- ✅ Host-Hook `required` live verifiziert: Lauf routet über Hook, kein RPC-Fehler, keine Fehlerwelle.
- ✅ Accuracy-Spot-Check nach Chunking: PERSON/ORT/IBAN erkannt, Art.9 geblockt, kein Fehlalarm.

## Incident (transparent dokumentiert)

Beim **ersten** Host-Hook-Cutover wurde ein Port-Branch gemergt, der versehentlich auf einer
**285 Commits divergenten origin-Basis** lag (Agent-Worktree `fresh`/origin statt lokalem HEAD) →
breite Konflikte → tsx-watch-Crash → :3100 **~3–4 min down**. Recovery: `git reset --hard
pre-pii-hook-cutover-2026-06-13` + sauberer Neustart. **Lehren:** (1) Port-Worktree immer off
**lokalem** HEAD; (2) Deploy über kontrollierten Stop→Merge→SDK-Build→Start, nicht Hot-Reload-Merge;
(3) Dev-Server ist **launchd `ing.paperclip.dev`** (KeepAlive) → Neustart via
`launchctl kickstart -k gui/$(id -u)/ing.paperclip.dev`. Zweiter Cutover (korrekte Basis, ff-Merge)
lief sauber.

## Offene Folge-Schritte (nicht in diesem Rollout)

1. **provider-map `codex_local`** im Plugin aktivieren, sobald ein OpenAI/codex-Agent existiert
   (Auto-Wiring `OPENAI_BASE_URL=:4711/openai/v1`).
2. **n8n-Direkt-Calls**: optional „Artikel2Blog" o.ä. auf den `/openai`-Passthrough umbiegen, falls je
   aktiviert; n8n grundsätzlich außerhalb des Plugin-Hooks.
3. **`/health`-Härtung**: meldet „classifier reachable" auch wenn die echte Klassifikation (Modellname/
   Timeout) bricht — ein echter Klassifikations-Ping wäre robuster.
4. **Agent-eigene Outbound-Calls**: organisatorisch/Policy adressieren (Host-Hook kann das nicht).
