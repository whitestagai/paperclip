import { randomUUID } from "node:crypto";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import {
  agentRuntimeState,
  agents,
  companies,
  createDb,
  heartbeatRuns,
} from "@paperclipai/db";
import {
  getEmbeddedPostgresTestSupport,
  startEmbeddedPostgresTestDatabase,
} from "./helpers/embedded-postgres.js";
import { createSelfHealDeps } from "../services/recovery/agent-self-heal.ts";

const embeddedPostgresSupport = await getEmbeddedPostgresTestSupport();
const describeEmbeddedPostgres = embeddedPostgresSupport.supported ? describe : describe.skip;

if (!embeddedPostgresSupport.supported) {
  console.warn(
    `Skipping self-heal deps tests on this host: ${embeddedPostgresSupport.reason ?? "unsupported environment"}`,
  );
}

/**
 * Diese Tests decken den Teil der Deps-Fabrik ab, der sich nur gegen eine echte
 * Datenbank pruefen laesst: welche `heartbeat_runs`-Zeile der Waechter als
 * Fehlerquelle nimmt. Der Live-Befund C1 (neuester Lauf ist `scheduled_retry`
 * mit leeren Fehlerfeldern) ist hier als Fixture nachgebaut.
 */
const LIVE_RUNTIME_ERROR =
  "Claude run failed: subtype=success: API Error: Server is temporarily limiting requests";

describeEmbeddedPostgres("createSelfHealDeps.loadErroredAgents", () => {
  let db!: ReturnType<typeof createDb>;
  let tempDb: Awaited<ReturnType<typeof startEmbeddedPostgresTestDatabase>> | null = null;

  beforeAll(async () => {
    tempDb = await startEmbeddedPostgresTestDatabase("paperclip-self-heal-deps-");
    db = createDb(tempDb.connectionString);
  }, 20_000);

  afterEach(async () => {
    await db.delete(agentRuntimeState);
    await db.delete(heartbeatRuns);
    await db.delete(agents);
    await db.delete(companies);
  });

  afterAll(async () => {
    await tempDb?.cleanup();
  });

  const deps = () =>
    createSelfHealDeps(db as never, {
      heartbeat: { wakeup: async () => undefined },
    });

  async function seedErroredAgent(): Promise<{ companyId: string; agentId: string }> {
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
      name: "VP Engineering",
      role: "engineer",
      status: "error",
      adapterType: "claude_local",
      adapterConfig: {},
      runtimeConfig: {},
      permissions: {},
    });
    return { companyId, agentId };
  }

  it("nimmt den letzten ECHTEN Fehllauf, nicht die neuere scheduled_retry-Zeile", async () => {
    const { companyId, agentId } = await seedErroredAgent();

    await db.insert(heartbeatRuns).values([
      {
        id: randomUUID(),
        companyId,
        agentId,
        status: "failed",
        errorCode: "llm_unreachable",
        error: "fetch failed",
        createdAt: new Date("2026-08-17T10:00:00.000Z"),
      },
      {
        // Neuer, aber ohne Fehlerfelder — die Falle aus Befund C1.
        id: randomUUID(),
        companyId,
        agentId,
        status: "scheduled_retry",
        createdAt: new Date("2026-08-17T11:00:00.000Z"),
        scheduledRetryAt: new Date("2026-08-17T13:00:00.000Z"),
      },
    ]);

    const [row] = await deps().loadErroredAgents();

    expect(row.lastErrorCode).toBe("llm_unreachable");
    expect(row.lastErrorText).toBe("fetch failed");
  });

  it("zieht agent_runtime_state.last_error, wenn der Fehllauf keinen Text hat", async () => {
    const { companyId, agentId } = await seedErroredAgent();

    await db.insert(heartbeatRuns).values({
      id: randomUUID(),
      companyId,
      agentId,
      status: "failed",
      createdAt: new Date("2026-08-17T10:00:00.000Z"),
    });
    await db.insert(agentRuntimeState).values({
      agentId,
      companyId,
      adapterType: "claude_local",
      lastRunStatus: "failed",
      lastError: LIVE_RUNTIME_ERROR,
    });

    const [row] = await deps().loadErroredAgents();

    expect(row.lastErrorCode).toBeNull();
    expect(row.lastErrorText).toBe(LIVE_RUNTIME_ERROR);
  });

  it("markiert einen anstehenden scheduled_retry-Lauf als hasPendingRun", async () => {
    const { companyId, agentId } = await seedErroredAgent();

    await db.insert(heartbeatRuns).values({
      id: randomUUID(),
      companyId,
      agentId,
      status: "scheduled_retry",
      createdAt: new Date("2026-08-17T11:00:00.000Z"),
      scheduledRetryAt: new Date("2026-08-17T13:00:00.000Z"),
    });

    const [row] = await deps().loadErroredAgents();

    expect(row.hasPendingRun).toBe(true);
  });

  it("ohne anstehenden Lauf ist hasPendingRun falsch", async () => {
    const { companyId, agentId } = await seedErroredAgent();

    await db.insert(heartbeatRuns).values({
      id: randomUUID(),
      companyId,
      agentId,
      status: "timed_out",
      error: "run exceeded wall clock",
      createdAt: new Date("2026-08-17T11:00:00.000Z"),
    });

    const [row] = await deps().loadErroredAgents();

    expect(row.hasPendingRun).toBe(false);
    expect(row.lastErrorText).toBe("run exceeded wall clock");
  });

  it("beruehrt nur Agenten in status=error", async () => {
    const { agentId } = await seedErroredAgent();
    await db.update(agents).set({ status: "idle" });

    await expect(deps().loadErroredAgents()).resolves.toEqual([]);
    expect(agentId).toBeTruthy();
  });
});
