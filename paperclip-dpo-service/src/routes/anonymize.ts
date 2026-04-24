import type { FastifyInstance } from "fastify";
import { z } from "zod";
import type { Dpo } from "paperclip-dpo";
import type { DebugTrail } from "../debug-trail.js";

const Body = z.object({
  text: z.string().min(1),
  targetLlm: z.string().min(1),
  agent: z.string().min(1),
  tenantId: z.string().optional(),
});

export interface AnonymizeRouteOptions {
  dpo: Dpo;
  debugTrail?: DebugTrail;
}

export function registerAnonymizeRoute(app: FastifyInstance, opts: AnonymizeRouteOptions): void {
  app.post("/anonymize", async (req, reply) => {
    const parsed = Body.safeParse(req.body);
    if (!parsed.success) {
      return reply.code(400).send({ error: "bad_request", details: parsed.error.flatten() });
    }
    const trail = opts.debugTrail;
    const traceId = trail?.newTraceId() ?? "";
    if (trail?.isEnabled) {
      trail.write({
        traceId,
        route: "anonymize",
        stage: "request",
        agent: parsed.data.agent,
        targetLlm: parsed.data.targetLlm,
        tenantId: parsed.data.tenantId,
        text: parsed.data.text,
      });
    }
    const result = await opts.dpo.anonymize(parsed.data);
    if ("blocked" in result) {
      if (trail?.isEnabled) {
        trail.write({
          traceId,
          route: "anonymize",
          stage: "blocked",
          agent: parsed.data.agent,
          targetLlm: parsed.data.targetLlm,
          blockedReason: result.reason,
        });
      }
      return { blocked: true, reason: result.reason };
    }
    if (trail?.isEnabled) {
      trail.write({
        traceId,
        route: "anonymize",
        stage: "anonymized",
        agent: parsed.data.agent,
        targetLlm: parsed.data.targetLlm,
        mappingId: result.mappingId,
        text: result.anonymizedText,
      });
    }
    return {
      blocked: false,
      anonymizedText: result.anonymizedText,
      mappingId: result.mappingId,
    };
  });
}
