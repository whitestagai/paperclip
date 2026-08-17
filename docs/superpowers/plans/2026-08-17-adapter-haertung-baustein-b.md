# Adapter-Härtung — Baustein B Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transiente LLM-Störungen werden im Adapter abgefangen, **bevor** ein Agent daran stirbt — die Selbstheilung soll der Notnagel sein, nicht der Regelbetrieb.

**Architecture:** Bounded Retry mit exponentiellem Backoff auf dem Chat-Completion-Aufruf, sauber getrennt von der bestehenden Fallback-Logik: Verbindungsfehler und Überlast werden wiederholt, echte 4xx nicht — dort greift weiterhin der Wechsel auf das Fallback-Modell.

**Tech Stack:** TypeScript, vitest. Eigenes Repo: `~/SynologyDrive/Mac/Claude Code MAC/opensource/paperclip-adapter-lmstudio` (Remote `whitestag-ai`).

**Spec:** `docs/superpowers/specs/2026-07-24-agent-self-heal-design.md`, §3 Baustein B

## Global Constraints

- **Anderes Repo.** Alle Arbeit in `~/SynologyDrive/Mac/Claude Code MAC/opensource/paperclip-adapter-lmstudio`, nicht im Paperclip-Monorepo.
- **Nach jeder Änderung `npm run build`.** Der Host lädt `dist/`, nicht `src/`. Ein vergessener Build ist ein stiller Nicht-Deploy.
- Der Adapter ist über `~/.paperclip/adapter-plugins.json` als `lmstudio_local` registriert (localPath, kein npm-Paket).
- Baseline vor Beginn: `npx vitest run` → 156 Tests grün, `npx tsc --noEmit` sauber.
- Deutsche Kommentare, die das WARUM erklären.
- **Nicht anfassen:** die `classifyHttpError`-Regex (die trägt den RAM-Guardrail-Fix vom 07.07.) und die `reasoningEffort`-Weitergabe (drei Aufrufstellen, 17.08.).

## Warum das nötig ist — gemessen am 17.08.

Fehlercodes aus 7 Tagen (`heartbeat_runs`, `failed`/`timed_out`):

| Code | Anzahl | im Adapter abfangbar? |
|---|---:|---|
| `claude_transient_upstream` | 182 | nein — anderer Adapter (`claude_local`) |
| `llm_unreachable` | 83 | **ja** — Verbindungsfehler |
| `max_iterations` | 44 | teilweise — Task 3 |
| `adapter_failed` | 29 | **ja** — meist Verbindungsabbruch |
| `llm_error` | 16 | **ja** — u.a. „Model reloaded" |
| `timeout` | 13 | teilweise |

Der Chat-Completion-Aufruf retryt heute **gar nicht**: `callChatCompletion` wirft bei `fetch failed` sofort. Nur der Endpoint-Probe in `endpoint-resolver.ts` hat einen Retry. Ein einziger Netzhänger tötet also einen Agentenlauf, der 20 Minuten Arbeit enthalten kann.

Live belegt am selben Tag: die Sekretärin starb an `LM Studio API error 400: {"error":"Model reloaded."}` — eine Störung, die Sekunden dauert.

## File Structure

| Datei | Verantwortung |
|---|---|
| `src/server/retry-policy.ts` | **neu, rein:** ist dieser Fehler wiederholbar, und wie lange warten |
| `tests/retry-policy.test.ts` | Tests dazu |
| `src/server/llm-client.ts` | Retry-Schleife um den Completion-Aufruf |
| `tests/llm-client-retry.test.ts` | Tests dazu |
| `src/server/execute.ts` | Konfigurationswerte lesen und durchreichen |

---

### Task 1: Retry-Politik (rein)

**Files:**
- Create: `src/server/retry-policy.ts`
- Test: `tests/retry-policy.test.ts`

**Interfaces:**
- Produces: `isRetryableLlmFailure(err: unknown): boolean` und `retryDelayMs(attempt: number, baseMs: number): number`.

- [ ] **Step 1: Write the failing test**

