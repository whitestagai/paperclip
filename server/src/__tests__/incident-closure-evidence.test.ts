import { randomUUID } from "node:crypto";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { agentSelfHealLedger, agents, companies, createDb } from "@paperclipai/db";
import {
  getEmbeddedPostgresTestSupport,
  startEmbeddedPostgresTestDatabase,
} from "./helpers/embedded-postgres.js";
import { findAgentHealingEvidence } from "../services/recovery/incident-closure.ts";

const embeddedPostgresSupport = await getEmbeddedPostgresTestSupport();
const describeEmbeddedPostgres = embeddedPostgresSupport.supported ? describe : describe.skip;

if (!embeddedPostgresSupport.supported) {
  console.warn(
    `Skipping incident-closure evidence tests on this host: ${embeddedPostgresSupport.reason ?? "unsupported environment"}`,
  );
}

/**
 * `findAgentHealingEvidence` beantwortet genau eine Frage: lief dieser Agent
 * NACH dem Stranden nachweislich wieder durch? Belegt wird das allein durch ein
 * gesetztes `resolved_at` im Selbstheilungs-Ledger.
 */
const INCIDENT_AT = new Date("2026-08-21T12:00:00.000Z");

describeEmbeddedPostgres("findAgentHealingEvidence", () => {
  let db!: ReturnType<typeof createDb>;
  let tempDb: Awaited<ReturnType<typeof startEmbeddedPostgresTestDatabase>> | null = null;

  beforeAll(async () => {
    tempDb = await startEmbeddedPostgresTestDatabase("paperclip-incident-closure-");
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

  async function seedAgent(name = "CEO"): Promise<{ companyId: string; agentId: string }> {
    const companyId = randomUUID();
    const agentId = randomUUID();
    await db.insert(companies).values({
      id: companyId,
      name: "Paperclip",
      issuePrefix: `T${companyId.replace(/-/g, "").slice(0, 6).toUpperCase()}`,
      requireBoardApprovalForNewAgents: false,
    });
    await db.insert(agents).values({
      id: agentId,
      companyId,
      name,
      role: "ceo",
      status: "idle",
      adapterType: "lmstudio_local",
      adapterConfig: {},
      runtimeConfig: {},
      permissions: {},
    });
    return { companyId, agentId };
  }

  function ledgerRow(
    companyId: string,
    agentId: string,
    fingerprint: string,
    resolvedAt: Date | null,
  ) {
    return {
      id: randomUUID(),
      companyId,
      agentId,
      errorClass: "infra_transient",
      errorFingerprint: fingerprint,
      attemptCount: 1,
      resolvedAt,
      createdAt: INCIDENT_AT,
    };
  }

  it("liefert das juengste resolved_at nach dem Vorfall", async () => {
    const { companyId, agentId } = await seedAgent();
    await db.insert(agentSelfHealLedger).values([
      ledgerRow(companyId, agentId, "code:llm_error", new Date("2026-08-21T12:30:00.000Z")),
      ledgerRow(companyId, agentId, "code:timeout", new Date("2026-08-21T13:15:00.000Z")),
    ]);

    const found = await findAgentHealingEvidence(db as never, agentId, INCIDENT_AT);

    expect(found?.toISOString()).toBe("2026-08-21T13:15:00.000Z");
  });

  it("liefert null, wenn die Heilung aelter ist als der Vorfall", async () => {
    const { companyId, agentId } = await seedAgent();
    await db
      .insert(agentSelfHealLedger)
      .values([
        ledgerRow(companyId, agentId, "code:llm_error", new Date("2026-08-21T11:30:00.000Z")),
      ]);

    expect(await findAgentHealingEvidence(db as never, agentId, INCIDENT_AT)).toBeNull();
  });

  it("ignoriert offene Zeilen — eine laufende Stoerung ist kein Beleg", async () => {
    const { companyId, agentId } = await seedAgent();
    await db
      .insert(agentSelfHealLedger)
      .values([ledgerRow(companyId, agentId, "code:llm_error", null)]);

    expect(await findAgentHealingEvidence(db as never, agentId, INCIDENT_AT)).toBeNull();
  });

  it("zaehlt die Heilung eines ANDEREN Agenten nicht mit", async () => {
    const mine = await seedAgent("CEO");
    const other = await seedAgent("CTO");
    await db
      .insert(agentSelfHealLedger)
      .values([
        ledgerRow(
          other.companyId,
          other.agentId,
          "code:llm_error",
          new Date("2026-08-21T13:00:00.000Z"),
        ),
      ]);

    expect(await findAgentHealingEvidence(db as never, mine.agentId, INCIDENT_AT)).toBeNull();
  });
});
