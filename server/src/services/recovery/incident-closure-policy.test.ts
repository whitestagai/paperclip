import { describe, expect, it } from "vitest";
import { decideIncidentClosure } from "./incident-closure-policy.js";

/**
 * Zeitanker der Tests: das Recovery-Issue entstand um 12:00. Alles, was den
 * Agenten davor geheilt hat, ist fuer diesen Vorfall wertlos.
 */
const RECOVERY_CREATED_AT = new Date("2026-08-21T12:00:00Z");
const AFTER = new Date("2026-08-21T12:30:00Z");
const BEFORE = new Date("2026-08-21T11:30:00Z");

function input(overrides: Partial<Parameters<typeof decideIncidentClosure>[0]> = {}) {
  return {
    assigneeAgentId: "agent-1",
    recoveryCreatedAt: RECOVERY_CREATED_AT,
    latestHealedAt: AFTER,
    hasActiveRun: false,
    ...overrides,
  };
}

describe("decideIncidentClosure", () => {
  it("schliesst, wenn der Agent nach dem Stranden nachweislich wieder lief", () => {
    expect(decideIncidentClosure(input())).toEqual({ kind: "close" });
  });

  it("wartet, solange auf dem Recovery-Issue ein Lauf aktiv ist", () => {
    expect(decideIncidentClosure(input({ hasActiveRun: true }))).toEqual({
      kind: "wait_active_run",
    });
  });

  it("tut nichts, wenn der Agent seit dem Stranden nie durchlief", () => {
    expect(decideIncidentClosure(input({ latestHealedAt: null }))).toEqual({
      kind: "not_healed",
    });
  });

  it("schliesst NICHT, wenn die Heilung aelter ist als das Recovery-Issue", () => {
    // Der Kern der Sache: eine Heilung von vorhin belegt nicht, dass der
    // Agent den Vorfall ueberstanden hat, der danach entstand.
    expect(decideIncidentClosure(input({ latestHealedAt: BEFORE }))).toEqual({
      kind: "not_healed",
    });
  });

  it("schliesst NICHT, wenn Heilung und Recovery-Issue exakt gleich alt sind", () => {
    // Gleichstand ist kein Beleg: die Reihenfolge ist dann nicht entscheidbar.
    expect(decideIncidentClosure(input({ latestHealedAt: RECOVERY_CREATED_AT }))).toEqual({
      kind: "not_healed",
    });
  });

  it("ueberspringt ein Quell-Issue ohne Assignee", () => {
    expect(decideIncidentClosure(input({ assigneeAgentId: null }))).toEqual({
      kind: "skip",
      reason: "no_assignee",
    });
  });

  it("prueft den Assignee vor der Heilung — ohne Agenten gibt es keine Evidenz", () => {
    expect(decideIncidentClosure(input({ assigneeAgentId: null, latestHealedAt: null }))).toEqual({
      kind: "skip",
      reason: "no_assignee",
    });
  });

  it("schuetzt laufende Arbeit auch dann, wenn gar keine Heilung vorliegt", () => {
    // Reihenfolge-Absicherung: 'not_healed' fuehrt zu keiner Aktion, aber die
    // Antwort muss trotzdem eindeutig sein, damit die Zaehler stimmen.
    expect(decideIncidentClosure(input({ latestHealedAt: null, hasActiveRun: true }))).toEqual({
      kind: "not_healed",
    });
  });
});
