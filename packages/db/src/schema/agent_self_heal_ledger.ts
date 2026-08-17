import { sql } from "drizzle-orm";
import { pgTable, uuid, text, integer, timestamp, index, uniqueIndex } from "drizzle-orm/pg-core";
import { agents } from "./agents.js";
import { companies } from "./companies.js";

/**
 * Versuchs-Ledger der Agenten-Selbstheilung.
 *
 * Eine offene Zeile pro (Agent, Fehler-Fingerprint) haelt fest, wie oft schon
 * wiederbelebt oder eskaliert wurde und ab wann der naechste Versuch erlaubt
 * ist. Ohne dieses Gate wuerde der 30-s-Tick einen Wiederbelebungssturm
 * erzeugen.
 */
export const agentSelfHealLedger = pgTable(
  "agent_self_heal_ledger",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    agentId: uuid("agent_id").notNull().references(() => agents.id),
    companyId: uuid("company_id").notNull().references(() => companies.id),
    errorClass: text("error_class").notNull(),
    errorFingerprint: text("error_fingerprint").notNull(),
    attemptCount: integer("attempt_count").notNull().default(0),
    lastAction: text("last_action"),
    nextEligibleAt: timestamp("next_eligible_at", { withTimezone: true }),
    resolvedAt: timestamp("resolved_at", { withTimezone: true }),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
    updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (table) => ({
    agentOpenIdx: index("agent_self_heal_ledger_agent_open_idx").on(table.agentId, table.resolvedAt),
    // Genau eine OFFENE Zeile je Agent und Stoerung; abgeschlossene Zeilen
    // bleiben als Historie liegen.
    openFingerprintIdx: uniqueIndex("agent_self_heal_ledger_open_fingerprint_idx")
      .on(table.agentId, table.errorFingerprint)
      .where(sql`resolved_at is null`),
  }),
);
