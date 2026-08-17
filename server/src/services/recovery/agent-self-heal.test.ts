import { describe, expect, it, vi } from "vitest";
import { runAgentSelfHeal } from "./agent-self-heal.js";

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
  ...over,
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
      }),
    );
    expect(deps.logAction).toHaveBeenCalledWith(
      expect.objectContaining({ action: "agent.self_heal.revived" }),
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
