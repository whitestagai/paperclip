import { describe, expect, it, vi } from "vitest";
import {
  reconcileHealedStrandedIssues,
  type IncidentClosureDeps,
} from "./incident-closure.js";

const INCIDENT_AT = new Date("2026-08-21T12:00:00.000Z");
const HEALED_AT = new Date("2026-08-21T12:30:00.000Z");

const RECOVERY = {
  id: "recovery-1",
  companyId: "company-1",
  originId: "source-1",
  createdAt: INCIDENT_AT,
};

/**
 * Baut Deps, die den Gutfall abbilden. Jeder Test veraendert nur den Punkt,
 * um den es ihm geht — so bleibt sichtbar, welche Bedingung das Verhalten kippt.
 */
function makeDeps(overrides: Partial<IncidentClosureDeps> = {}) {
  const calls: string[] = [];
  const deps: IncidentClosureDeps = {
    loadOpenStrandedRecoveries: async () => [RECOVERY],
    loadSourceIssue: async () => ({ id: "source-1", assigneeAgentId: "agent-1" }),
    findHealingEvidence: async () => HEALED_AT,
    hasActiveRun: async () => false,
    removeBlocker: async () => {
      calls.push("removeBlocker");
      return true;
    },
    cancelRecoveryIssue: async () => {
      calls.push("cancelRecoveryIssue");
    },
    wakeAgent: async () => {
      calls.push("wakeAgent");
    },
    logAction: async () => {},
    ...overrides,
  };
  return { deps, calls };
}

describe("reconcileHealedStrandedIssues", () => {
  it("gibt die geparkte Arbeit zurueck, wenn der Agent nachweislich wieder lief", async () => {
    const { deps, calls } = makeDeps();

    const result = await reconcileHealedStrandedIssues(deps);

    expect(result.closed).toBe(1);
    expect(calls).toEqual(["removeBlocker", "cancelRecoveryIssue", "wakeAgent"]);
  });

  it("entblockt VOR dem Stilllegen — ein stillgelegter Blocker waere unsichtbar tot", async () => {
    const { deps, calls } = makeDeps();

    await reconcileHealedStrandedIssues(deps);

    expect(calls.indexOf("removeBlocker")).toBeLessThan(calls.indexOf("cancelRecoveryIssue"));
  });

  it("weckt zuletzt — der einzige Schritt mit Aussenwirkung", async () => {
    const { deps, calls } = makeDeps();

    await reconcileHealedStrandedIssues(deps);

    expect(calls.at(-1)).toBe("wakeAgent");
  });

  it("weckt den Ur-Agenten auf dem QUELL-Issue, nicht auf dem Recovery-Issue", async () => {
    const wakeAgent = vi.fn(async () => {});
    const { deps } = makeDeps({ wakeAgent });

    await reconcileHealedStrandedIssues(deps);

    expect(wakeAgent).toHaveBeenCalledWith("agent-1", "source-1");
  });

  it("ruehrt nichts an, wenn der Agent seit dem Stranden nie durchlief", async () => {
    const { deps, calls } = makeDeps({ findHealingEvidence: async () => null });

    const result = await reconcileHealedStrandedIssues(deps);

    expect(result.notHealed).toBe(1);
    expect(result.closed).toBe(0);
    expect(calls).toEqual([]);
  });

  it("ruehrt nichts an, solange auf dem Recovery-Issue ein Lauf aktiv ist", async () => {
    const { deps, calls } = makeDeps({ hasActiveRun: async () => true });

    const result = await reconcileHealedStrandedIssues(deps);

    expect(result.waitedActiveRun).toBe(1);
    expect(calls).toEqual([]);
  });

  it("ueberspringt ein Recovery-Issue, dessen Quell-Issue es nicht mehr gibt", async () => {
    const { deps, calls } = makeDeps({ loadSourceIssue: async () => null });

    const result = await reconcileHealedStrandedIssues(deps);

    expect(result.skipped).toBe(1);
    expect(calls).toEqual([]);
  });

  it("ueberspringt ein Quell-Issue ohne Assignee", async () => {
    const { deps, calls } = makeDeps({
      loadSourceIssue: async () => ({ id: "source-1", assigneeAgentId: null }),
    });

    const result = await reconcileHealedStrandedIssues(deps);

    expect(result.skipped).toBe(1);
    expect(calls).toEqual([]);
  });

  it("laesst das Issue frei, wenn das Wecken scheitert — die harmlosere Richtung", async () => {
    const { deps, calls } = makeDeps({
      wakeAgent: async () => {
        throw new Error("wakeup abgelehnt");
      },
    });

    const result = await reconcileHealedStrandedIssues(deps);

    // Blocker weg und Recovery stillgelegt: ein freies Issue ohne Weckruf ist
    // auffindbar, ein halb entblocktes nicht.
    expect(calls).toEqual(["removeBlocker", "cancelRecoveryIssue"]);
    expect(result.closed).toBe(1);
    expect(result.wakeFailed).toBe(1);
  });

  it("verarbeitet die uebrigen weiter, wenn ein Recovery-Issue wirft", async () => {
    const second = { ...RECOVERY, id: "recovery-2", originId: "source-2" };
    const { deps, calls } = makeDeps({
      loadOpenStrandedRecoveries: async () => [RECOVERY, second],
      loadSourceIssue: async (_companyId: string, issueId: string) => {
        if (issueId === "source-1") throw new Error("DB weg");
        return { id: "source-2", assigneeAgentId: "agent-2" };
      },
    });

    const result = await reconcileHealedStrandedIssues(deps);

    expect(result.failed).toBe(1);
    expect(result.closed).toBe(1);
    expect(calls).toEqual(["removeBlocker", "cancelRecoveryIssue", "wakeAgent"]);
  });

  it("protokolliert jeden Abschluss — ein Waechter ohne Spur ist wertlos", async () => {
    const logAction = vi.fn(async () => {});
    const { deps } = makeDeps({ logAction });

    await reconcileHealedStrandedIssues(deps);

    expect(logAction).toHaveBeenCalledWith(
      expect.objectContaining({
        companyId: "company-1",
        action: "recovery.incident_closed",
      }),
    );
  });
});