```typescript
import { describe, it, expect } from "vitest";
import { isRetryableLlmFailure, retryDelayMs } from "../src/server/retry-policy.js";
import { LlmClientError } from "../src/server/llm-client.js";

describe("isRetryableLlmFailure — wiederholbar", () => {
  it.each([
    ["network", "LLM network error: ECONNREFUSED (fetch failed)"],
    ["network", "LLM network error: ECONNRESET (socket hang up)"],
    ["timeout", "LLM call timed out"],
  ])("wiederholt %s: %s", (kind, msg) => {
    expect(isRetryableLlmFailure(new LlmClientError(kind as never, msg))).toBe(true);
  });

  it("wiederholt einen 503", () => {
    expect(isRetryableLlmFailure(new LlmClientError("unknown", "LM Studio API error 503: overloaded"))).toBe(true);
  });

  it("wiederholt „Model reloaded\" — die Stoerung dauert Sekunden", () => {
    expect(isRetryableLlmFailure(
      new LlmClientError("unknown", 'LM Studio API error 400: {"error":"Model reloaded."}'),
    )).toBe(true);
  });
});

describe("isRetryableLlmFailure — NICHT wiederholbar", () => {
  it("wiederholt kein Modellproblem — dort greift der Fallback-Wechsel", () => {
    expect(isRetryableLlmFailure(new LlmClientError("model", "LM Studio model error 400: not found"))).toBe(false);
  });

  it("wiederholt keinen echten 400", () => {
    expect(isRetryableLlmFailure(new LlmClientError("unknown", "LM Studio API error 400: bad request"))).toBe(false);
  });

  it("wiederholt keinen 401", () => {
    expect(isRetryableLlmFailure(new LlmClientError("unknown", "LM Studio API error 401: unauthorized"))).toBe(false);
  });

  it("wiederholt nichts Fremdes", () => {
    expect(isRetryableLlmFailure(new Error("irgendwas"))).toBe(false);
  });
});

describe("retryDelayMs — 0,5 / 1,5 / 4 s", () => {
  it.each([[0, 500], [1, 1500], [2, 4000]])("Versuch %i wartet %i ms", (attempt, expected) => {
    expect(retryDelayMs(attempt, 500)).toBe(expected);
  });

  it("deckelt bei der letzten Stufe", () => {
    expect(retryDelayMs(9, 500)).toBe(4000);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run tests/retry-policy.test.ts`
Expected: FAIL — Modul nicht gefunden

- [ ] **Step 3: Write minimal implementation**

```typescript
import { LlmClientError } from "./llm-client.js";

/** Wartezeiten als Vielfache der Basis: 0,5 s → 1,5 s → 4 s. */
const BACKOFF_MULTIPLIERS = [1, 3, 8] as const;

/**
 * Nur Stoerungen wiederholen, die von selbst vergehen.
 *
 * Bewusst NICHT wiederholt wird `kind === "model"` — dort wechselt der Adapter
 * auf das Fallback-Modell, und ein Retry wuerde diesen Wechsel nur verzoegern.
 * `Model reloaded` kommt als 400 daher, ist aber eine Sekundenstoerung: LM Studio
 * hat das Modell mitten im Aufruf neu geladen. Genau daran ist am 17.08. die
 * Sekretaerin gestorben.
 */
export function isRetryableLlmFailure(err: unknown): boolean {
  if (!(err instanceof LlmClientError)) return false;
  if (err.kind === "network" || err.kind === "timeout") return true;
  if (err.kind === "model") return false;
  return /\b(429|500|502|503|504)\b|overloaded|model reloaded/i.test(err.message);
}

/** Wartezeit vor dem naechsten Versuch. */
export function retryDelayMs(attempt: number, baseMs: number): number {
  const index = Math.min(Math.max(attempt, 0), BACKOFF_MULTIPLIERS.length - 1);
  return baseMs * BACKOFF_MULTIPLIERS[index];
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run tests/retry-policy.test.ts`
Expected: PASS (11 Tests)

- [ ] **Step 5: Commit**

```bash
git add src/server/retry-policy.ts tests/retry-policy.test.ts
git commit -m "feat(retry): Politik fuer wiederholbare LLM-Stoerungen"
```

