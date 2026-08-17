import { and, desc, eq, isNull } from "drizzle-orm";
import type { Db } from "@paperclipai/db";
import { agents, agentSelfHealLedger, heartbeatRuns, activityLog } from "@paperclipai/db";
import { agentService } from "../agents.js";
import { logger } from "../../middleware/logger.js";
import { classifySelfHealError } from "./agent-self-heal-classify.js";
import {
  buildErrorFingerprint,
  computeNextEligibleAt,
  decideSelfHeal,
  resolveEscalationTarget,
} from "./agent-self-heal-policy.js";

export interface SelfHealAgentRow {
  id: string;
  companyId: string;
  name: string;
  status: string;
  reportsTo: string | null;
  adapterType: string;
  adapterConfig: Record<string, unknown>;
  lastErrorCode: string | null;
  lastErrorText: string | null;
}

export interface SelfHealDeps {
  loadErroredAgents(): Promise<SelfHealAgentRow[]>;
  loadFleet(): Promise<Array<{ id: string; reportsTo: string | null; status: string }>>;
  loadLedger(
    agentId: string,
    fingerprint: string,
  ): Promise<{ attemptCount: number; nextEligibleAt: Date | null } | null>;
  saveLedger(input: {
    agentId: string;
    companyId: string;
    errorClass: string;
    fingerprint: string;
    attemptCount: number;
    lastAction: string;
    nextEligibleAt: Date | null;
  }): Promise<void>;
  probeEndpoint(agent: {
    adapterType: string;
    adapterConfig: Record<string, unknown>;
  }): Promise<boolean | null>;
  reviveAgent(agentId: string): Promise<void>;
  wakeAgent(agentId: string, reason: string): Promise<void>;
  escalateToManager(input: {
    agentId: string;
    managerAgentId: string;
    reason: string;
  }): Promise<void>;
  escalateToHuman(input: { agentId: string; reason: string }): Promise<void>;
  logAction(input: {
    companyId: string;
    agentId: string;
    action: string;
    detail: Record<string, unknown>;
  }): Promise<void>;
  now(): Date;
}

export interface SelfHealResult {
  scanned: number;
  revived: number;
  escalatedManager: number;
  escalatedHuman: number;
  waited: number;
  skipped: number;
  failed: number;
}

/**
 * Ein Durchlauf der Selbstheilung.
 *
 * Alle Seiteneffekte laufen ueber `deps`, damit jeder Zweig ohne Datenbank und
 * ohne Netz pruefbar ist. Ein Fehler an einem Agenten wird protokolliert und
 * uebersprungen — er darf die uebrigen nicht mitreissen.
 */
