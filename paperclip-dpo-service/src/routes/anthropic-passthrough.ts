import type { FastifyInstance, FastifyRequest, FastifyReply } from "fastify";
import { z } from "zod";
import { randomUUID } from "node:crypto";
import type { Dpo as PiiProxy } from "paperclip-dpo";
import { createAnthropicSseDeanonymizer } from "../streaming/anthropic-sse-deanonymizer.js";
import type { DebugTrail } from "../debug-trail.js";

const ANTHROPIC_UPSTREAM_DEFAULT = "https://api.anthropic.com/v1/messages";

const TextBlock = z.object({ type: z.literal("text"), text: z.string() }).passthrough();
const OtherBlock = z.object({ type: z.string() }).passthrough();
const ContentBlock = z.union([TextBlock, OtherBlock]);
const Content = z.union([z.string(), z.array(ContentBlock)]);

const Message = z
  .object({
    role: z.enum(["user", "assistant"]),
    content: Content,
  })
  .passthrough();

const RequestBody = z
  .object({
    model: z.string(),
    messages: z.array(Message),
    system: z.union([z.string(), z.array(ContentBlock)]).optional(),
    stream: z.boolean().optional(),
  })
  .passthrough();

export interface AnthropicPassthroughOptions {
  piiProxy: PiiProxy;
  fetchFn?: typeof fetch;
  upstreamUrl?: string;
  tenantId?: string;
  debugTrail?: DebugTrail;
}

type TextRef = { get: () => string; set: (value: string) => void };

function collectRequestTextRefs(body: z.infer<typeof RequestBody>): TextRef[] {
  const refs: TextRef[] = [];

  const pushContent = (owner: { content: unknown }) => {
    const c = owner.content;
    if (typeof c === "string") {
      refs.push({
        get: () => owner.content as string,
        set: (v) => {
          owner.content = v;
        },
      });
    } else if (Array.isArray(c)) {
      for (const block of c) {
        if (isTextBlock(block)) {
          const tb = block as { text: string };
          refs.push({ get: () => tb.text, set: (v) => { tb.text = v; } });
        }
      }
    }
  };

  if (body.system !== undefined) {
    if (typeof body.system === "string") {
      refs.push({
        get: () => body.system as string,
        set: (v) => {
          body.system = v;
        },
      });
    } else {
      for (const block of body.system) {
        if (isTextBlock(block)) {
          const tb = block as { text: string };
          refs.push({ get: () => tb.text, set: (v) => { tb.text = v; } });
        }
      }
    }
  }

  for (const m of body.messages) pushContent(m as { content: unknown });
  return refs;
}

function collectResponseTextRefs(resp: { content?: unknown }): TextRef[] {
  const refs: TextRef[] = [];
  const c = resp.content;
  if (Array.isArray(c)) {
    for (const block of c) {
      if (isTextBlock(block)) {
        const tb = block as { text: string };
        refs.push({ get: () => tb.text, set: (v) => { tb.text = v; } });
      }
    }
  }
  return refs;
}

function isTextBlock(block: unknown): boolean {
  return (
    !!block &&
    typeof block === "object" &&
    (block as { type?: unknown }).type === "text" &&
    typeof (block as { text?: unknown }).text === "string"
  );
}

function buildBoundary(): string {
  return ` ---PII-PROXY-BOUNDARY-${randomUUID()}--- `;
}

function ensureBoundaryAbsent(boundary: string, texts: string[]): string {
  let b = boundary;
  while (texts.some((t) => t.includes(b))) b = buildBoundary();
  return b;
}

// Hop-by-hop headers and proxy-internal headers that must not leak upstream.
// Content-length is stripped because the body is re-serialized after
// anonymization and fetch() recomputes it from the new payload.
const STRIP_HEADER_NAMES = new Set<string>([
  "host",
  "content-length",
  "connection",
  "keep-alive",
  "transfer-encoding",
  "upgrade",
  "te",
  "trailer",
  "proxy-authorization",
  "proxy-authenticate",
  "x-pii-proxy-key",
  // accept-encoding is stripped so we receive raw (uncompressed) SSE chunks
  // instead of gzip/br — the streaming pipeline decodes text, not bytes.
  "accept-encoding",
]);

/**
 * Forward all request headers to the upstream provider, except hop-by-hop
 * headers and proxy-internal secrets. Earlier versions used a narrow
 * whitelist, but that stripped Anthropic-specific metadata headers (user-agent,
 * x-stainless-*, x-api-key-auth-method, …) which the upstream uses to
 * classify the auth mode — leading to spurious 401s.
 */
