import { describe, expect, it } from "vitest";
import { classifySelfHealError } from "./agent-self-heal-classify.js";

describe("classifySelfHealError — nach error_code", () => {
  it.each([
    ["claude_transient_upstream", "infra_transient"],
    ["llm_unreachable", "infra_transient"],
    ["timeout", "infra_transient"],
    ["process_lost", "infra_transient"],
    ["llm_error", "infra_transient"],
    ["max_iterations", "convergence"],
    ["claude_auth_required", "deterministic"],
    ["adapter_failed", "unknown"],
  ])("ordnet %s als %s ein", (code, expected) => {
    expect(classifySelfHealError({ errorCode: code, errorText: null })).toBe(expected);
  });

  it("bevorzugt error_code gegenueber widersprechendem Text", () => {
    expect(
      classifySelfHealError({ errorCode: "max_iterations", errorText: "fetch failed" }),
    ).toBe("convergence");
  });
});

describe("classifySelfHealError — Rueckfall auf den Fehlertext", () => {
  it.each([
    ["LLM network error: ECONNREFUSED (fetch failed)", "infra_transient"],
    ["LLM call timed out: The operation was aborted due to timeout", "infra_transient"],
    ["Failed to load model: insufficient system resources", "infra_transient"],
    ["Max iterations (8) reached without final answer", "convergence"],
    ["400 Bad Request: content was blocked", "deterministic"],
    ["Expecting value: line 1 column 1 (parse error)", "deterministic"],
    ["could not authenticate", "deterministic"],
  ])("ordnet %j als %s ein", (text, expected) => {
    expect(classifySelfHealError({ errorCode: null, errorText: text })).toBe(expected);
  });

  it("faellt bei voelliger Unkenntnis auf unknown zurueck", () => {
    expect(classifySelfHealError({ errorCode: null, errorText: "irgendwas neues" })).toBe("unknown");
    expect(classifySelfHealError({ errorCode: null, errorText: null })).toBe("unknown");
  });
});
