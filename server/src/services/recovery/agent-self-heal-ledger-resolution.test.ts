import { randomUUID } from "node:crypto";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { and, eq, isNull } from "drizzle-orm";
import { agentSelfHealLedger, agents, companies, createDb } from "@paperclipai/db";
import {
  getEmbeddedPostgresTestSupport,
  startEmbeddedPostgresTestDatabase,
} from "../../__tests__/helpers/embedded-postgres.js";
import { applySelfHealLedgerResolutionForRunOutcome } from "./agent-self-heal.js";

const embeddedPostgresSupport = await getEmbeddedPostgresTestSupport();
const describeEmbeddedPostgres = embeddedPostgresSupport.supported ? describe : describe.skip;

if (!embeddedPostgresSupport.supported) {
  console.warn(
    `Skipping embedded Postgres self-heal ledger tests on this host: ${embeddedPostgresSupport.reason ?? "unsupported environment"}`,
  );
}

const NOW = new Date("2026-10-03T17:00:00.000Z");

describeEmbeddedPostgres("applySelfHealLedgerResolutionForRunOutcome", () => {
  let db!: ReturnType<typeof createDb>;
  let tempDb: Awaited<ReturnType<typeof startEmbeddedPostgresTestDatabase>> | null = null;

  beforeAll(async () => {
    tempDb = await startEmbeddedPostgresTestDatabase("self-heal-ledger-resolution-");
    db = createDb(tempDb.connectionString);
  }, 20_000);

  afterEach(async () => {
    await db.delete(agentSelfHealLedger);
    await db.delete(agents);
    await db.delete(companies);
  });

  afterAll(async () => {
    await tempDb?.cleanup();
  });

  async function seedAgent(name: string) {
    const companyId = randomUUID();
    const agentId = randomUUID();
    await db.insert(companies).values({
      id: companyId,
      name: `Company ${name}`,
      issuePrefix: `T${companyId.replace(/-/g, "").slice(0, 6).toUpperCase()}`,
      requireBoardApprovalForNewAgents: false,
    });
    await db.insert(agents).values({
      id: agentId,
      companyId,
      name,
      role: "engineer",
      status: "error",
      adapterType: "lmstudio_local",
      adapterConfig: {},
      runtimeConfig: {},
    });
    return { companyId, agentId };
  }

  async function seedOpenLedgerRow(
    ids: { companyId: string; agentId: string },
    fingerprint: string,
    attemptCount: number,
  ) {
    await db.insert(agentSelfHealLedger).values({
      agentId: ids.agentId,
      companyId: ids.companyId,
      errorClass: "convergence",
      errorFingerprint: fingerprint,
      attemptCount,
      lastAction: "escalated_human",
    });
  }

  async function openRowCount(agentId: string) {
    const rows = await db
      .select({ id: agentSelfHealLedger.id })
      .from(agentSelfHealLedger)
      .where(and(eq(agentSelfHealLedger.agentId, agentId), isNull(agentSelfHealLedger.resolvedAt)));
    return rows.length;
  }

  it("closes every open ledger row of the agent when the run succeeded", async () => {
    const ids = await seedAgent("Lektorat");
    await seedOpenLedgerRow(ids, "code:max_iterations", 57);
    await seedOpenLedgerRow(ids, "code:llm_error", 3);

    const resolved = await applySelfHealLedgerResolutionForRunOutcome(db, ids.agentId, "succeeded", NOW);

    expect(resolved).toBe(2);
    expect(await openRowCount(ids.agentId)).toBe(0);
  });

  it("stamps resolvedAt with the supplied timestamp", async () => {
    const ids = await seedAgent("Vault-Maintainer");
    await seedOpenLedgerRow(ids, "code:max_iterations", 77);

    await applySelfHealLedgerResolutionForRunOutcome(db, ids.agentId, "succeeded", NOW);

    const [row] = await db
      .select({ resolvedAt: agentSelfHealLedger.resolvedAt })
      .from(agentSelfHealLedger)
      .where(eq(agentSelfHealLedger.agentId, ids.agentId));
    expect(row?.resolvedAt?.toISOString()).toBe(NOW.toISOString());
  });

  it("keeps the row open when the run failed", async () => {
    const ids = await seedAgent("CHO");
    await seedOpenLedgerRow(ids, "code:max_iterations", 57);

    const resolved = await applySelfHealLedgerResolutionForRunOutcome(db, ids.agentId, "failed", NOW);

    expect(resolved).toBe(0);
    expect(await openRowCount(ids.agentId)).toBe(1);
  });

  it("keeps the row open when the run timed out", async () => {
    const ids = await seedAgent("CRO");
    await seedOpenLedgerRow(ids, "code:timeout", 16);

    const resolved = await applySelfHealLedgerResolutionForRunOutcome(db, ids.agentId, "timed_out", NOW);

    expect(resolved).toBe(0);
    expect(await openRowCount(ids.agentId)).toBe(1);
  });

  it("closes the row when the run was cancelled", async () => {
    const ids = await seedAgent("Recherche");
    await seedOpenLedgerRow(ids, "code:max_iterations", 14);

    const resolved = await applySelfHealLedgerResolutionForRunOutcome(db, ids.agentId, "cancelled", NOW);

    expect(resolved).toBe(1);
    expect(await openRowCount(ids.agentId)).toBe(0);
  });

  it("leaves other agents' open rows untouched", async () => {
    const mine = await seedAgent("Lektorat");
    const other = await seedAgent("Redaktion");
    await seedOpenLedgerRow(mine, "code:max_iterations", 57);
    await seedOpenLedgerRow(other, "code:max_iterations", 19);

    await applySelfHealLedgerResolutionForRunOutcome(db, mine.agentId, "succeeded", NOW);

    expect(await openRowCount(mine.agentId)).toBe(0);
    expect(await openRowCount(other.agentId)).toBe(1);
  });

  it("is idempotent — a second successful run resolves nothing further", async () => {
    const ids = await seedAgent("Sekretaerin");
    await seedOpenLedgerRow(ids, "code:max_iterations", 6);

    await applySelfHealLedgerResolutionForRunOutcome(db, ids.agentId, "succeeded", NOW);
    const again = await applySelfHealLedgerResolutionForRunOutcome(db, ids.agentId, "succeeded", NOW);

    expect(again).toBe(0);
  });
});
