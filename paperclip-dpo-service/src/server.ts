import Fastify, { type FastifyInstance } from "fastify";
import type { Dpo } from "paperclip-dpo";
import { registerAuth } from "./auth.js";
import { registerHealthRoute } from "./routes/health.js";
import { registerAnonymizeRoute } from "./routes/anonymize.js";
import { registerDeanonymizeRoute } from "./routes/deanonymize.js";
import { registerSafeCallRoute } from "./routes/safe-call.js";
import { registerAnthropicPassthroughRoute } from "./routes/anthropic-passthrough.js";
import { DebugTrail } from "./debug-trail.js";

export interface BuildServerOptions {
  sharedKey: string;
  classifierUrl: string;
  dpo: Dpo;
  fetchFn?: typeof fetch;
  logger?: boolean;
  debugTrail?: DebugTrail;
}

export async function buildServer(opts: BuildServerOptions): Promise<FastifyInstance> {
  const app = Fastify({ logger: opts.logger ?? false });
  const trail = opts.debugTrail ?? new DebugTrail({ enabled: false });
  registerAuth(app, { sharedKey: opts.sharedKey });
  registerHealthRoute(app, { classifierUrl: opts.classifierUrl, fetchFn: opts.fetchFn });
  registerAnonymizeRoute(app, { dpo: opts.dpo, debugTrail: trail });
  registerDeanonymizeRoute(app, { dpo: opts.dpo, debugTrail: trail });
  registerSafeCallRoute(app, { dpo: opts.dpo, fetchFn: opts.fetchFn, debugTrail: trail });
  registerAnthropicPassthroughRoute(app, { piiProxy: opts.dpo, fetchFn: opts.fetchFn });
  await app.ready();
  return app;
}
