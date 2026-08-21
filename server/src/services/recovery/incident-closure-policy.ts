export type IncidentClosureAction =
  | { kind: "close" }
  | { kind: "wait_active_run" }
  | { kind: "not_healed" }
  | { kind: "skip"; reason: string };

/**
 * Entscheidet, ob ein offenes Recovery-Issue abgeschlossen und seine geparkte
 * Arbeit freigegeben werden darf — bewusst frei von IO, damit jeder Zweig ohne
 * Datenbank und ohne Netz pruefbar ist (dasselbe Muster wie `decideSelfHeal`).
 *
 * `latestHealedAt` ist das juengste `resolved_at` aus dem Selbstheilungs-Ledger
 * des zustaendigen Agenten. Nur ein erfolgreicher Lauf setzt es — ein blosser
 * Wiederbelebungsversuch reicht als Beleg nicht (Spec §4).
 */
export function decideIncidentClosure(input: {
  assigneeAgentId: string | null;
  recoveryCreatedAt: Date;
  latestHealedAt: Date | null;
  hasActiveRun: boolean;
}): IncidentClosureAction {
  if (!input.assigneeAgentId) return { kind: "skip", reason: "no_assignee" };

  // Strikt groesser: bei Gleichstand ist die Reihenfolge von Heilung und
  // Stranden nicht entscheidbar, und im Zweifel bleibt die Arbeit geparkt.
  const healedAfterIncident =
    input.latestHealedAt !== null &&
    input.latestHealedAt.getTime() > input.recoveryCreatedAt.getTime();
  if (!healedAfterIncident) return { kind: "not_healed" };

  if (input.hasActiveRun) return { kind: "wait_active_run" };

  return { kind: "close" };
}