---

### Task 2: Retry-Schleife im Completion-Aufruf

**Files:**
- Modify: `src/server/llm-client.ts`
- Test: `tests/llm-client-retry.test.ts`

**Interfaces:**
- Consumes: `isRetryableLlmFailure`, `retryDelayMs`.
- Produces: `CompletionRequest` bekommt `maxRetries?: number` und `retryBaseMs?: number`; `callChatCompletion` wiederholt entsprechend.

- [ ] **Step 1: Write the failing test**

```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";
import { callChatCompletion } from "../src/server/llm-client.js";

const BASE = {
  url: "http://localhost:1234",
  model: "qwen3.6-35b-a3b-mlx",
  messages: [{ role: "user" as const, content: "Hallo" }],
  tools: [],
  timeoutMs: 30000,
  retryBaseMs: 1,   // Tests warten nicht wirklich
};

const ok = () => ({
  ok: true,
  json: async () => ({
    choices: [{ message: { role: "assistant", content: "Fertig" }, finish_reason: "stop" }],
    usage: { prompt_tokens: 3, completion_tokens: 2 },
  }),
});

const netzfehler = () => Object.assign(new Error("fetch failed"), { cause: { code: "ECONNRESET" } });

describe("callChatCompletion — Retry", () => {
  beforeEach(() => { vi.restoreAllMocks(); });

  it("gibt nach einem Netzfehler im zweiten Versuch sauber zurueck", async () => {
    const fetchMock = vi.fn().mockRejectedValueOnce(netzfehler()).mockResolvedValue(ok());
    vi.stubGlobal("fetch", fetchMock);

    const result = await callChatCompletion({ ...BASE, maxRetries: 3 });

    expect(result.message.content).toBe("Fertig");
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("wiederholt „Model reloaded\" und kommt durch", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: false, status: 400, statusText: "Bad Request",
        text: async () => '{"error":"Model reloaded."}' })
      .mockResolvedValue(ok());
    vi.stubGlobal("fetch", fetchMock);

    const result = await callChatCompletion({ ...BASE, maxRetries: 3 });

    expect(result.message.content).toBe("Fertig");
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("gibt nach erschoepften Versuchen den letzten Fehler weiter", async () => {
    const fetchMock = vi.fn().mockRejectedValue(netzfehler());
    vi.stubGlobal("fetch", fetchMock);

    await expect(callChatCompletion({ ...BASE, maxRetries: 3 })).rejects.toThrow(/network|fetch failed/i);
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("wiederholt einen echten 400 NICHT — der Fallback-Wechsel soll greifen", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false, status: 400, statusText: "Bad Request", text: async () => "bad request",
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(callChatCompletion({ ...BASE, maxRetries: 3 })).rejects.toThrow();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("wiederholt ein Modellproblem NICHT", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false, status: 400, statusText: "Bad Request",
      text: async () => "Failed to load model: insufficient system resources",
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(callChatCompletion({ ...BASE, maxRetries: 3 })).rejects.toThrow();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("wiederholt ohne maxRetries gar nicht (bisheriges Verhalten)", async () => {
    const fetchMock = vi.fn().mockRejectedValue(netzfehler());
    vi.stubGlobal("fetch", fetchMock);

    await expect(callChatCompletion({ ...BASE })).rejects.toThrow();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run tests/llm-client-retry.test.ts`
Expected: FAIL — es wird jeweils nur einmal aufgerufen

- [ ] **Step 3: Write minimal implementation**

In `src/server/llm-client.ts` das Interface ergänzen:

```typescript
  /**
   * Wie oft ein Aufruf bei einer VORUEBERGEHENDEN Stoerung wiederholt wird
   * (Gesamtzahl der Versuche, nicht zusaetzliche). Ohne Angabe: kein Retry —
   * das bisherige Verhalten bleibt der Default.
   */
  maxRetries?: number;
  /** Basis der Wartezeit; die Stufen sind 1× / 3× / 8×. */
  retryBaseMs?: number;
```

Den Rumpf von `callChatCompletion` in eine innere Funktion ziehen und umwickeln:

