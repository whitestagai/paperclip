/**
 * Ordnet den Ausgang eines gescheiterten Heartbeat-Runs einer Fehlerklasse zu.
 *
 * Primaerquelle ist `heartbeat_runs.error_code` — ein gepflegtes, strukturiertes
 * Feld. Der Textabgleich ist nur der Rueckfall fuer Laeufe ohne Code (aeltere
 * Zeilen, Fremdadapter).
 */
export type SelfHealErrorClass =
  | "infra_transient"
  | "convergence"
  | "deterministic"
  | "unknown";

/** Gemessene Verteilung siehe Plan-Abschnitt „Abweichungen von der Spec". */
const CLASS_BY_ERROR_CODE: Record<string, SelfHealErrorClass> = {
  claude_transient_upstream: "infra_transient",
  llm_unreachable: "infra_transient",
  llm_error: "infra_transient",
  timeout: "infra_transient",
  process_lost: "infra_transient",
  max_iterations: "convergence",
  claude_auth_required: "deterministic",
  // adapter_failed bleibt bewusst ungenannt: der Code deckt sowohl transiente
  // als auch deterministische Ursachen ab, also konservativ als unknown
  // behandeln (eskalieren statt blind wiederholen).
};

const INFRA_TEXT = /fetch failed|timed?\s*out|timeout|insufficient (system )?resources|econnreset|econnrefused|socket hang up|temporarily limiting/i;
const CONVERGENCE_TEXT = /max iterations/i;
const DETERMINISTIC_TEXT = /\b400\b|blocked|parse|authenticate/i;

export function classifySelfHealError(input: {
  errorCode: string | null;
  errorText: string | null;
}): SelfHealErrorClass {
  if (input.errorCode) {
    return CLASS_BY_ERROR_CODE[input.errorCode] ?? "unknown";
  }
  const text = input.errorText ?? "";
  if (!text) return "unknown";
  if (CONVERGENCE_TEXT.test(text)) return "convergence";
  if (INFRA_TEXT.test(text)) return "infra_transient";
  if (DETERMINISTIC_TEXT.test(text)) return "deterministic";
  return "unknown";
}
