import { afterEach, describe, expect, it, vi } from "vitest";
import {
  createSelfHealDeps,
  extractLoadedModelIds,
  extractModelIds,
  pickSelfHealErrorSource,
  runAgentSelfHeal,
  selfHealTickIsNoteworthy,
  tickAgentSelfHeal,
} from "./agent-self-heal.js";

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

describe("Modell-Listen auswerten", () => {
  it("v0: nur `state: loaded` zaehlt", () => {
    const ids = extractLoadedModelIds({
      data: [
        { id: "qwen3.6-35b-a3b-mlx", state: "loaded" },
        { id: "google/gemma-4-31b", state: "not-loaded" },
      ],
    });
    expect(ids && [...ids]).toEqual(["qwen3.6-35b-a3b-mlx"]);
  });

  it("v0 ohne `state` gilt als unbrauchbar (Signal fuer den Rueckfall)", () => {
    expect(extractLoadedModelIds({ data: [{ id: "a" }] })).toBeNull();
    expect(extractLoadedModelIds({ object: "list" })).toBeNull();
    expect(extractLoadedModelIds(null)).toBeNull();
  });

  it("v1 kennt nur Existenz", () => {
    const ids = extractModelIds({ data: [{ id: "a" }, { id: "b" }] });
    expect(ids && [...ids]).toEqual(["a", "b"]);
    expect(extractModelIds("kaputt")).toBeNull();
  });
});

