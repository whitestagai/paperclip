import { and, desc, eq, inArray, isNull } from "drizzle-orm";
import type { Db } from "@paperclipai/db";
import {
  agents,
  agentRuntimeState,
  agentSelfHealLedger,
  heartbeatRuns,
  activityLog,
} from "@paperclipai/db";
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
  /** Es liegt schon ein geplanter oder wartender Lauf vor (siehe Runner-Kommentar). */
  hasPendingRun: boolean;
}

/**
 * Waehlt aus, welcher Fehler die Klassifikation fuettert.
 *
 * Warum es diese Funktion braucht: die Zeile in `heartbeat_runs` mit dem
 * hoechsten `created_at` ist oft eine `scheduled_retry`- oder `queued`-Zeile
 * OHNE `error_code`/`error`. Wer die nimmt, klassifiziert `unknown` und schickt
 * genau die Agenten an den Menschen, die eine Wiederbelebung retten wuerde. Der
 * wahre Fehlertext steht dann in `agent_runtime_state.last_error` und wird hier
 * als Rueckfall gezogen. Leerstrings gelten dabei als „kein Text" — ein `??`
 * allein wuerde sie durchlassen und den Rueckfall blockieren.
 */
export function pickSelfHealErrorSource(input: {
  run: { errorCode: string | null; error: string | null } | null;
  runtimeLastError: string | null;
}): { lastErrorCode: string | null; lastErrorText: string | null } {
  const nonEmpty = (value: string | null | undefined) =>
    typeof value === "string" && value.trim().length > 0 ? value : null;

  return {
    lastErrorCode: nonEmpty(input.run?.errorCode),
    lastErrorText: nonEmpty(input.run?.error) ?? nonEmpty(input.runtimeLastError),
  };
}

/** Modell-Liste beider LM-Studio-Endpunkte; `null`, wenn die Antwort unbrauchbar ist. */
function toModelEntries(body: unknown): Array<Record<string, unknown>> | null {
  if (typeof body !== "object" || body === null) return null;
  const data = (body as { data?: unknown }).data;
  if (!Array.isArray(data)) return null;
  return data.filter(
    (entry): entry is Record<string, unknown> => typeof entry === "object" && entry !== null,
  );
}

/**
 * IDs der GELADENEN Modelle aus `/api/v0/models`.
 *
 * `null` heisst „diese Antwort taugt nicht als Ladezustands-Quelle" — kein
 * `data`-Array oder keine einzige Zeile mit `state`. Das trennt LM Studio von
 * fremden OpenAI-kompatiblen Servern und ist das Signal fuer den Rueckfall auf
 * `/v1/models`.
 */
export function extractLoadedModelIds(body: unknown): Set<string> | null {
  const entries = toModelEntries(body);
  if (!entries) return null;
  if (!entries.some((entry) => typeof entry.state === "string")) return null;
  return new Set(
    entries
      .filter((entry) => entry.state === "loaded" && typeof entry.id === "string")
      .map((entry) => entry.id as string),
  );
}

