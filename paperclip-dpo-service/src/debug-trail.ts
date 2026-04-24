import { appendFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";
import { randomUUID } from "node:crypto";

export type DebugStage =
  | "request"
  | "anonymized"
  | "external_response_raw"
  | "deanonymized"
  | "blocked"
  | "error";

export interface DebugTrailInput {
  traceId: string;
  route: "anonymize" | "deanonymize" | "safe-call";
  stage: DebugStage;
  agent?: string;
  targetLlm?: string;
  tenantId?: string;
  mappingId?: string;
  text?: string;
  externalUrl?: string;
  blockedReason?: string;
  errorCode?: string;
  errorMessage?: string;
  httpStatus?: number;
  responsePath?: string;
}

export type DebugTrailEntry = DebugTrailInput & { ts: string };

export interface DebugTrailOptions {
  enabled: boolean;
  dir?: string;
}

export class DebugTrail {
  private enabled: boolean;
  private dir?: string;

  constructor(opts: DebugTrailOptions) {
    this.enabled = opts.enabled;
    this.dir = opts.dir;
    if (this.enabled && this.dir) {
      mkdirSync(this.dir, { recursive: true });
    }
  }

  get isEnabled(): boolean {
    return this.enabled;
  }

  newTraceId(): string {
    return randomUUID();
  }

  write(entry: DebugTrailInput): void {
    if (!this.enabled || !this.dir) return;
    const ts = new Date().toISOString();
    const full: DebugTrailEntry = { ...entry, ts };
    const day = ts.slice(0, 10);
    const file = join(this.dir, `dpo-debug-trail-${day}.jsonl`);
    appendFileSync(file, JSON.stringify(full) + "\n", "utf8");
  }
}