function buildUpstreamHeaders(req: FastifyRequest): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [name, value] of Object.entries(req.headers)) {
    const lower = name.toLowerCase();
    if (STRIP_HEADER_NAMES.has(lower)) continue;
    if (value === undefined) continue;
    out[lower] = Array.isArray(value) ? value.join(", ") : String(value);
  }
  if (!out["content-type"]) out["content-type"] = "application/json";
  if (!out["anthropic-version"]) out["anthropic-version"] = "2023-06-01";
  return out;
}

function previewBody(raw: string, max = 500): string {
  if (raw.length <= max) return raw;
  return raw.slice(0, max) + `… [+${raw.length - max} bytes]`;
}

export function registerAnthropicPassthroughRoute(
  app: FastifyInstance,
  opts: AnthropicPassthroughOptions,
): void {
  const fetchFn = opts.fetchFn ?? fetch;
  const upstream = opts.upstreamUrl ?? ANTHROPIC_UPSTREAM_DEFAULT;
  const trail = opts.debugTrail;

  app.post(
    "/anthropic/v1/messages",
    { config: { noAuth: true } },
    async (req: FastifyRequest, reply: FastifyReply) => {
      const apiKey = typeof req.headers["x-api-key"] === "string" ? req.headers["x-api-key"] : "";
      const authHeader =
        typeof req.headers["authorization"] === "string" ? req.headers["authorization"] : "";
      if (!apiKey && !authHeader) {
        return reply.code(401).send({
          type: "error",
          error: { type: "authentication_error", message: "missing x-api-key or authorization" },
        });
      }

      const parsed = RequestBody.safeParse(req.body);
      if (!parsed.success) {
        return reply.code(400).send({
          type: "error",
          error: {
            type: "invalid_request_error",
            message: "bad_request",
            details: parsed.error.flatten(),
          },
        });
      }

      const body = parsed.data;
      const isStreaming = body.stream === true;
      const traceId = trail?.newTraceId() ?? "";
      const targetLlm = body.model;

      const refs = collectRequestTextRefs(body);
      const originals = refs.map((r) => r.get());
      const joinedOriginal = originals.join("\n---\n");

      const upstreamHeaders = buildUpstreamHeaders(req);
      const forwardedHeaderNames = Object.keys(upstreamHeaders).sort();

      if (trail?.isEnabled) {
        trail.write({
          traceId,
          route: "anthropic-passthrough",
          stage: "request",
          targetLlm,
          tenantId: opts.tenantId,
          externalUrl: upstream,
          text: joinedOriginal,
          forwardedHeaderNames,
          streaming: isStreaming,
        });
      }

      req.log?.debug?.(
        { forwardedHeaderNames, upstream, streaming: isStreaming, traceId },
        "[anthropic-passthrough] forwarding to upstream",
      );

      // No text to anonymize (image-only) — forward verbatim.
      if (refs.length === 0) {
        return forwardVerbatim(fetchFn, upstream, upstreamHeaders, body, reply, req, trail, traceId, targetLlm);
      }

      const boundary = ensureBoundaryAbsent(buildBoundary(), originals);
      const joined = originals.join(boundary);

      const anon = await opts.piiProxy.anonymize({
        text: joined,
        targetLlm,
        agent: "anthropic-passthrough",
        tenantId: opts.tenantId,
      });
      if ("blocked" in anon) {
        if (trail?.isEnabled) {
          trail.write({
            traceId,
            route: "anthropic-passthrough",
            stage: "blocked",
            targetLlm,
            tenantId: opts.tenantId,
            blockedReason: anon.reason,
          });
        }
        return reply.code(400).send({
          type: "error",
          error: {
            type: "invalid_request_error",
            message: `blocked_by_pii_proxy:${anon.reason}`,
          },
        });
      }

      const anonParts = anon.anonymizedText.split(boundary);
      if (anonParts.length !== refs.length) {
        if (trail?.isEnabled) {
          trail.write({
            traceId,
            route: "anthropic-passthrough",
            stage: "error",
            targetLlm,
            errorCode: "boundary_split_mismatch",
            errorMessage: `expected ${refs.length}, got ${anonParts.length}`,
          });
        }
        return reply.code(500).send({
          type: "error",
          error: {
            type: "api_error",
            message: `boundary-split mismatch (expected ${refs.length}, got ${anonParts.length})`,
          },
        });
      }
      for (let i = 0; i < refs.length; i++) refs[i].set(anonParts[i]);

      if (trail?.isEnabled) {
        trail.write({
          traceId,
          route: "anthropic-passthrough",
          stage: "anonymized",
          targetLlm,
          tenantId: opts.tenantId,
          mappingId: anon.mappingId,
          externalUrl: upstream,
          text: anon.anonymizedText,
        });
      }

      if (!isStreaming) {
        return forwardNonStreaming(
          fetchFn,
          upstream,
          upstreamHeaders,
          body,
          reply,
          opts.piiProxy,
          anon.mappingId,
          req,
          trail,
          traceId,
          targetLlm,
        );
      }

      const mappingTable = opts.piiProxy.getMappingTable(anon.mappingId);
      return forwardStreaming(
        fetchFn,
        upstream,
        upstreamHeaders,
        body,
        reply,
        mappingTable,
        req,
        trail,
        traceId,
        targetLlm,
      );
    },
  );
}