export async function runAgentSelfHeal(
  deps: SelfHealDeps,
  options: { maxInfraRevives: number; cooldownMs: number; maxConcurrentRevives: number },
): Promise<SelfHealResult> {
  const log = logger.child({ service: "agent-self-heal" });
  const agents = await deps.loadErroredAgents();
  const result: SelfHealResult = {
    scanned: agents.length,
    revived: 0,
    escalatedManager: 0,
    escalatedHuman: 0,
    waited: 0,
    skipped: 0,
    failed: 0,
  };
  if (agents.length === 0) return result;

  const now = deps.now();
  let fleet: Array<{ id: string; reportsTo: string | null; status: string }> | null = null;

  for (const agent of agents) {
    // errorClass/fingerprint sind reine, synchrone Funktionen (kein IO) —
    // ausserhalb des try berechnet, damit sie im catch-Zweig zur Verfuegung
    // stehen, falls ein spaeterer await (Ledger, Revive, ...) wirft.
    const errorInput = { errorCode: agent.lastErrorCode, errorText: agent.lastErrorText };
    const errorClass = classifySelfHealError(errorInput);
    const fingerprint = buildErrorFingerprint(errorInput);
    let attemptCount = 0;

    try {
      const ledger = await deps.loadLedger(agent.id, fingerprint);
      attemptCount = ledger?.attemptCount ?? 0;

      // Cooldown und Deckel muessen VOR dem Probe geprueft werden:
      // decideSelfHeal prueft den Cooldown ohnehin vor der Klassen-Verzweigung,
      // und ein erschoepfter Wiederbelebungs-Deckel verhindert "revive"
      // unabhaengig vom Probe-Ergebnis. Ohne diese Vorprüfung würde das
      // Endpoint bei jedem Tick fuer bereits gebremste oder gedeckelte
      // Agenten sinnlos angepingt — genau der Sturm, den die Probe eigentlich
      // verhindern soll (Zielszenario: Endpoint down, viele tote Agenten).
      const cooldownActive =
        agent.status === "error" &&
        !!ledger?.nextEligibleAt &&
        ledger.nextEligibleAt.getTime() > now.getTime();
      const capReached =
        errorClass === "infra_transient" && result.revived >= options.maxConcurrentRevives;

      // Das Endpoint nur pruefen, wenn die Entscheidung tatsaechlich davon
      // abhaengen kann: falscher Status, aktiver Cooldown, erschoepfter
      // Deckel oder eine nicht-infra_transient-Klasse liefern ihr Ergebnis
      // so oder so — dort waere der Netzaufruf reiner Leerlauf.
      const endpointHealthy =
        agent.status === "error" &&
        !cooldownActive &&
        !capReached &&
        errorClass === "infra_transient" &&
        attemptCount < options.maxInfraRevives
          ? await deps.probeEndpoint(agent)
          : null;

      const action = decideSelfHeal({
        errorClass,
        agentStatus: agent.status,
        endpointHealthy,
        attemptCount,
        nextEligibleAt: ledger?.nextEligibleAt ?? null,
        now,
        maxInfraRevives: options.maxInfraRevives,
      });

      if (action.kind === "revive" && capReached) {
        result.waited += 1;
        continue;
      }

      const persist = async (lastAction: string, bumpAttempt: boolean) => {
        await deps.saveLedger({
          agentId: agent.id,
          companyId: agent.companyId,
          errorClass,
          fingerprint,
          attemptCount: bumpAttempt ? attemptCount + 1 : attemptCount,
          lastAction,
          nextEligibleAt: computeNextEligibleAt(attemptCount, now, options.cooldownMs),
        });
        await deps.logAction({
          companyId: agent.companyId,
          agentId: agent.id,
          action: `agent.self_heal.${lastAction}`,
          detail: { errorClass, fingerprint, attemptCount, endpointHealthy, agentName: agent.name },
        });
      };

      switch (action.kind) {
        case "revive": {
          await deps.reviveAgent(agent.id);
          await deps.wakeAgent(agent.id, `self_heal:${errorClass}`);
          result.revived += 1;
          await persist("revived", true);
          break;
        }
        case "wait_endpoint_down":
        case "wait_cooldown": {
          result.waited += 1;
          break;
        }
        case "escalate_manager": {
          fleet ??= await deps.loadFleet();
          const target = resolveEscalationTarget({ agentId: agent.id, agents: fleet });
          if (target.kind === "agent") {
            await deps.escalateToManager({
              agentId: agent.id,
              managerAgentId: target.agentId,
              reason: errorClass,
            });
            result.escalatedManager += 1;
            await persist("escalated_manager", true);
          } else {
            await deps.escalateToHuman({ agentId: agent.id, reason: target.reason });
            result.escalatedHuman += 1;
            await persist("escalated_human", true);
          }
          break;
        }
        case "escalate_human": {
          await deps.escalateToHuman({ agentId: agent.id, reason: action.reason });
          result.escalatedHuman += 1;
          await persist("escalated_human", true);
          break;
        }
        case "skip": {
          result.skipped += 1;
          break;
        }
      }
    } catch (err) {
      log.error({ err, agentId: agent.id }, "self-heal fuer einen Agenten fehlgeschlagen");
      result.failed += 1;

      // Ohne diesen Zweig waere ein dauerhaft werfender reviveAgent unsichtbar
      // und ohne Bremse: kein Ledger-Eintrag heisst kein nextEligibleAt, also
      // wuerde der Agent bei jedem Tick sofort erneut versucht. Das Loggen und
      // Persistieren selbst wird gekapselt — scheitert schon das Protokoll,
      // darf das den Durchlauf der uebrigen Agenten nicht kippen.
      try {
        await deps.logAction({
          companyId: agent.companyId,
          agentId: agent.id,
          action: "agent.self_heal.failed",
          detail: {
            error: err instanceof Error ? err.message : String(err),
            errorClass,
            agentName: agent.name,
          },
        });
        await deps.saveLedger({
          agentId: agent.id,
          companyId: agent.companyId,
          errorClass,
          fingerprint,
          attemptCount: attemptCount + 1,
          lastAction: "failed",
          nextEligibleAt: computeNextEligibleAt(attemptCount, now, options.cooldownMs),
        });
      } catch (loggingErr) {
        log.error(
          { err: loggingErr, agentId: agent.id },
          "Protokollieren des Fehlschlags schlug ebenfalls fehl",
        );
      }
    }
  }

  return result;
}

