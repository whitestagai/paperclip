import { randomUUID } from "node:crypto";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import {
  activityLog,
  agentSelfHealLedger,
  agents,
  companies,
  createDb,
  issueRelations,
  issues,
} from "@paperclipai/db";
import { eq } from "drizzle-orm";
import {
  getEmbeddedPostgresTestSupport,
  startEmbeddedPostgresTestDatabase,
} from "./helpers/embedded-postgres.js";
import {
  createIncidentClosureDeps,
  reconcileHealedStrandedIssues,
} from "../services/recovery/incident-closure.ts";

const embeddedPostgresSupport = await getEmbeddedPostgresTestSupport();
const describeEmbeddedPostgres = embeddedPostgresSupport.supported ? describe : describe.skip;

if (!embeddedPostgresSupport.supported) {
  console.warn(
    `Skipping incident-closure integration tests: ${embeddedPostgresSupport.reason ?? "unsupported environment"}`,
  );
}

const INCIDENT_AT = new Date("2026-08-21T12:00:00.000Z");

describeEmbeddedPostgres("Vorfall-Abschluss end-to-end", () => {
  let db!: ReturnType<typeof createDb>;
  let tempDb: Awaited<ReturnType<typeof startEmbeddedPostgresTestDatabase>> | null = null;
  const wakeups: Array<{ agentId: string; issueId: unknown }> = [];

  beforeAll(async () => {
    tempDb = await startEmbeddedPostgresTestDatabase("paperclip-incident-e2e-");
    db = createDb(tempDb.connectionString);
  }, 20_000);

  afterEach(async () => {
    wakeups.length = 0;
    await db.delete(activityLog);
    await db.delete(issueRelations);
    await db.delete(agentSelfHealLedger);
    await db.delete(issues);
    await db.delete(agents);
    await db.delete(companies);
  });

  afterAll(async () => {
    await tempDb?.cleanup();
  });

  const deps = () =>
    createIncidentClosureDeps(db as never, {
      heartbeat: {
        wakeup: async (agentId: string, opts: Record<string, unknown>) => {
          wakeups.push({
            agentId,
            issueId: (opts.payload as Record<string, unknown> | undefined)?.issueId,
          });
          return undefined;
        },
      },
    });

  /**
   * Baut die echte Lage nach: ein gestrandetes Quell-Issue, ein Recovery-Issue,
   * das es blockiert, und wahlweise den Heilungsbeleg im Ledger.
   */
  async function seedIncident(opts: { healedAt: Date | null }) {
    const companyId = randomUUID();
    const agentId = randomUUID();
    const sourceId = randomUUID();
    const recoveryId = randomUUID();

    await db.insert(companies).values({
      id: companyId,
      name: "Paperclip",
      issuePrefix: `T${companyId.replace(/-/g, "").slice(0, 6).toUpperCase()}`,
      requireBoardApprovalForNewAgents: false,
    });
    await db.insert(agents).values({
      id: agentId,
      companyId,
      name: "CEO",
      role: "ceo",
      status: "idle",
      adapterType: "lmstudio_local",
      adapterConfig: {},
      runtimeConfig: {},
      permissions: {},
    });
    await db.insert(issues).values([
      {
        id: sourceId,
        companyId,
        title: "Geparkte Arbeit",
        status: "blocked",
        priority: "high",
        assigneeAgentId: agentId,
        createdByUserId: "user-1",
      },
      {
        id: recoveryId,
        companyId,
        title: "Recover stalled issue",
        status: "blocked",
        priority: "high",
        assigneeAgentId: agentId,
        createdByUserId: "user-1",
        originKind: "stranded_issue_recovery",
        originId: sourceId,
        createdAt: INCIDENT_AT,
      },
    ]);
    await db.insert(issueRelations).values({
      companyId,
      issueId: recoveryId,
      relatedIssueId: sourceId,
      type: "blocks",
    });
    if (opts.healedAt) {
      await db.insert(agentSelfHealLedger).values({
        id: randomUUID(),
        companyId,
        agentId,
        errorClass: "infra_transient",
        errorFingerprint: "code:llm_error",
        attemptCount: 3,
        resolvedAt: opts.healedAt,
        createdAt: INCIDENT_AT,
      });
    }
    return { companyId, agentId, sourceId, recoveryId };
  }

  it("gibt die geparkte Arbeit frei, legt das Recovery-Issue still und weckt den Ur-Agenten", async () => {
    const { agentId, sourceId, recoveryId } = await seedIncident({
      healedAt: new Date("2026-08-21T12:30:00.000Z"),
    });

    const result = await reconcileHealedStrandedIssues(deps());

    expect(result.closed).toBe(1);
    expect(result.blockersRemoved).toBe(1);

    const relations = await db
      .select()
      .from(issueRelations)
      .where(eq(issueRelations.relatedIssueId, sourceId));
    expect(relations).toHaveLength(0);

    const [recovery] = await db.select().from(issues).where(eq(issues.id, recoveryId));
    expect(recovery.status).toBe("cancelled");

    expect(wakeups).toEqual([{ agentId, issueId: sourceId }]);
  });

  it("laesst alles stehen, solange der Agent nicht nachweislich wieder lief", async () => {
    const { sourceId, recoveryId } = await seedIncident({ healedAt: null });

    const result = await reconcileHealedStrandedIssues(deps());

    expect(result.notHealed).toBe(1);
    expect(result.closed).toBe(0);

    const relations = await db
      .select()
      .from(issueRelations)
      .where(eq(issueRelations.relatedIssueId, sourceId));
    expect(relations).toHaveLength(1);

    const [recovery] = await db.select().from(issues).where(eq(issues.id, recoveryId));
    expect(recovery.status).toBe("blocked");
    expect(wakeups).toEqual([]);
  });

  it("schliesst NICHT, wenn die Heilung aelter ist als der Vorfall", async () => {
    const { recoveryId } = await seedIncident({
      healedAt: new Date("2026-08-21T11:00:00.000Z"),
    });

    const result = await reconcileHealedStrandedIssues(deps());

    expect(result.notHealed).toBe(1);
    const [recovery] = await db.select().from(issues).where(eq(issues.id, recoveryId));
    expect(recovery.status).toBe("blocked");
  });

  it("hinterlaesst eine Spur im activity_log", async () => {
    const { recoveryId } = await seedIncident({
      healedAt: new Date("2026-08-21T12:30:00.000Z"),
    });

    await reconcileHealedStrandedIssues(deps());

    const entries = await db
      .select()
      .from(activityLog)
      .where(eq(activityLog.entityId, recoveryId));
    expect(entries.map((row) => row.action)).toContain("recovery.incident_closed");
  });
});