async function forwardVerbatim(
  fetchFn: typeof fetch,
  upstream: string,
  headers: Record<string, string>,
  body: unknown,
  reply: FastifyReply,
  req: FastifyRequest,
  trail: DebugTrail | undefined,
  traceId: string,
  targetLlm: string,
): Promise<FastifyReply> {
  const res = await fetchFn(upstream, { method: "POST", headers, body: JSON.stringify(body) });
  const text = await res.text();
  req.log?.debug?.(
    { upstreamStatus: res.status, bodyPreview: previewBody(text), traceId },
    "[anthropic-passthrough] upstream response (verbatim)",
  );
  if (trail?.isEnabled) {
    trail.write({
      traceId,
      route: "anthropic-passthrough",
      stage: res.ok ? "external_response_raw" : "error",
      targetLlm,
      httpStatus: res.status,
      text: previewBody(text),
      ...(res.ok ? {} : { errorCode: "upstream_non_2xx" }),
    });
  }
  reply.code(res.status);
  reply.header("content-type", res.headers.get("content-type") ?? "application/json");
  return reply.send(text);
}

async function forwardNonStreaming(
  fetchFn: typeof fetch,
  upstream: string,
  headers: Record<string, string>,
  body: unknown,
  reply: FastifyReply,
  piiProxy: PiiProxy,
  mappingId: string,
  req: FastifyRequest,
  trail: DebugTrail | undefined,
  traceId: string,
  targetLlm: string,
): Promise<FastifyReply> {
  let upstreamRes: Response;
  try {
    upstreamRes = await fetchFn(upstream, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    if (trail?.isEnabled) {
      trail.write({
        traceId,
        route: "anthropic-passthrough",
        stage: "error",
        targetLlm,
        errorCode: "upstream_unreachable",
        errorMessage: message,
      });
    }
    return reply.code(502).send({
      type: "error",
      error: { type: "api_error", message: `upstream_unreachable: ${message}` },
    });
  }

  const rawText = await upstreamRes.text();
  req.log?.debug?.(
    { upstreamStatus: upstreamRes.status, bodyPreview: previewBody(rawText), traceId },
    "[anthropic-passthrough] upstream response (non-streaming)",
  );

  if (!upstreamRes.ok) {
    if (trail?.isEnabled) {
      trail.write({
        traceId,
        route: "anthropic-passthrough",
        stage: "error",
        targetLlm,
        mappingId,
        httpStatus: upstreamRes.status,
        errorCode: "upstream_non_2xx",
        text: previewBody(rawText),
      });
    }
    reply.code(upstreamRes.status);
    reply.header("content-type", upstreamRes.headers.get("content-type") ?? "application/json");
    return reply.send(rawText);
  }

  if (trail?.isEnabled) {
    trail.write({
      traceId,
      route: "anthropic-passthrough",
      stage: "external_response_raw",
      targetLlm,
      mappingId,
      httpStatus: upstreamRes.status,
      text: rawText,
    });
  }

  let jsonResp: Record<string, unknown>;
  try {
    jsonResp = JSON.parse(rawText) as Record<string, unknown>;
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    if (trail?.isEnabled) {
      trail.write({
        traceId,
        route: "anthropic-passthrough",
        stage: "error",
        targetLlm,
        mappingId,
        errorCode: "upstream_invalid_json",
        errorMessage: message,
      });
    }
    return reply.code(502).send({
      type: "error",
      error: { type: "api_error", message: `upstream_invalid_json: ${message}` },
    });
  }

  const respRefs = collectResponseTextRefs(jsonResp);
  for (const ref of respRefs) {
    const deanon = piiProxy.deanonymize({ mappingId, text: ref.get() });
    ref.set(deanon.text);
  }

  if (trail?.isEnabled) {
    const deanonText = respRefs.map((r) => r.get()).join("\n---\n");
    trail.write({
      traceId,
      route: "anthropic-passthrough",
      stage: "deanonymized",
      targetLlm,
      mappingId,
      text: deanonText,
    });
  }

  reply.code(200);
  reply.header("content-type", "application/json");
  return reply.send(jsonResp);
}

async function forwardStreaming(
  fetchFn: typeof fetch,
  upstream: string,
  headers: Record<string, string>,
  body: unknown,
  reply: FastifyReply,
  mappingTable: Map<string, string>,
  req: FastifyRequest,
  trail: DebugTrail | undefined,
  traceId: string,
  targetLlm: string,
): Promise<FastifyReply> {
  let upstreamRes: Response;
  try {
    upstreamRes = await fetchFn(upstream, {
      method: "POST",
      headers: { ...headers, accept: "text/event-stream" },
      body: JSON.stringify(body),
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    if (trail?.isEnabled) {
      trail.write({
        traceId,
        route: "anthropic-passthrough",
        stage: "error",
        targetLlm,
        errorCode: "upstream_unreachable",
        errorMessage: message,
      });
    }
    return reply.code(502).send({
      type: "error",
      error: { type: "api_error", message: `upstream_unreachable: ${message}` },
    });
  }

  if (!upstreamRes.ok) {
    const text = await upstreamRes.text();
    req.log?.debug?.(
      { upstreamStatus: upstreamRes.status, bodyPreview: previewBody(text), traceId },
      "[anthropic-passthrough] upstream non-2xx on streaming",
    );
    if (trail?.isEnabled) {
      trail.write({
        traceId,
        route: "anthropic-passthrough",
        stage: "error",
        targetLlm,
        httpStatus: upstreamRes.status,
        errorCode: "upstream_non_2xx",
        text: previewBody(text),
        streaming: true,
      });
    }
    reply.code(upstreamRes.status);
    reply.header("content-type", upstreamRes.headers.get("content-type") ?? "application/json");
    return reply.send(text);
  }
  if (!upstreamRes.body) {
    if (trail?.isEnabled) {
      trail.write({
        traceId,
        route: "anthropic-passthrough",
        stage: "error",
        targetLlm,
        errorCode: "upstream_no_body",
        streaming: true,
      });
    }
    return reply.code(502).send({
      type: "error",
      error: { type: "api_error", message: "upstream response has no body" },
    });
  }

  reply.code(200);
  reply.raw.setHeader("content-type", "text/event-stream");
  reply.raw.setHeader("cache-control", "no-cache");
  reply.raw.setHeader("connection", "keep-alive");
  reply.raw.flushHeaders();

  const writeSse = (event: string, data: string): void => {
    reply.raw.write(`event: ${event}\ndata: ${data}\n\n`);
  };

  const pipeline = createAnthropicSseDeanonymizer({
    mappingTable,
    writeEvent: writeSse,
  });

  const reader = upstreamRes.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let rawChunkCount = 0;
  let rawFirstChunkPreview = "";

  try {
    // eslint-disable-next-line no-constant-condition
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      if (value) {
        const chunk = decoder.decode(value, { stream: true });
        if (rawChunkCount === 0) rawFirstChunkPreview = previewBody(chunk);
        rawChunkCount++;
        pipeline.write(chunk);
      }
    }
    pipeline.write(decoder.decode());
    pipeline.end();

    if (trail?.isEnabled) {
      trail.write({
        traceId,
        route: "anthropic-passthrough",
        stage: "external_response_raw",
        targetLlm,
        httpStatus: upstreamRes.status,
        text: rawFirstChunkPreview,
        streaming: true,
      });
      trail.write({
        traceId,
        route: "anthropic-passthrough",
        stage: "deanonymized",
        targetLlm,
        streaming: true,
        text: `[streamed ${rawChunkCount} raw chunks — deanonymization applied per content_block_delta]`,
      });
    }
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    if (trail?.isEnabled) {
      trail.write({
        traceId,
        route: "anthropic-passthrough",
        stage: "error",
        targetLlm,
        errorCode: "upstream_stream_error",
        errorMessage: message,
        streaming: true,
      });
    }
    try {
      writeSse(
        "error",
        JSON.stringify({
          type: "error",
          error: { type: "api_error", message: `upstream_stream_error: ${message}` },
        }),
      );
    } catch {
      /* best-effort */
    }
  } finally {
    reply.raw.end();
  }

  return reply;
}
