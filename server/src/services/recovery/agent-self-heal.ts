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