describe("probeEndpoint", () => {
  const probe = (adapterConfig: Record<string, unknown>, adapterType = "lmstudio_local") =>
    createSelfHealDeps({} as never, { heartbeat: { wakeup: async () => undefined } }).probeEndpoint({
      adapterType,
      adapterConfig,
    });

  const jsonResponse = (body: unknown) =>
    ({ ok: true, json: async () => body }) as unknown as Response;

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("meldet krank, wenn das Modell existiert aber NICHT geladen ist", async () => {
    // Genau der I1-Befund: /v1/models listet 18 IDs, davon 9 entladen.
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) =>
        url.includes("/api/v0/models")
          ? jsonResponse({ data: [{ id: "qwen3.6-35b-a3b-mlx", state: "not-loaded" }] })
          : jsonResponse({ data: [{ id: "qwen3.6-35b-a3b-mlx" }] }),
      ),
    );

    await expect(probe({ url: "http://host:1234", model: "qwen3.6-35b-a3b-mlx" })).resolves.toBe(
      false,
    );
  });

  it("meldet gesund, wenn das Modell geladen ist", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse({ data: [{ id: "qwen3.6-35b-a3b-mlx", state: "loaded" }] })),
    );

    await expect(probe({ url: "http://host:1234/", model: "qwen3.6-35b-a3b-mlx" })).resolves.toBe(
      true,
    );
  });

  it("nimmt auch den fallbackModel, wenn nur der geladen ist", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse({ data: [{ id: "google/gemma-4-12b", state: "loaded" }] })),
    );

    await expect(
      probe({ model: "qwen3.6-35b-a3b-mlx", fallbackModel: "google/gemma-4-12b" }),
    ).resolves.toBe(true);
  });

  it("faellt auf /v1/models zurueck, wenn /api/v0/models nichts Brauchbares liefert", async () => {
    const fetchMock = vi.fn(async (url: string) =>
      url.includes("/api/v0/models")
        ? ({ ok: false, json: async () => ({}) } as unknown as Response)
        : jsonResponse({ data: [{ id: "qwen3.6-35b-a3b-mlx" }] }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(probe({ model: "qwen3.6-35b-a3b-mlx" })).resolves.toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("meldet krank, wenn das Endpoint gar nicht antwortet", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("fetch failed");
      }),
    );

    await expect(probe({ model: "qwen3.6-35b-a3b-mlx" })).resolves.toBe(false);
  });

  it("liefert null fuer Nicht-LM-Studio-Adapter, ohne zu netzen", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    await expect(probe({}, "claude_local")).resolves.toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
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

  it("hinterlaesst beim Endpoint-Ausfall eine Spur — ohne Versuchszaehler zu erhoehen", async () => {
    const deps = makeDeps({
      loadErroredAgents: vi.fn().mockResolvedValue([erroredAgent()]),
      probeEndpoint: vi.fn().mockResolvedValue(false),
    });
    await runAgentSelfHeal(deps, OPTS);

    expect(deps.saveLedger).toHaveBeenCalledWith(
      expect.objectContaining({
        agentId: "agent-1",
        errorClass: "infra_transient",
        lastAction: "waited_endpoint_down",
        // Warten ist kein Versuch, und ohne Ledger-Zeile bleibt es bei null:
        // der Agent soll beim naechsten Tick sofort wieder dran sein.
        attemptCount: 0,
        nextEligibleAt: null,
      }),
    );
    expect(deps.logAction).toHaveBeenCalledWith(
      expect.objectContaining({ action: "agent.self_heal.waited_endpoint_down" }),
    );
  });

  it("verlaengert beim Endpoint-Ausfall einen bestehenden Cooldown nicht", async () => {
    const abgelaufen = new Date("2026-08-17T11:50:00.000Z");
    const deps = makeDeps({
      loadErroredAgents: vi.fn().mockResolvedValue([erroredAgent()]),
      probeEndpoint: vi.fn().mockResolvedValue(false),
      loadLedger: vi.fn().mockResolvedValue({ attemptCount: 2, nextEligibleAt: abgelaufen }),
    });
    await runAgentSelfHeal(deps, OPTS);

    expect(deps.saveLedger).toHaveBeenCalledWith(
      expect.objectContaining({ attemptCount: 2, nextEligibleAt: abgelaufen }),
    );
  });

  it("schreibt beim Cooldown-Warten nichts — der Grund steht schon im Ledger", async () => {
    const deps = makeDeps({
      loadErroredAgents: vi.fn().mockResolvedValue([erroredAgent()]),
      loadLedger: vi.fn().mockResolvedValue({
        attemptCount: 1,
        nextEligibleAt: new Date("2026-08-17T12:10:00.000Z"),
      }),
    });
    const result = await runAgentSelfHeal(deps, OPTS);

    expect(result.waited).toBe(1);
    expect(deps.saveLedger).not.toHaveBeenCalled();
    expect(deps.logAction).not.toHaveBeenCalled();
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
    // Die gedeckelten 7 Agenten duerfen keine Strafe kassieren — sie sollen beim
    // naechsten Durchlauf ohne Bremse wieder drankommen. Geprobt wird ohnehin nur
    // einmal, weil alle 9 dieselbe Endpoint-Konfiguration teilen.
    expect(deps.probeEndpoint).toHaveBeenCalledTimes(1);
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

  it("probt jedes Endpoint nur EINMAL pro Durchlauf", async () => {
    // 38 Agenten teilen live dieselbe url — ohne Memoisierung 38 Anfragen.
    const many = Array.from({ length: 6 }, (_, i) => erroredAgent({ id: `agent-${i}` }));
    const deps = makeDeps({ loadErroredAgents: vi.fn().mockResolvedValue(many) });

    const result = await runAgentSelfHeal(deps, { ...OPTS, maxConcurrentRevives: 99 });

    expect(result.revived).toBe(6);
    expect(deps.probeEndpoint).toHaveBeenCalledTimes(1);
  });

  it("probt getrennt, wenn Endpoint oder Modell abweichen", async () => {
    const deps = makeDeps({
      loadErroredAgents: vi.fn().mockResolvedValue([
        erroredAgent({ id: "a" }),
        erroredAgent({ id: "b", adapterConfig: { url: "http://mbp:1234", model: "qwen3.6-35b-a3b-mlx" } }),
        erroredAgent({ id: "c", adapterConfig: { url: "http://localhost:1234", model: "google/gemma-4-31b" } }),
        // Gleiche (leere) Konfiguration, aber anderer Adaptertyp — darf nicht
        // mit den lmstudio_local-Agenten in einen Cache-Eintrag fallen.
        erroredAgent({ id: "d", adapterType: "claude_local", adapterConfig: {} }),
      ]),
    });

    await runAgentSelfHeal(deps, { ...OPTS, maxConcurrentRevives: 99 });

    expect(deps.probeEndpoint).toHaveBeenCalledTimes(4);
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

describe("selfHealTickIsNoteworthy", () => {
  const leer = {
    scanned: 0,
    revived: 0,
    escalatedManager: 0,
    escalatedHuman: 0,
    waited: 0,
    skipped: 0,
    failed: 0,
  };

  it("meldet einen reinen Warte-Durchlauf — sonst bleibt ein Ausfall unsichtbar", () => {
    expect(selfHealTickIsNoteworthy({ ...leer, scanned: 38, waited: 38 })).toBe(true);
  });

  it("schweigt bei einem ereignislosen Durchlauf", () => {
    expect(selfHealTickIsNoteworthy({ ...leer, scanned: 3, skipped: 3 })).toBe(false);
  });
});

describe("tickAgentSelfHeal", () => {
  const TICK_OPTS = { ...OPTS, enabled: true, minIntervalMs: 0 };

  it("startet keinen zweiten Durchlauf, solange der erste laeuft", async () => {
    // index.ts ruft mit `void`. Ohne die Sperre laufen bei einem haengenden
    // Endpoint zwei Durchlaeufe parallel und maxConcurrentRevives gilt je
    // Durchlauf statt global.
    let release!: () => void;
    const blocked = new Promise<void>((resolve) => {
      release = resolve;
    });
    const deps = makeDeps({
      loadErroredAgents: vi.fn().mockImplementation(async () => {
        await blocked;
        return [];
      }),
    });

    const first = tickAgentSelfHeal(deps, TICK_OPTS);
    await expect(tickAgentSelfHeal(deps, TICK_OPTS)).resolves.toBeNull();
    expect(deps.loadErroredAgents).toHaveBeenCalledTimes(1);

    release();
    await expect(first).resolves.toMatchObject({ scanned: 0 });

    // Nach dem Ende ist die Sperre wieder offen.
    await expect(tickAgentSelfHeal(deps, TICK_OPTS)).resolves.toMatchObject({ scanned: 0 });
    expect(deps.loadErroredAgents).toHaveBeenCalledTimes(2);
  });

  it("gibt die Sperre auch frei, wenn der Durchlauf wirft", async () => {
    const deps = makeDeps({
      loadErroredAgents: vi.fn().mockRejectedValue(new Error("DB weg")),
    });

    await expect(tickAgentSelfHeal(deps, TICK_OPTS)).rejects.toThrow("DB weg");
    // Waere `running` haengen geblieben, kaeme hier null statt eines Ergebnisses.
    await expect(
      tickAgentSelfHeal(makeDeps(), TICK_OPTS),
    ).resolves.toMatchObject({ scanned: 0 });
  });

  it("laeuft nicht, wenn abgeschaltet", async () => {
    const deps = makeDeps();
    await expect(
      tickAgentSelfHeal(deps, { ...TICK_OPTS, enabled: false }),
    ).resolves.toBeNull();
    expect(deps.loadErroredAgents).not.toHaveBeenCalled();
  });
});