/**
 * Verdrahtet den Runner mit der Datenbank und den Diensten.
 *
 * Abweichung vom Brief: die Fabrik nimmt bewusst NUR `db` und `heartbeat`
 * entgegen — `server/src/index.ts` hat keinen fertigen Agenten-Service im
 * Zugriff, deshalb erzeugt sich die Fabrik `agentService(db)` selbst. Fuer
 * die Wiederbelebung gilt: `resume()` setzt status=idle und raeumt
 * pauseReason auf, es wird NIE direkt per `UPDATE agents SET status` gepatcht.
 *
 * `probeEndpoint` liefert absichtlich `null` fuer alles, was kein LM Studio
 * ist: fuer claude_local gibt es kein Modell-Listing, dort schuetzt allein
 * der Cooldown.
 */
export function createSelfHealDeps(
  db: Db,
  svc: {
    heartbeat: { wakeup(agentId: string, opts: Record<string, unknown>): Promise<unknown> };
  },
): SelfHealDeps {
  const agentSvc = agentService(db);

  return {
    async loadErroredAgents() {
      const rows = await db
        .select({
          id: agents.id,
          companyId: agents.companyId,
          name: agents.name,
          status: agents.status,
          reportsTo: agents.reportsTo,
          adapterType: agents.adapterType,
          adapterConfig: agents.adapterConfig,
        })
        .from(agents)
        .where(eq(agents.status, "error"));

      return Promise.all(
        rows.map(async (row) => {
          const [lastRun] = await db
            .select({ errorCode: heartbeatRuns.errorCode, error: heartbeatRuns.error })
            .from(heartbeatRuns)
            .where(eq(heartbeatRuns.agentId, row.id))
            .orderBy(desc(heartbeatRuns.createdAt))
            .limit(1);
          return {
            ...row,
            adapterConfig: (row.adapterConfig ?? {}) as Record<string, unknown>,
            lastErrorCode: lastRun?.errorCode ?? null,
            lastErrorText: lastRun?.error ?? null,
          };
        }),
      );
    },

    async loadFleet() {
      return db
        .select({ id: agents.id, reportsTo: agents.reportsTo, status: agents.status })
        .from(agents);
    },

    async loadLedger(agentId, fingerprint) {
      const [row] = await db
        .select({
          attemptCount: agentSelfHealLedger.attemptCount,
          nextEligibleAt: agentSelfHealLedger.nextEligibleAt,
        })
        .from(agentSelfHealLedger)
        .where(
          and(
            eq(agentSelfHealLedger.agentId, agentId),
            eq(agentSelfHealLedger.errorFingerprint, fingerprint),
            isNull(agentSelfHealLedger.resolvedAt),
          ),
        )
        .limit(1);
      return row ?? null;
    },

    async saveLedger(input) {
      await db
        .insert(agentSelfHealLedger)
        .values({
          agentId: input.agentId,
          companyId: input.companyId,
          errorClass: input.errorClass,
          errorFingerprint: input.fingerprint,
          attemptCount: input.attemptCount,
          lastAction: input.lastAction,
          nextEligibleAt: input.nextEligibleAt,
        })
        .onConflictDoUpdate({
          target: [agentSelfHealLedger.agentId, agentSelfHealLedger.errorFingerprint],
          targetWhere: isNull(agentSelfHealLedger.resolvedAt),
          set: {
            attemptCount: input.attemptCount,
            lastAction: input.lastAction,
            nextEligibleAt: input.nextEligibleAt,
            updatedAt: new Date(),
          },
        });
    },

    async probeEndpoint(agent) {
      if (agent.adapterType !== "lmstudio_local") return null;
      const base = typeof agent.adapterConfig.url === "string" ? agent.adapterConfig.url : "http://localhost:1234";
      const wanted = typeof agent.adapterConfig.model === "string" ? agent.adapterConfig.model : null;
      const fallback = typeof agent.adapterConfig.fallbackModel === "string" ? agent.adapterConfig.fallbackModel : null;
      try {
        const res = await fetch(`${base.replace(/\/+$/, "")}/v1/models`, {
          signal: AbortSignal.timeout(8000),
        });
        if (!res.ok) return false;
        const body = (await res.json()) as { data?: Array<{ id?: string }> };
        const ids = new Set((body.data ?? []).map((m) => m.id).filter(Boolean) as string[]);
        // Erreichbar genuegt nicht — das konfigurierte Modell (oder der
        // Fallback) muss auch geladen sein, sonst scheitert der Run erneut.
        if (!wanted && !fallback) return ids.size > 0;
        return (wanted !== null && ids.has(wanted)) || (fallback !== null && ids.has(fallback));
      } catch {
        return false;
      }
    },

    async reviveAgent(agentId) {
      // resume() setzt status=idle und raeumt pauseReason auf — nie direkt patchen.
      await agentSvc.resume(agentId);
    },

    async wakeAgent(agentId, reason) {
      await svc.heartbeat.wakeup(agentId, {
        source: "automation",
        triggerDetail: "system",
        reason,
        requestedByActorType: "system",
        requestedByActorId: "agent-self-heal",
      });
    },

    async escalateToManager({ agentId, managerAgentId, reason }) {
      await svc.heartbeat.wakeup(managerAgentId, {
        source: "automation",
        triggerDetail: "system",
        reason: `self_heal_escalation:${reason}`,
        payload: { strandedAgentId: agentId, cause: reason },
        requestedByActorType: "system",
        requestedByActorId: "agent-self-heal",
      });
    },

    async escalateToHuman({ agentId, reason }) {
      // Bewusst nur protokollieren: die Mail-/Board-Strecke haengt an
      // send-walter-deliverable und ist eigene Arbeit. Der activity_log-Eintrag
      // ist die Spur, an der ein Mensch es findet.
      logger.child({ service: "agent-self-heal" }).warn(
        { agentId, reason },
        "self-heal braucht einen Menschen",
      );
    },

    async logAction({ companyId, agentId, action, detail }) {
      // Drizzle-Feldname ist `details`, nicht `metadata` — siehe
      // packages/db/src/schema/activity_log.ts.
      await db.insert(activityLog).values({
        companyId,
        actorType: "system",
        actorId: "agent-self-heal",
        action,
        entityType: "agent",
        entityId: agentId,
        details: detail,
      });
    },

    now: () => new Date(),
  };
}

