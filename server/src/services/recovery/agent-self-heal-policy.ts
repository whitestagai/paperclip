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
