import { describe, expect, it } from "vitest";
import { decideLedgerResolution } from "./agent-self-heal.js";

describe("decideLedgerResolution", () => {
  it("schliesst offene Zeilen bei succeeded", () => {
    expect(decideLedgerResolution("succeeded")).toBe(true);
  });

  it("schliesst offene Zeilen bei cancelled", () => {
    expect(decideLedgerResolution("cancelled")).toBe(true);
  });

  it.each(["failed", "timed_out"] as const)("laesst die Zeile bei %s offen", (outcome) => {
    expect(decideLedgerResolution(outcome)).toBe(false);
  });
});