/** IDs aus `/v1/models` — reine Existenz, der Ladezustand fehlt dort. */
export function extractModelIds(body: unknown): Set<string> | null {
  const entries = toModelEntries(body);
  if (!entries) return null;
  return new Set(
    entries.filter((entry) => typeof entry.id === "string").map((entry) => entry.id as string),
  );
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

  // Eine Probe je Endpoint-Konfiguration statt je Agent: 38 Agenten teilen
  // dieselbe `url`. Haengt der Host (Timeout statt Connection-Refused), waeren
  // das 38 × 8 s = 304 s — mehr als das 120-s-Tick-Intervall, also garantierte
  // Ueberlappung. Der Cache lebt bewusst NUR fuer diesen Durchlauf: ein
  // Endpoint, das zwischen zwei Ticks gesund wird, muss neu geprueft werden.
  // `adapterType` steckt im Schluessel, weil ein Adapter ohne url/model sonst
  // mit einem fremden Adaptertyp kollidieren wuerde.
  const probeCache = new Map<string, Promise<boolean | null>>();
  const probe = (agent: SelfHealAgentRow): Promise<boolean | null> => {
    const part = (value: unknown) => (typeof value === "string" ? value : "");
    const key = [
      agent.adapterType,
      part(agent.adapterConfig.url),
      part(agent.adapterConfig.model),
      part(agent.adapterConfig.fallbackModel),
    ].join("|");
    const cached = probeCache.get(key);
    if (cached) return cached;
    const pending = deps.probeEndpoint(agent);
    probeCache.set(key, pending);
    return pending;
  };

  for (const agent of agents) {
    // Fuer diesen Agenten hat das System schon einen Plan: ein `scheduled_retry`
    // oder `queued` Lauf steht an. Parallel wiederbeleben und wecken wuerde
    // gegen diesen Plan arbeiten (zwei Laeufe, verdoppelte Kosten) — der
    // Waechter haelt sich raus, bis der geplante Weg gescheitert ist.
    if (agent.hasPendingRun) {
      result.skipped += 1;
      continue;
    }

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
          ? await probe(agent)
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
 * der Cooldown. Bei LM Studio wird der Ladezustand geprueft (`/api/v0/models`),
 * mit Rueckfall auf reine Existenz (`/v1/models`).
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
          // Nur echte Fehlausgaenge tragen `error_code`/`error`. Ohne diesen
          // Statusfilter greift der Waechter die neueste `scheduled_retry`- oder
          // `queued`-Zeile mit leeren Fehlerfeldern ab und klassifiziert alles
          // als `unknown` (live an zwei Agenten nachgewiesen).
          const [lastRun] = await db
            .select({ errorCode: heartbeatRuns.errorCode, error: heartbeatRuns.error })
            .from(heartbeatRuns)
            .where(
              and(
                eq(heartbeatRuns.agentId, row.id),
                inArray(heartbeatRuns.status, ["failed", "timed_out"]),
              ),
            )
            .orderBy(desc(heartbeatRuns.createdAt))
            .limit(1);

          const [pendingRun] = await db
            .select({ id: heartbeatRuns.id })
            .from(heartbeatRuns)
            .where(
              and(
                eq(heartbeatRuns.agentId, row.id),
                inArray(heartbeatRuns.status, ["scheduled_retry", "queued"]),
              ),
            )
            .limit(1);

          const [runtime] = await db
            .select({ lastError: agentRuntimeState.lastError })
            .from(agentRuntimeState)
            .where(eq(agentRuntimeState.agentId, row.id))
            .limit(1);

          return {
            ...row,
            adapterConfig: (row.adapterConfig ?? {}) as Record<string, unknown>,
            ...pickSelfHealErrorSource({
              run: lastRun ?? null,
              runtimeLastError: runtime?.lastError ?? null,
            }),
            hasPendingRun: !!pendingRun,
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
      const base = (
        typeof agent.adapterConfig.url === "string" ? agent.adapterConfig.url : "http://localhost:1234"
      ).replace(/\/+$/, "");
      const wanted = typeof agent.adapterConfig.model === "string" ? agent.adapterConfig.model : null;
      const fallback = typeof agent.adapterConfig.fallbackModel === "string" ? agent.adapterConfig.fallbackModel : null;

      const hit = (ids: Set<string>) => {
        if (!wanted && !fallback) return ids.size > 0;
        return (wanted !== null && ids.has(wanted)) || (fallback !== null && ids.has(fallback));
      };

      const fetchJson = async (path: string): Promise<unknown> => {
        try {
          const res = await fetch(`${base}${path}`, { signal: AbortSignal.timeout(8000) });
          if (!res.ok) return null;
          return await res.json();
        } catch {
          return null;
        }
      };

      // Erreichbar genuegt nicht — das konfigurierte Modell (oder der Fallback)
      // muss GELADEN sein. Nur LM Studios eigene API (`/api/v0/models`) fuehrt
      // dafuer `state`; `/v1/models` listet auch entladene Modelle (live
      // gemessen: 18 IDs, 9 davon nicht geladen). Ohne diese Unterscheidung
      // sieht der Waechter nach einer RAM-Verdraengung "gesund", belebt wieder,
      // der Lauf scheitert erneut — und nach drei Runden ist der Agent
      // endgueltig als Menschenfall abgestempelt, obwohl das Endpoint eine
      // halbe Stunde spaeter von selbst gesund gewesen waere.
      const loadedIds = extractLoadedModelIds(await fetchJson("/api/v0/models"));
      if (loadedIds) return hit(loadedIds);

      // Rueckfall fuer alles, was `/api/v0/models` nicht bedient (anderer
      // OpenAI-kompatibler Server, Fehlerantwort): dort ist NUR Existenz
      // pruefbar, „geladen" bleibt unbekannt. Bewusst schwaecher als oben.
      const ids = extractModelIds(await fetchJson("/v1/models"));
      return ids ? hit(ids) : false;
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
let running = false;

/**
 * Scheduler-Einstieg. Der 30-s-Tick ruft das oft; gescannt wird nur, wenn der
 * eigene Mindestabstand abgelaufen ist.
 *
 * `index.ts` ruft mit `void`, wartet also nicht ab. Laeuft ein Durchlauf laenger
 * als das Intervall, wuerde ein zweiter parallel starten — mit eigenem `result`,
 * womit `maxConcurrentRevives` faktisch pro Durchlauf statt global gilt. Das
 * `running`-Flag verhindert das; `lastTickAt` bleibt dabei unberuehrt, damit der
 * abgewiesene Tick nicht auch noch das Zeitfenster des laufenden verschiebt.
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
  if (running) return null;
  const now = deps.now().getTime();
  if (now - lastTickAt < options.minIntervalMs) return null;
  lastTickAt = now;
  running = true;
  try {
    return await runAgentSelfHeal(deps, options);
  } finally {
    running = false;
  }
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
