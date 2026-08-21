import { and, desc, eq, gt, inArray, isNotNull, isNull, notInArray } from "drizzle-orm";
import type { Db } from "@paperclipai/db";
import {
  activityLog,
  agentSelfHealLedger,
  heartbeatRuns,
  issueRelations,
  issues,
} from "@paperclipai/db";
import { issueService } from "../issues.js";
import { decideIncidentClosure } from "./incident-closure-policy.js";
import { RECOVERY_ORIGIN_KINDS } from "./origins.js";

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
  /** Diesen Tick nicht mehr angefasst, weil der Deckel erreicht war. */
  deferredOverBudget: number;
}

export interface IncidentClosureOptions {
  /**
   * Hoechstzahl Abschluesse je Durchlauf. Ohne Deckel gibt der erste Lauf auf
   * gewachsenen Daten hunderte Issues gleichzeitig frei und weckt ebenso viele
   * Agenten — dieselbe Sturmform, gegen die die Selbstheilung
   * `maxConcurrentRevives` hat. Der Rest kommt beim naechsten Tick dran.
   */
  maxClosuresPerTick?: number;
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
  options: IncidentClosureOptions = {},
): Promise<IncidentClosureResult> {
  const result: IncidentClosureResult = {
    closed: 0,
    waitedActiveRun: 0,
    notHealed: 0,
    skipped: 0,
    failed: 0,
    wakeFailed: 0,
    blockersRemoved: 0,
    deferredOverBudget: 0,
  };
  const budget = options.maxClosuresPerTick ?? Number.POSITIVE_INFINITY;

  for (const recovery of await deps.loadOpenStrandedRecoveries()) {
    // Deckel erreicht: den Rest bewusst gar nicht erst anfassen — weder Abfrage
    // noch Zaehlung als „geprueft", damit der naechste Tick unvoreingenommen
    // beginnt.
    if (result.closed >= budget) {
      result.deferredOverBudget += 1;
      continue;
    }
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

/** Laeufe, die als „auf diesem Issue wird gerade gearbeitet" zaehlen. */
const ACTIVE_RUN_STATUSES = ["queued", "running", "scheduled_retry"] as const;

/**
 * Verdrahtet den Durchlauf gegen die echte Datenbank. Bewusst als eigene Fabrik
 * wie `createSelfHealDeps` — der Durchlauf selbst bleibt damit ohne DB pruefbar.
 */
export function createIncidentClosureDeps(
  db: Db,
  svc: {
    heartbeat: { wakeup(agentId: string, opts: Record<string, unknown>): Promise<unknown> };
  },
): IncidentClosureDeps {
  const issuesSvc = issueService(db);

  return {
    async loadOpenStrandedRecoveries() {
      return db
        .select({
          id: issues.id,
          companyId: issues.companyId,
          originId: issues.originId,
          createdAt: issues.createdAt,
        })
        .from(issues)
        .where(
          and(
            eq(issues.originKind, RECOVERY_ORIGIN_KINDS.strandedIssueRecovery),
            isNull(issues.hiddenAt),
            notInArray(issues.status, ["done", "cancelled"]),
          ),
        );
    },

    async loadSourceIssue(companyId, issueId) {
      return db
        .select({ id: issues.id, assigneeAgentId: issues.assigneeAgentId })
        .from(issues)
        .where(and(eq(issues.companyId, companyId), eq(issues.id, issueId)))
        .limit(1)
        .then((rows) => rows[0] ?? null);
    },

    findHealingEvidence(agentId, since) {
      return findAgentHealingEvidence(db, agentId, since);
    },

    async hasActiveRun(companyId, issueId) {
      const row = await db
        .select({ id: heartbeatRuns.id })
        .from(issues)
        .innerJoin(heartbeatRuns, eq(issues.executionRunId, heartbeatRuns.id))
        .where(
          and(
            eq(issues.companyId, companyId),
            eq(issues.id, issueId),
            inArray(heartbeatRuns.status, [...ACTIVE_RUN_STATUSES]),
          ),
        )
        .limit(1)
        .then((rows) => rows[0] ?? null);
      return Boolean(row);
    },

    async removeBlocker(recovery) {
      if (!recovery.originId) return false;
      // Anders als bei Liveness-Vorfaellen ist `originId` hier direkt die
      // Quell-Issue-ID — es gibt keinen zusammengesetzten Schluessel zu parsen.
      const blockerIds = await db
        .select({ blockerIssueId: issueRelations.issueId })
        .from(issueRelations)
        .where(
          and(
            eq(issueRelations.companyId, recovery.companyId),
            eq(issueRelations.relatedIssueId, recovery.originId),
            eq(issueRelations.type, "blocks"),
          ),
        )
        .then((rows) => rows.map((row) => row.blockerIssueId));

      if (!blockerIds.includes(recovery.id)) return false;
      await issuesSvc.update(recovery.originId, {
        blockedByIssueIds: blockerIds.filter((blockerId) => blockerId !== recovery.id),
      });
      return true;
    },

    async cancelRecoveryIssue(recoveryId) {
      await issuesSvc.update(recoveryId, { status: "cancelled" });
    },

    async wakeAgent(agentId, issueId) {
      await svc.heartbeat.wakeup(agentId, {
        source: "automation",
        triggerDetail: "system",
        reason: "incident_closed_work_returned",
        payload: { issueId },
        requestedByActorType: "system",
        requestedByActorId: "incident-closure",
      });
    },

    async logAction(entry) {
      await db.insert(activityLog).values({
        companyId: entry.companyId,
        actorType: "system",
        actorId: "incident-closure",
        action: entry.action,
        entityType: "issue",
        entityId: entry.entityId,
        details: entry.detail,
      });
    },
  };
}
