import type { SelfHealErrorClass } from "./agent-self-heal-classify.js";

/** Backoff-Stufen in Vielfachen des Basis-Cooldowns: 5 min → 15 min → 60 min. */
const BACKOFF_MULTIPLIERS = [1, 3, 12] as const;

/**
 * Stabiler Schluessel je Stoerung. Zweck: dieselbe Stoerung darf das Ledger
 * nicht mit neuen Zeilen fluten, nur weil eine Iterationszahl oder Laufzeit im
 * Fehlertext wechselt.
 */
export function buildErrorFingerprint(input: {
  errorCode: string | null;
  errorText: string | null;
}): string {
  if (input.errorCode) return `code:${input.errorCode}`;
  const text = input.errorText;
  if (!text) return "unknown";
  const normalized = text
    .toLowerCase()
    .replace(/\d+(\.\d+)?/g, "#")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 200);
  return `text:${normalized}`;
}

/** Wann der naechste Versuch fuer diese Stoerung erlaubt ist. */
export function computeNextEligibleAt(
  attemptCount: number,
  now: Date,
  baseCooldownMs: number,
): Date {
  const index = Math.min(Math.max(attemptCount, 0), BACKOFF_MULTIPLIERS.length - 1);
  return new Date(now.getTime() + baseCooldownMs * BACKOFF_MULTIPLIERS[index]);
}

export type { SelfHealErrorClass };

export type SelfHealAction =
  | { kind: "revive" }
  | { kind: "wait_endpoint_down" }
  | { kind: "wait_cooldown" }
  | { kind: "escalate_manager" }
  | { kind: "escalate_human"; reason: string }
  | { kind: "skip"; reason: string };

/**
 * Politik der Selbstheilung — bewusst frei von IO, damit jeder Zweig ohne
 * Datenbank und ohne Netz pruefbar ist.
 *
 * `endpointHealthy === null` heisst „nicht pruefbar" (claude_local hat kein
 * Modell-Listing). Das wird als gesund gewertet; gegen Stuerme schuetzt dort
 * allein der Cooldown.
 */
export function decideSelfHeal(input: {
  errorClass: SelfHealErrorClass;
  agentStatus: string;
  endpointHealthy: boolean | null;
  attemptCount: number;
  nextEligibleAt: Date | null;
  now: Date;
  maxInfraRevives: number;
}): SelfHealAction {
  if (input.agentStatus !== "error") {
    return { kind: "skip", reason: `agent_status_${input.agentStatus}` };
  }
  if (input.nextEligibleAt && input.nextEligibleAt.getTime() > input.now.getTime()) {
    return { kind: "wait_cooldown" };
  }

  switch (input.errorClass) {
    case "infra_transient":
      if (input.attemptCount >= input.maxInfraRevives) {
        return { kind: "escalate_human", reason: "max_infra_revives_exhausted" };
      }
      if (input.endpointHealthy === false) {
        return { kind: "wait_endpoint_down" };
      }
      return { kind: "revive" };

    case "convergence":
      if (input.attemptCount >= 1) {
        return { kind: "escalate_human", reason: "convergence_manager_exhausted" };
      }
      return { kind: "escalate_manager" };

    case "deterministic":
      return { kind: "escalate_human", reason: "deterministic_error" };

    case "unknown":
      return { kind: "escalate_human", reason: "unclassified_error" };
  }
}
