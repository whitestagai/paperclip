import { describe, expect, it, vi } from "vitest";
import { pickSelfHealErrorSource, runAgentSelfHeal } from "./agent-self-heal.js";

const NOW = new Date("2026-08-17T12:00:00.000Z");
const OPTS = { maxInfraRevives: 3, cooldownMs: 300_000, maxConcurrentRevives: 5 };

function makeDeps(overrides: Partial<Parameters<typeof runAgentSelfHeal>[0]> = {}) {
  const deps = {
    loadErroredAgents: vi.fn().mockResolvedValue([]),
    loadFleet: vi.fn().mockResolvedValue([]),
    loadLedger: vi.fn().mockResolvedValue(null),
    saveLedger: vi.fn().mockResolvedValue(undefined),
    probeEndpoint: vi.fn().mockResolvedValue(true),
    reviveAgent: vi.fn().mockResolvedValue(undefined),
    wakeAgent: vi.fn().mockResolvedValue(undefined),
    escalateToManager: vi.fn().mockResolvedValue(undefined),
    escalateToHuman: vi.fn().mockResolvedValue(undefined),
    logAction: vi.fn().mockResolvedValue(undefined),
    now: () => NOW,
    ...overrides,
  };
  return deps as Parameters<typeof runAgentSelfHeal>[0] & typeof deps;
}

const erroredAgent = (over: Record<string, unknown> = {}) => ({
  id: "agent-1",
  companyId: "company-1",
  name: "SEO/GEO",
  status: "error",
  reportsTo: "cto",
  adapterType: "lmstudio_local",
  adapterConfig: { url: "http://localhost:1234", model: "qwen3.6-35b-a3b-mlx" },
  lastErrorCode: "llm_unreachable",
  lastErrorText: null,
  hasPendingRun: false,
  ...over,
});

const LIVE_RUNTIME_ERROR =
  "Claude run failed: subtype=success: API Error: Server is temporarily limiting requests";

describe("pickSelfHealErrorSource", () => {
  it("faellt auf agent_runtime_state.last_error zurueck, wenn der Lauf keinen Text hat", () => {
    // Live-Fall: neuester Fehllauf ohne Fehlerfelder, Wahrheit im Runtime-State.
    expect(
      pickSelfHealErrorSource({ run: null, runtimeLastError: LIVE_RUNTIME_ERROR }),
    ).toEqual({ lastErrorCode: null, lastErrorText: LIVE_RUNTIME_ERROR });
  });

  it("bevorzugt den Lauf, wenn er selbst Code und Text traegt", () => {
    expect(
      pickSelfHealErrorSource({
        run: { errorCode: "llm_unreachable", error: "fetch failed" },
        runtimeLastError: LIVE_RUNTIME_ERROR,
      }),
    ).toEqual({ lastErrorCode: "llm_unreachable", lastErrorText: "fetch failed" });
  });

  it("behandelt Leerstrings als fehlend, sonst blockiert '' den Rueckfall", () => {
    expect(
      pickSelfHealErrorSource({
        run: { errorCode: "  ", error: "" },
        runtimeLastError: LIVE_RUNTIME_ERROR,
      }),
    ).toEqual({ lastErrorCode: null, lastErrorText: LIVE_RUNTIME_ERROR });
  });
});