```typescript
export async function callChatCompletion(req: CompletionRequest): Promise<CompletionResponse> {
  const attempts = Math.max(1, req.maxRetries ?? 1);
  const baseMs = req.retryBaseMs ?? 500;
  let lastError: unknown;

  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      return await callChatCompletionOnce(req);
    } catch (err) {
      lastError = err;
      const kannWiederholen = attempt < attempts - 1 && isRetryableLlmFailure(err);
      if (!kannWiederholen) throw err;
      await new Promise((resolve) => setTimeout(resolve, retryDelayMs(attempt, baseMs)));
    }
  }
  throw lastError;
}
```

`callChatCompletionOnce` ist der bisherige Rumpf, unverändert — inklusive `reasoningEffort`, `recoverReasoningOnlyMessage` und `classifyHttpError`.

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run tests/llm-client-retry.test.ts`
Expected: PASS (6 Tests)

- [ ] **Step 5: Regression**

Run: `npx vitest run`
Expected: 156 bisherige + 17 neue Tests grün. Besonders `tests/fallback.test.ts` muss grün bleiben — der Fallback-Wechsel darf durch den Retry weder verzögert noch übersprungen werden.

- [ ] **Step 6: Commit**

```bash
git add src/server/llm-client.ts tests/llm-client-retry.test.ts
git commit -m "feat(retry): Completion-Aufruf uebersteht voruebergehende Stoerungen"
```

---

### Task 3: Konfiguration durchreichen und weicheres `max_iterations`

**Files:**
- Modify: `src/server/execute.ts`
- Test: `tests/execute-retry-config.test.ts`

**Interfaces:**
- Produces: `execute` liest `config.maxCompletionRetries` (Default 3) und `config.retryBackoffMs` (Default 500) und reicht sie an **alle drei** Aufrufstellen weiter.

- [ ] **Step 1: Write the failing test**

```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";
import { execute } from "../src/server/execute.js";

const okModels = () => ({ ok: true, status: 200, json: async () => ({ data: [{ id: "m" }] }) });
const finalAnswer = () => ({
  ok: true, status: 200,
  json: async () => ({
    choices: [{ message: { role: "assistant", content: "Fertig." }, finish_reason: "stop" }],
    usage: { prompt_tokens: 3, completion_tokens: 2 },
  }),
});

function makeCtx(overrides: Record<string, unknown> = {}) {
  return {
    runId: "run-1",
    agent: { id: "agent-1", companyId: "company-1", name: "Test", adapterType: "lmstudio_local", adapterConfig: {} },
    config: {
      url: "http://primary:1234", defaultModel: "big",
      fallbackUrl: "", fallbackModel: "",
      probeTimeoutMs: 200, probeRetryBackoffMs: 0, timeoutMs: 5000, maxIterations: 3,
      retryBackoffMs: 1,
      ...overrides,
    },
    context: { paperclipApiUrl: "http://localhost:3100" },
    runtime: { sessionId: null, sessionParams: null, sessionDisplayId: null, taskKey: null },
    onLog: async () => {},
    authToken: "test-auth",
  };
}

