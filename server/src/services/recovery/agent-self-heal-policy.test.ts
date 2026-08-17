import { describe, expect, it } from "vitest";
import { buildErrorFingerprint, computeNextEligibleAt } from "./agent-self-heal-policy.js";

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