let lastTickAt = 0;

/**
 * Scheduler-Einstieg. Der 30-s-Tick ruft das oft; gescannt wird nur, wenn der
 * eigene Mindestabstand abgelaufen ist.
 */
export async function tickAgentSelfHeal(
  deps: SelfHealDeps,
  options: {
    enabled: boolean;
    minIntervalMs: number;
    maxInfraRevives: number;
    cooldownMs: number;
    maxConcurrentRevives: number;
  },
): Promise<SelfHealResult | null> {
  if (!options.enabled) return null;
  const now = deps.now().getTime();
  if (now - lastTickAt < options.minIntervalMs) return null;
  lastTickAt = now;
  return runAgentSelfHeal(deps, options);
}

/**
 * Ein erfolgreicher (oder abgebrochener) Run beendet die Stoerung — die offene
 * Ledger-Zeile wird geschlossen, damit ein spaeterer Ausfall wieder bei
 * attempt_count 0 anfaengt. `cancelled` zaehlt mit, weil `finalizeAgentStatus`
 * es genauso wie `succeeded` als „nicht kaputt" behandelt.
 */
export function decideLedgerResolution(
  outcome: "succeeded" | "failed" | "cancelled" | "timed_out",
): boolean {
  return outcome === "succeeded" || outcome === "cancelled";
}

/** Schliesst alle offenen Ledger-Zeilen eines Agenten. Gibt die Anzahl zurueck. */
export async function resolveSelfHealLedgerForAgent(
  db: Db,
  agentId: string,
  now: Date,
): Promise<number> {
  const rows = await db
    .update(agentSelfHealLedger)
    .set({ resolvedAt: now, updatedAt: now })
    .where(and(eq(agentSelfHealLedger.agentId, agentId), isNull(agentSelfHealLedger.resolvedAt)))
    .returning({ id: agentSelfHealLedger.id });
  return rows.length;
}
