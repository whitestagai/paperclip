CREATE TABLE "agent_self_heal_ledger" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"agent_id" uuid NOT NULL,
	"company_id" uuid NOT NULL,
	"error_class" text NOT NULL,
	"error_fingerprint" text NOT NULL,
	"attempt_count" integer DEFAULT 0 NOT NULL,
	"last_action" text,
	"next_eligible_at" timestamp with time zone,
	"resolved_at" timestamp with time zone,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
ALTER TABLE "agent_self_heal_ledger" ADD CONSTRAINT "agent_self_heal_ledger_agent_id_agents_id_fk" FOREIGN KEY ("agent_id") REFERENCES "public"."agents"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "agent_self_heal_ledger" ADD CONSTRAINT "agent_self_heal_ledger_company_id_companies_id_fk" FOREIGN KEY ("company_id") REFERENCES "public"."companies"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "agent_self_heal_ledger_agent_open_idx" ON "agent_self_heal_ledger" USING btree ("agent_id","resolved_at");--> statement-breakpoint
CREATE UNIQUE INDEX "agent_self_heal_ledger_open_fingerprint_idx" ON "agent_self_heal_ledger" USING btree ("agent_id","error_fingerprint") WHERE resolved_at is null;