describe("execute — Retry-Konfiguration", () => {
  beforeEach(() => { vi.restoreAllMocks(); });

  it("uebersteht einen Netzfehler mitten im Lauf", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(okModels())
      .mockRejectedValueOnce(Object.assign(new Error("fetch failed"), { cause: { code: "ECONNRESET" } }))
      .mockResolvedValue(finalAnswer());
    vi.stubGlobal("fetch", fetchMock);

    const result = await execute(makeCtx({ maxCompletionRetries: 3 }) as never);

    expect(result.exitCode).toBe(0);
  });

  it("gibt ohne Konfiguration drei Versuche als Default", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(okModels())
      .mockRejectedValueOnce(Object.assign(new Error("fetch failed"), { cause: { code: "ECONNRESET" } }))
      .mockResolvedValue(finalAnswer());
    vi.stubGlobal("fetch", fetchMock);

    const result = await execute(makeCtx() as never);

    expect(result.exitCode).toBe(0);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run tests/execute-retry-config.test.ts`
Expected: FAIL — der Netzfehler beendet den Lauf

- [ ] **Step 3: Write minimal implementation**

In `execute.ts` neben `reasoningEffort` lesen:

```typescript
  // Voruebergehende Stoerungen (Netzhaenger, „Model reloaded", 503) sollen einen
  // Lauf nicht toeten — er kann 20 Minuten Arbeit enthalten. Echte 4xx bleiben
  // ungewiederholt, dort greift weiterhin der Wechsel auf das Fallback-Modell.
  const maxCompletionRetries = asNumber(config.maxCompletionRetries, 3);
  const retryBackoffMs = asNumber(config.retryBackoffMs, 500);
```

und an **alle drei** Aufrufstellen weitergeben (`maxRetries: maxCompletionRetries, retryBaseMs: retryBackoffMs`): den primären `callChatCompletion`, die Fallback-Wiederholung, und `streamChatCompletion` für die Abschlusszusammenfassung — Letztere ist beim `reasoningEffort` schon einmal fast übersehen worden.

Für `streamChatCompletion` die gleichen zwei Felder in `StreamRequest` ergänzen und dort dieselbe Schleife anwenden.

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run tests/execute-retry-config.test.ts`
Expected: PASS (2 Tests)

- [ ] **Step 5: Volle Suite und Typprüfung**

```bash
npx vitest run
npx tsc --noEmit
```
Expected: alles grün, keine Typfehler.

- [ ] **Step 6: Bauen und ausliefern**

```bash
npm run build
grep -c "isRetryableLlmFailure" dist/server/llm-client.js   # muss > 0 sein
```
Der Host lädt `dist/`. Ohne Build ist nichts passiert.

- [ ] **Step 7: Commit und Push**

```bash
git add -A
git commit -m "feat(retry): Konfiguration durchgereicht, alle drei Aufrufstellen"
git push
```

---

### Task 4: Live-Verifikation

- [ ] **Step 1: Adapter neu laden**

```bash
launchctl kickstart -k gui/501/ing.paperclip.dev
until curl -s -o /dev/null --max-time 5 http://127.0.0.1:3100/; do sleep 3; done
```

- [ ] **Step 2: Wirkung belegen**

Einen Agenten wecken und im LM-Studio-Protokoll (`~/.lmstudio/server-logs/<jahr-monat>/<datum>.log`) prüfen, dass ein Lauf durchgeht. Dann über einige Tage die Fehlerverteilung vergleichen:

```bash
PGPASSWORD=paperclip psql -h 127.0.0.1 -p 54329 -U paperclip -d paperclip -At -F' | ' -c \
  "select coalesce(error_code,'(null)'), count(*) from heartbeat_runs
   where created_at > now()-interval '7 days' and status in ('failed','timed_out')
   group by 1 order by 2 desc"
```

Erwartung: `llm_unreachable` (83), `adapter_failed` (29) und `llm_error` (16) gehen deutlich zurück. `claude_transient_upstream` (182) bleibt unverändert — anderer Adapter, siehe unten.

- [ ] **Step 3: Ergebnis anhängen**

Die gemessene Verteilung als Abschnitt „Wirkung" an diesen Plan anfügen und committen.

---

## Nicht in diesem Plan (bewusst)

- **`claude_transient_upstream` (182 Fälle, der häufigste Ausfall).** Betrifft den `claude_local`-Adapter, nicht diesen. Dort liegt ausserdem WHI-3876: ein einzelner 429 beendet den Run, und die Continuation setzt `scheduled_retry_attempt` auf 0 zurück — eine Endlosschleife statt einer Deckelung. Das ist ein eigener, dringlicherer Plan.
- **Weiches `max_iterations`** (Spec §3 B.2b: Teilergebnis statt hartem Fehler). Ändert das Ergebnisformat des Adapters und braucht eine Entscheidung, wie die Gegenseite ein Teilergebnis behandelt. Eigener Entwurf.
- **Caps der Manager-Agenten anheben** (Spec §3 B.2a). Konfigurationsfrage, kein Code.