describe("runAgentSelfHeal", () => {
  it("tut nichts, wenn kein Agent in error steht", async () => {
    const deps = makeDeps();
    const result = await runAgentSelfHeal(deps, OPTS);
    expect(result).toMatchObject({ scanned: 0, revived: 0 });
    expect(deps.reviveAgent).not.toHaveBeenCalled();
  });

  it("belebt einen infra_transient-Agenten bei gesundem Endpoint und weckt ihn", async () => {
    const deps = makeDeps({ loadErroredAgents: vi.fn().mockResolvedValue([erroredAgent()]) });
    const result = await runAgentSelfHeal(deps, OPTS);

    expect(deps.reviveAgent).toHaveBeenCalledWith("agent-1");
    expect(deps.wakeAgent).toHaveBeenCalledWith("agent-1", expect.stringContaining("self_heal"));
    expect(result.revived).toBe(1);
  });

  it("belebt den Live-Fall: Fehlertext nur im Runtime-State, kein error_code", async () => {
    // Ohne den Rueckfall auf agent_runtime_state.last_error waere lastErrorText
    // null → Klasse `unknown` → escalate_human. Genau der C1-Befund.
    const deps = makeDeps({
      loadErroredAgents: vi.fn().mockResolvedValue([
        erroredAgent({ lastErrorCode: null, lastErrorText: LIVE_RUNTIME_ERROR }),
      ]),
    });
    const result = await runAgentSelfHeal(deps, OPTS);

    expect(deps.escalateToHuman).not.toHaveBeenCalled();
    expect(deps.reviveAgent).toHaveBeenCalledWith("agent-1");
    expect(result.revived).toBe(1);
    expect(deps.saveLedger).toHaveBeenCalledWith(
      expect.objectContaining({ errorClass: "infra_transient", lastAction: "revived" }),
    );
  });

  it("haelt sich raus, wenn schon ein Lauf ansteht (scheduled_retry/queued)", async () => {
    const deps = makeDeps({
      loadErroredAgents: vi.fn().mockResolvedValue([erroredAgent({ hasPendingRun: true })]),
    });
    const result = await runAgentSelfHeal(deps, OPTS);

    expect(result.skipped).toBe(1);
    expect(deps.reviveAgent).not.toHaveBeenCalled();
    expect(deps.wakeAgent).not.toHaveBeenCalled();
    expect(deps.probeEndpoint).not.toHaveBeenCalled();
    expect(deps.loadLedger).not.toHaveBeenCalled();
  });

  it("belebt NICHT, wenn das Endpoint down ist", async () => {
    const deps = makeDeps({
      loadErroredAgents: vi.fn().mockResolvedValue([erroredAgent()]),
      probeEndpoint: vi.fn().mockResolvedValue(false),
    });
    const result = await runAgentSelfHeal(deps, OPTS);

    expect(deps.reviveAgent).not.toHaveBeenCalled();
    expect(result.waited).toBe(1);
  });

  it("respektiert den Cooldown aus dem Ledger", async () => {
    const deps = makeDeps({
      loadErroredAgents: vi.fn().mockResolvedValue([erroredAgent()]),
      loadLedger: vi.fn().mockResolvedValue({
        attemptCount: 1,
        nextEligibleAt: new Date("2026-08-17T12:10:00.000Z"),
      }),
    });
    const result = await runAgentSelfHeal(deps, OPTS);

    expect(deps.reviveAgent).not.toHaveBeenCalled();
    expect(deps.probeEndpoint).not.toHaveBeenCalled();
    expect(result.waited).toBe(1);
  });

  it("eskaliert max_iterations an den lebenden Vorgesetzten", async () => {
    const deps = makeDeps({
      loadErroredAgents: vi.fn().mockResolvedValue([
        erroredAgent({ lastErrorCode: "max_iterations" }),
      ]),
      loadFleet: vi.fn().mockResolvedValue([
        { id: "agent-1", reportsTo: "cto", status: "error" },
        { id: "cto", reportsTo: null, status: "idle" },
      ]),
    });
    const result = await runAgentSelfHeal(deps, OPTS);

    expect(deps.escalateToManager).toHaveBeenCalledWith(
      expect.objectContaining({ agentId: "agent-1", managerAgentId: "cto" }),
    );
    expect(deps.reviveAgent).not.toHaveBeenCalled();
    expect(result.escalatedManager).toBe(1);
  });

  it("gibt an den Menschen ab, wenn der Vorgesetzte selbst tot ist", async () => {
    const deps = makeDeps({
      loadErroredAgents: vi.fn().mockResolvedValue([
        erroredAgent({ lastErrorCode: "max_iterations" }),
      ]),
      loadFleet: vi.fn().mockResolvedValue([
        { id: "agent-1", reportsTo: "cto", status: "error" },
        { id: "cto", reportsTo: null, status: "error" },
      ]),
    });
    const result = await runAgentSelfHeal(deps, OPTS);

    expect(deps.escalateToHuman).toHaveBeenCalled();
    expect(result.escalatedHuman).toBe(1);
  });

  it("eskaliert deterministische Fehler ohne jeden Retry", async () => {
    const deps = makeDeps({
      loadErroredAgents: vi.fn().mockResolvedValue([
        erroredAgent({ lastErrorCode: "claude_auth_required" }),
      ]),
    });
    await runAgentSelfHeal(deps, OPTS);

    expect(deps.reviveAgent).not.toHaveBeenCalled();
    expect(deps.probeEndpoint).not.toHaveBeenCalled();
    expect(deps.escalateToHuman).toHaveBeenCalled();
  });

  it("deckelt die Wiederbelebungen pro Tick", async () => {
    const many = Array.from({ length: 9 }, (_, i) => erroredAgent({ id: `agent-${i}` }));
    const deps = makeDeps({ loadErroredAgents: vi.fn().mockResolvedValue(many) });

    const result = await runAgentSelfHeal(deps, { ...OPTS, maxConcurrentRevives: 2 });

    expect(deps.reviveAgent).toHaveBeenCalledTimes(2);
    expect(result.revived).toBe(2);
    // Die gedeckelten 7 Agenten duerfen weder proben noch eine Strafe kassieren —
    // sie sollen beim naechsten Durchlauf ohne Bremse wieder drankommen.
    expect(deps.probeEndpoint).toHaveBeenCalledTimes(2);
    expect(deps.saveLedger).toHaveBeenCalledTimes(2);
    expect(deps.logAction).toHaveBeenCalledTimes(2);
  });

  it("schreibt jede Aktion ins Ledger und ins Protokoll", async () => {
    const deps = makeDeps({ loadErroredAgents: vi.fn().mockResolvedValue([erroredAgent()]) });
    await runAgentSelfHeal(deps, OPTS);

    expect(deps.saveLedger).toHaveBeenCalledWith(
      expect.objectContaining({
        agentId: "agent-1",
        errorClass: "infra_transient",
        fingerprint: "code:llm_unreachable",
        attemptCount: 1,
        lastAction: "revived",
        // computeNextEligibleAt muss mit dem ALTEN attemptCount (0) rechnen,
        // nicht mit dem neu gespeicherten (1) — sonst kippt die 5/15/60-Progression.
        nextEligibleAt: new Date("2026-08-17T12:05:00.000Z"),
      }),
    );
    expect(deps.logAction).toHaveBeenCalledWith(
      expect.objectContaining({ action: "agent.self_heal.revived" }),
    );
  });

  it("skip-Zweig: falscher Agenten-Status wird gezaehlt, ohne Probe oder Revive", async () => {
    const deps = makeDeps({
      loadErroredAgents: vi.fn().mockResolvedValue([erroredAgent({ status: "idle" })]),
    });
    const result = await runAgentSelfHeal(deps, OPTS);

    expect(result.skipped).toBe(1);
    expect(deps.reviveAgent).not.toHaveBeenCalled();
    expect(deps.probeEndpoint).not.toHaveBeenCalled();
  });

  it("failed-Zweig: ein werfender reviveAgent bekommt Protokoll UND Ledger-Bremse", async () => {
    const deps = makeDeps({
      loadErroredAgents: vi.fn().mockResolvedValue([erroredAgent()]),
      reviveAgent: vi.fn().mockRejectedValue(new Error("resume schlug fehl")),
    });
    const result = await runAgentSelfHeal(deps, OPTS);

    expect(result.failed).toBe(1);
    expect(deps.logAction).toHaveBeenCalledWith(
      expect.objectContaining({ action: "agent.self_heal.failed" }),
    );
    expect(deps.saveLedger).toHaveBeenCalledWith(
      expect.objectContaining({ lastAction: "failed" }),
    );
  });

  it("laesst ein Scheitern an einem Agenten die uebrigen nicht mitreissen", async () => {
    const deps = makeDeps({
      loadErroredAgents: vi.fn().mockResolvedValue([
        erroredAgent({ id: "agent-kaputt" }),
        erroredAgent({ id: "agent-ok" }),
      ]),
      reviveAgent: vi.fn().mockImplementation(async (id: string) => {
        if (id === "agent-kaputt") throw new Error("resume schlug fehl");
      }),
    });

    const result = await runAgentSelfHeal(deps, OPTS);

    expect(result.revived).toBe(1);
    expect(deps.wakeAgent).toHaveBeenCalledWith("agent-ok", expect.any(String));
  });
});
