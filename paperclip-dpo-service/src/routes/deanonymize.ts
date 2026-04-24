import type { FastifyInstance } from "fastify";
import { z } from "zod";
import type { Dpo } from "paperclip-dpo";
import { MappingNotFoundError } from "paperclip-dpo";
import type { DebugTrail } from "../debug-trail.js";

const Body = z.object({
  mappingId: z.string().min(1),
  text: z.string(),
});

export interface DeanonymizeRouteOptions {
  dpo: Dpo;
  debugTrail?: DebugTrail;
}

export function registerDeanonymizeRoute(app: FastifyInstance, opts: DeanonymizeRouteOptions): void {
  app.post("/deanonymize", async (req, reply) => {
    const parsed = Body.safeParse(req.body);
    if (!parsed.success) {
      return reply.code(400).send({ error: "bad_request", details: parsed.error.flatten() });
    }
    const trail = opts.debugTrail;
    const traceId = trail?.newTraceId() ?? "";
    if (trail?.isEnabled) {
      trail.write({
        traceId,
        route: "deanonymize",
        stage: "request",
        mappingId: parsed.data.mappingId,
        text: parsed.data.text,
      });
    }
    try {
      const result = opts.dpo.deanonymize(parsed.data);
      if (trail?.isEnabled) {
        trail.write({
          traceId,
          route: "deanonymize",
          stage: "deanonymized",
          mappingId: parsed.data.mappingId,
          text: result.text,
        });
      }
      return { text: result.text };
    } catch (err) {
      if (err instanceof MappingNotFoundError) {
        if (trail?.isEnabled) {
          trail.write({
            traceId,
            route: "deanonymize",
            stage: "error",
            mappingId: parsed.data.mappingId,
            errorCode: "mapping_not_found",
          });
        }
        return reply.code(404).send({ error: "mapping_not_found" });
      }
      throw err;
    }
  });
}
