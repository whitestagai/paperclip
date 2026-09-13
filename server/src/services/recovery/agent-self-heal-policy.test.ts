import { describe, expect, it } from "vitest";
import {
  buildErrorFingerprint,
  computeNextEligibleAt,
  decideSelfHeal,
  resolveEscalationTarget,
} from "./agent-self-heal-policy.js";

describe("buildErrorFingerprint", () => {
  it("nimmt den error_code, wenn vorhanden", () => {
    expect(buildErrorFingerprint({ errorCode: "llm_unreachable", errorText: "egal" }))
      .toBe("code:llm_unreachable");
  });

  it("normalisiert wechselnde Zahlen und Zeitangaben im Text weg", () => {
    const a = buildErrorFingerprint({ errorCode: null, errorText: "Max iterations (8) reached after 12.4s" });
    const b = buildErrorFingerprint({ errorCode: null, errorText: "Max iterations (12) reached after 91.7s" });
    expect(a).toBe(b);
  });

  it("unterscheidet verschiedene Stoerungen", () => {
    const a = buildErrorFingerprint({ errorCode: null, errorText: "fetch failed" });
    const b = buildErrorFingerprint({ errorCode: null, errorText: "could not authenticate" });
    expect(a).not.toBe(b);
  });

  it("liefert einen stabilen Wert ohne jede Information", () => {
    expect(buildErrorFingerprint({ errorCode: null, errorText: null })).toBe("unknown");
  });
});

describe("computeNextEligibleAt — exponentiell 5/15/60 min", () => {
  const now = new Date("2026-08-17T12:00:00.000Z");
  const base = 300_000;

  it.each([
    [0, "2026-08-17T12:05:00.000Z"],
    [1, "2026-08-17T12:15:00.000Z"],
    [2, "2026-08-17T13:00:00.000Z"],
  ])("Versuch %i wartet bis %s", (attempts, expected) => {
    expect(computeNextEligibleAt(attempts, now, base).toISOString()).toBe(expected);
  });

  it("deckelt den Backoff bei 60 Minuten", () => {
    expect(computeNextEligibleAt(9, now, base).toISOString()).toBe("2026-08-17T13:00:00.000Z");
  });
});

const base = {
  errorClass: "infra_transient" as const,
  agentStatus: "error",
  endpointHealthy: true as boolean | null,
  attemptCount: 0,
  nextEligibleAt: null as Date | null,
  now: new Date("2026-08-17T12:00:00.000Z"),
  maxInfraRevives: 3,
};

describe("decideSelfHeal — Schutzgitter", () => {
  it.each(["idle", "running", "paused", "terminated", "pending_approval"])(
    "ruehrt einen Agenten in %s nicht an",
    (status) => {
      expect(decideSelfHeal({ ...base, agentStatus: status }).kind).toBe("skip");
    },
  );

  it("wartet, solange der Cooldown laeuft", () => {
    const action = decideSelfHeal({
      ...base,
      nextEligibleAt: new Date("2026-08-17T12:05:00.000Z"),
    });
    expect(action.kind).toBe("wait_cooldown");
  });

  it("handelt, sobald der Cooldown abgelaufen ist", () => {
    const action = decideSelfHeal({
      ...base,
      nextEligibleAt: new Date("2026-08-17T11:59:00.000Z"),
    });
    expect(action.kind).toBe("revive");
  });
});

describe("decideSelfHeal — infra_transient", () => {
  it("belebt wieder, wenn das Endpoint gesund ist", () => {
    expect(decideSelfHeal(base).kind).toBe("revive");
  });

  it("wartet, wenn das Endpoint down ist", () => {
    expect(decideSelfHeal({ ...base, endpointHealthy: false }).kind).toBe("wait_endpoint_down");
  });

  it("belebt auch, wenn die Gesundheit nicht pruefbar ist (claude_local)", () => {
    expect(decideSelfHeal({ ...base, endpointHealthy: null }).kind).toBe("revive");
  });

  it("gibt nach MAX_INFRA_REVIVES an den Menschen ab", () => {
    const action = decideSelfHeal({ ...base, attemptCount: 3 });
    expect(action).toEqual({ kind: "escalate_human", reason: "max_infra_revives_exhausted" });
  });
});

describe("decideSelfHeal — uebrige Klassen", () => {
  it("eskaliert convergence an den Vorgesetzten, ohne Neustart", () => {
    expect(decideSelfHeal({ ...base, errorClass: "convergence" }).kind).toBe("escalate_manager");
  });

  it("eskaliert convergence nach einem Versuch an den Menschen", () => {
    const action = decideSelfHeal({ ...base, errorClass: "convergence", attemptCount: 1 });
    expect(action).toEqual({ kind: "escalate_human", reason: "convergence_manager_exhausted" });
  });

  it.each(["deterministic", "unknown"] as const)(
    "eskaliert %s sofort an den Menschen, ohne Auto-Retry",
    (errorClass) => {
      const action = decideSelfHeal({ ...base, errorClass });
      expect(action.kind).toBe("escalate_human");
    },
  );

  it("eskaliert deterministic auch bei gesundem Endpoint nicht in ein revive", () => {
    const action = decideSelfHeal({ ...base, errorClass: "deterministic", endpointHealthy: true });
    expect(action.kind).not.toBe("revive");
  });
});

const fleet = [
  { id: "spezialist", reportsTo: "cto", status: "error" },
  { id: "cto", reportsTo: "ceo", status: "idle" },
  { id: "ceo", reportsTo: null, status: "idle" },
];

describe("resolveEscalationTarget", () => {
  it("nimmt den direkten Vorgesetzten, wenn er lebt", () => {
    expect(resolveEscalationTarget({ agentId: "spezialist", agents: fleet }))
      .toEqual({ kind: "agent", agentId: "cto" });
  });

  it("ueberspringt einen toten Vorgesetzten", () => {
    const withDeadCto = fleet.map((a) => (a.id === "cto" ? { ...a, status: "error" } : a));
    expect(resolveEscalationTarget({ agentId: "spezialist", agents: withDeadCto }))
      .toEqual({ kind: "agent", agentId: "ceo" });
  });

  it.each(["error", "terminated", "paused"])("wertet Status %s als nicht tragfaehig", (status) => {
    const broken = fleet.map((a) => (a.id === "cto" ? { ...a, status } : a));
    expect(resolveEscalationTarget({ agentId: "spezialist", agents: broken }))
      .toEqual({ kind: "agent", agentId: "ceo" });
  });

  it("gibt an den Menschen ab, wenn die ganze Kette tot ist", () => {
    const allDead = fleet.map((a) => (a.id === "spezialist" ? a : { ...a, status: "error" }));
    expect(resolveEscalationTarget({ agentId: "spezialist", agents: allDead }))
      .toEqual({ kind: "human", reason: "chain_exhausted" });
  });

  it("gibt an den Menschen ab, wenn es keinen Vorgesetzten gibt", () => {
    expect(resolveEscalationTarget({ agentId: "ceo", agents: fleet }))
      .toEqual({ kind: "human", reason: "no_manager" });
  });

  it("laeuft bei einem Zyklus in der Kette nicht endlos", () => {
    const cyclic = [
      { id: "a", reportsTo: "b", status: "error" },
      { id: "b", reportsTo: "a", status: "error" },
    ];
    expect(resolveEscalationTarget({ agentId: "a", agents: cyclic }))
      .toEqual({ kind: "human", reason: "chain_exhausted" });
  });
});
