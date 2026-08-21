import { and, desc, eq, gt, isNotNull } from "drizzle-orm";
import type { Db } from "@paperclipai/db";
import { agentSelfHealLedger } from "@paperclipai/db";
import { decideIncidentClosure } from "./incident-closure-policy.js";

/**
 * Juengster Beleg dafuer, dass ein Agent nach `since` wieder durchgelaufen ist.
 * Quelle ist ausschliesslich `agent_self_heal_ledger.resolved_at` — das wird nur
 * von einem erfolgreichen (oder abgebrochenen) Lauf gesetzt, ein blosser
 * Wiederbelebungsversuch reicht als Beleg nicht (Spec §4).
 */
export async function findAgentHealingEvidence(
  db: Db,
  agentId: string,
  since: Date,
): Promise<Date | null> {
  const row = await db
    .select({ resolvedAt: agentSelfHealLedger.resolvedAt })
    .from(agentSelfHealLedger)
    .where(
      and(
        eq(agentSelfHealLedger.agentId, agentId),
        isNotNull(agentSelfHealLedger.resolvedAt),
        gt(agentSelfHealLedger.resolvedAt, since),
      ),
    )
    .orderBy(desc(agentSelfHealLedger.resolvedAt))
    .limit(1)
    .then((rows) => rows[0] ?? null);

  return row?.resolvedAt ?? null;
}

export interface StrandedRecoveryRow {
  id: string;
  companyId: string;
  originId: string | null;
  createdAt: Date;
}

export interface IncidentClosureDeps {
  loadOpenStrandedRecoveries(): Promise<StrandedRecoveryRow[]>;
  loadSourceIssue(
    companyId: string,
    issueId: string,
  ): Promise<{ id: string; assigneeAgentId: string | null } | null>;
  findHealingEvidence(agentId: string, since: Date): Promise<Date | null>;
  hasActiveRun(companyId: string, issueId: string): Promise<boolean>;
  removeBlocker(recovery: StrandedRecoveryRow): Promise<boolean>;
  cancelRecoveryIssue(recoveryId: string): Promise<void>;
  wakeAgent(agentId: string, issueId: string): Promise<void>;
  logAction(entry: {
    companyId: string;
    action: string;
    entityId: string;
    detail: Record<string, unknown>;
  }): Promise<void>;
}

export interface IncidentClosureResult {
  closed: number;
  waitedActiveRun: number;
  notHealed: number;
  skipped: number;
  failed: number;
  wakeFailed: number;
  blockersRemoved: number;
}

/**
 * Ein Durchlauf ueber die offenen `stranded_issue_recovery`-Issues: wo der
 * zustaendige Agent nach dem Stranden nachweislich wieder lief, wird der Blocker
 * entfernt, das Recovery-Issue stillgelegt und der Ur-Agent geweckt.
 *
 * Bewusst KEIN zweiter Entblock-Pfad: die Operationen sind dieselben, die der
 * Recovery-Dienst fuer erledigte Liveness-Vorfaelle schon benutzt (Spec §2).
 */
export async function reconcileHealedStrandedIssues(
  deps: IncidentClosureDeps,
): Promise<IncidentClosureResult> {
  const result: IncidentClosureResult = {
    closed: 0,
    waitedActiveRun: 0,
    notHealed: 0,
    skipped: 0,
    failed: 0,
    wakeFailed: 0,
    blockersRemoved: 0,
  };

  for (const recovery of await deps.loadOpenStrandedRecoveries()) {
    try {
      if (!recovery.originId) {
        result.skipped += 1;
        continue;
      }

      const source = await deps.loadSourceIssue(recovery.companyId, recovery.originId);
      if (!source) {
        result.skipped += 1;
        continue;
      }

      const assigneeAgentId = source.assigneeAgentId;
      // `findHealingEvidence` filtert bereits auf „nach dem Vorfall". Ist da
      // nichts, kann die teurere Lauf-Abfrage die Entscheidung nicht mehr
      // drehen — dann bleibt sie ungestellt.
      const latestHealedAt = assigneeAgentId
        ? await deps.findHealingEvidence(assigneeAgentId, recovery.createdAt)
        : null;
      const hasActiveRun = latestHealedAt
        ? await deps.hasActiveRun(recovery.companyId, recovery.id)
        : false;

      const action = decideIncidentClosure({
        assigneeAgentId,
        recoveryCreatedAt: recovery.createdAt,
        latestHealedAt,
        hasActiveRun,
      });

      switch (action.kind) {
        case "skip":
          result.skipped += 1;
          break;
        case "not_healed":
          result.notHealed += 1;
          break;
        case "wait_active_run":
          result.waitedActiveRun += 1;
          break;
        case "close": {
          // Reihenfolge ist Absicht: entblocken vor dem Stilllegen. Bricht der
          // zweite Schritt ab, ist das Issue frei und ein verwaistes
          // Recovery-Issue sichtbar — umgekehrt waere es unsichtbar tot.
          if (await deps.removeBlocker(recovery)) result.blockersRemoved += 1;
          await deps.cancelRecoveryIssue(recovery.id);
          result.closed += 1;

          // Wecken zuletzt, weil es der einzige Schritt mit Aussenwirkung ist.
          // Scheitert es, bleibt die Arbeit trotzdem frei und auffindbar.
          try {
            await deps.wakeAgent(assigneeAgentId as string, source.id);
          } catch (err) {
            result.wakeFailed += 1;
            await deps.logAction({
              companyId: recovery.companyId,
              action: "recovery.incident_closed.wake_failed",
              entityId: recovery.id,
              detail: {
                sourceIssueId: source.id,
                agentId: assigneeAgentId,
                error: err instanceof Error ? err.message : String(err),
              },
            });
          }

          await deps.logAction({
            companyId: recovery.companyId,
            action: "recovery.incident_closed",
            entityId: recovery.id,
            detail: {
              sourceIssueId: source.id,
              agentId: assigneeAgentId,
              healedAt: latestHealedAt?.toISOString() ?? null,
            },
          });
          break;
        }
      }
    } catch (err) {
      result.failed += 1;
      await deps.logAction({
        companyId: recovery.companyId,
        action: "recovery.incident_closed.failed",
        entityId: recovery.id,
        detail: { error: err instanceof Error ? err.message : String(err) },
      });
    }
  }

  return result;
}
