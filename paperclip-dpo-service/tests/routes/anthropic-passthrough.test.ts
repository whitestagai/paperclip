import { describe, it, expect, afterEach, beforeEach, vi } from "vitest";
import Fastify, { type FastifyInstance } from "fastify";
import { mkdtempSync, readFileSync, existsSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { registerAuth } from "../../src/auth.js";
import { registerAnthropicPassthroughRoute } from "../../src/routes/anthropic-passthrough.js";
import { DebugTrail } from "../../src/debug-trail.js";
import type { Dpo } from "paperclip-dpo";

const KEY = "test-key-32-bytes-xxxxxxxxxxxxxxx";

function mkDpo(overrides: Partial<Dpo> = {}): Dpo {
  return {
    anonymize: vi.fn().mockImplementation(async (req: { text: string }) => ({
      mappingId: "m-1",
      anonymizedText: req.text
        .replace(/Max Mustermann/g, "[PERSON_A]")
        .replace(/max@example\.com/g, "[EMAIL_A]"),
      findings: [],
      warnings: [],
    })),
    deanonymize: vi.fn().mockImplementation((req: { text: string }) => ({
      text: req.text
        .replace(/\[PERSON_A\]/g, "Max Mustermann")
        .replace(/\[EMAIL_A\]/g, "max@example.com"),
    })),
    getMappingTable: vi.fn().mockReturnValue(
      new Map<string, string>([
        ["[PERSON_A]", "Max Mustermann"],
        ["[EMAIL_A]", "max@example.com"],
      ]),
    ),
    close: vi.fn(),
    ...overrides,
  } as unknown as Dpo;
}

describe("POST /anthropic/v1/messages (passthrough)", () => {
  let app: FastifyInstance;
  afterEach(async () => app && (await app.close()));

  it("anonymizes string-content messages + system, calls upstream, deanonymizes response", async () => {
    const piiProxy = mkDpo();
    const fetchFn = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          id: "msg_1",
          type: "message",
          role: "assistant",
          content: [{ type: "text", text: "Ich schreibe [PERSON_A] eine Mail an [EMAIL_A]." }],
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );

    app = Fastify();
    registerAuth(app, { sharedKey: KEY });
    registerAnthropicPassthroughRoute(app, { piiProxy, fetchFn });
    await app.ready();

    const res = await app.inject({
      method: "POST",
      url: "/anthropic/v1/messages",
      headers: { "x-api-key": "sk-ant-xxx", "content-type": "application/json" },
      payload: {
        model: "claude-sonnet-4-6",
        max_tokens: 200,
        system: "Du bist der Buchhalter für Max Mustermann.",
        messages: [{ role: "user", content: "Schreibe an max@example.com." }],
      },
    });

    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.content[0].text).toBe("Ich schreibe Max Mustermann eine Mail an max@example.com.");

    expect(fetchFn).toHaveBeenCalledTimes(1);
    const [url, init] = fetchFn.mock.calls[0]!;
    expect(url).toBe("https://api.anthropic.com/v1/messages");
    const sent = JSON.parse(init.body as string);
    expect(sent.system).toBe("Du bist der Buchhalter für [PERSON_A].");
    expect(sent.messages[0].content).toBe("Schreibe an [EMAIL_A].");
    expect(init.headers["x-api-key"]).toBe("sk-ant-xxx");
  });

  it("anonymizes content-block array variant (text blocks only)", async () => {
    const piiProxy = mkDpo();
    const fetchFn = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({ content: [{ type: "text", text: "ok [PERSON_A]" }] }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );

    app = Fastify();
    registerAuth(app, { sharedKey: KEY });
    registerAnthropicPassthroughRoute(app, { piiProxy, fetchFn });
    await app.ready();

    const res = await app.inject({
      method: "POST",
      url: "/anthropic/v1/messages",
      headers: { "x-api-key": "sk-ant", "content-type": "application/json" },
      payload: {
        model: "claude-sonnet-4-6",
        messages: [
          {
            role: "user",
            content: [
              { type: "text", text: "Hi Max Mustermann" },
              { type: "image", source: { type: "base64", data: "abc" } },
            ],
          },
        ],
      },
    });

    expect(res.statusCode).toBe(200);
    const sent = JSON.parse(fetchFn.mock.calls[0]![1].body as string);
    expect(sent.messages[0].content[0].text).toBe("Hi [PERSON_A]");
    expect(sent.messages[0].content[1]).toEqual({ type: "image", source: { type: "base64", data: "abc" } });
    expect(res.json().content[0].text).toBe("ok Max Mustermann");
  });

  it("returns 401 when x-api-key and authorization missing", async () => {
    const piiProxy = mkDpo();
    const fetchFn = vi.fn();
    app = Fastify();
    registerAuth(app, { sharedKey: KEY });
    registerAnthropicPassthroughRoute(app, { piiProxy, fetchFn });
    await app.ready();

    const res = await app.inject({
      method: "POST",
      url: "/anthropic/v1/messages",
      headers: { "content-type": "application/json" },
      payload: { model: "claude", messages: [{ role: "user", content: "hi" }] },
    });
    expect(res.statusCode).toBe(401);
    expect(fetchFn).not.toHaveBeenCalled();
  });

  it("propagates pii-proxy.anonymize block without calling upstream", async () => {
    const piiProxy = mkDpo({
      anonymize: vi.fn().mockResolvedValue({ blocked: true, reason: "art_9_data_detected" }),
    } as Partial<Dpo>);
    const fetchFn = vi.fn();
    app = Fastify();
    registerAuth(app, { sharedKey: KEY });
    registerAnthropicPassthroughRoute(app, { piiProxy, fetchFn });
    await app.ready();

    const res = await app.inject({
      method: "POST",
      url: "/anthropic/v1/messages",
      headers: { "x-api-key": "sk-ant", "content-type": "application/json" },
      payload: { model: "claude", messages: [{ role: "user", content: "Blutgruppe A+" }] },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json().error.message).toMatch(/blocked_by_pii_proxy/);
    expect(fetchFn).not.toHaveBeenCalled();
  });

  it("passes through upstream non-2xx status and body verbatim", async () => {
    const piiProxy = mkDpo();
    const fetchFn = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({ type: "error", error: { type: "rate_limit_error", message: "slow down" } }),
        { status: 429, headers: { "content-type": "application/json" } },
      ),
    );
    app = Fastify();
    registerAuth(app, { sharedKey: KEY });
    registerAnthropicPassthroughRoute(app, { piiProxy, fetchFn });
    await app.ready();

    const res = await app.inject({
      method: "POST",
      url: "/anthropic/v1/messages",
      headers: { "x-api-key": "sk-ant", "content-type": "application/json" },
      payload: { model: "claude", messages: [{ role: "user", content: "Max Mustermann hi" }] },
    });
    expect(res.statusCode).toBe(429);
    expect(res.json().error.type).toBe("rate_limit_error");
  });

  it("keeps pseudonyms consistent across multiple text fields (single anonymize call)", async () => {
    const anonCalls: string[] = [];
    const piiProxy = mkDpo({
      anonymize: vi.fn().mockImplementation(async (req: { text: string }) => {
        anonCalls.push(req.text);
        return {
          mappingId: "m-1",
          anonymizedText: req.text.replace(/Max Mustermann/g, "[PERSON_A]"),
          findings: [],
          warnings: [],
        };
      }),
    } as Partial<Dpo>);
    const fetchFn = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({ content: [{ type: "text", text: "ok" }] }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );
    app = Fastify();
    registerAuth(app, { sharedKey: KEY });
    registerAnthropicPassthroughRoute(app, { piiProxy, fetchFn });
    await app.ready();

    await app.inject({
      method: "POST",
      url: "/anthropic/v1/messages",
      headers: { "x-api-key": "sk-ant", "content-type": "application/json" },
      payload: {
        model: "claude",
        system: "Assistent für Max Mustermann.",
        messages: [
          { role: "user", content: "Max Mustermann hat gefragt..." },
          { role: "assistant", content: "Verstanden, ich melde mich bei Max Mustermann." },
        ],
      },
    });

    expect(anonCalls).toHaveLength(1);
    const sent = JSON.parse(fetchFn.mock.calls[0]![1].body as string);
    expect(sent.system).toBe("Assistent für [PERSON_A].");
    expect(sent.messages[0].content).toBe("[PERSON_A] hat gefragt...");
    expect(sent.messages[1].content).toBe("Verstanden, ich melde mich bei [PERSON_A].");
  });

  describe("header forwarding", () => {
    it("forwards custom headers (user-agent, x-stainless-*) to upstream", async () => {
      const piiProxy = mkDpo();
      const fetchFn = vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ content: [{ type: "text", text: "ok" }] }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      );
      app = Fastify();
      registerAuth(app, { sharedKey: KEY });
      registerAnthropicPassthroughRoute(app, { piiProxy, fetchFn });
      await app.ready();

      await app.inject({
        method: "POST",
        url: "/anthropic/v1/messages",
        headers: {
          "x-api-key": "sk-ant",
          "content-type": "application/json",
          "user-agent": "claude-cli/1.2.3",
          "x-stainless-lang": "js",
          "x-stainless-package-version": "0.30.0",
          "anthropic-beta": "prompt-caching-2024-07-31",
        },
        payload: { model: "claude", messages: [{ role: "user", content: "hi Max Mustermann" }] },
      });

      const sentHeaders = fetchFn.mock.calls[0]![1].headers as Record<string, string>;
      expect(sentHeaders["user-agent"]).toBe("claude-cli/1.2.3");
      expect(sentHeaders["x-stainless-lang"]).toBe("js");
      expect(sentHeaders["x-stainless-package-version"]).toBe("0.30.0");
      expect(sentHeaders["anthropic-beta"]).toBe("prompt-caching-2024-07-31");
      expect(sentHeaders["x-api-key"]).toBe("sk-ant");
    });

    it("strips hop-by-hop and proxy-internal headers", async () => {
      const piiProxy = mkDpo();
      const fetchFn = vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ content: [{ type: "text", text: "ok" }] }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      );
      app = Fastify();
      registerAuth(app, { sharedKey: KEY });
      registerAnthropicPassthroughRoute(app, { piiProxy, fetchFn });
      await app.ready();

      await app.inject({
        method: "POST",
        url: "/anthropic/v1/messages",
        headers: {
          "x-api-key": "sk-ant",
          "content-type": "application/json",
          host: "localhost:4711",
          connection: "keep-alive",
          "transfer-encoding": "chunked",
          "keep-alive": "timeout=5",
          "proxy-authorization": "Basic abc",
          "x-pii-proxy-key": "secret-internal",
          "accept-encoding": "gzip, br",
        },
        payload: { model: "claude", messages: [{ role: "user", content: "hi" }] },
      });

      const sentHeaders = fetchFn.mock.calls[0]![1].headers as Record<string, string>;
      expect(sentHeaders["host"]).toBeUndefined();
      expect(sentHeaders["connection"]).toBeUndefined();
      expect(sentHeaders["transfer-encoding"]).toBeUndefined();
      expect(sentHeaders["keep-alive"]).toBeUndefined();
      expect(sentHeaders["proxy-authorization"]).toBeUndefined();
      expect(sentHeaders["x-pii-proxy-key"]).toBeUndefined();
      expect(sentHeaders["accept-encoding"]).toBeUndefined();
    });

    it("injects default anthropic-version when not provided", async () => {
      const piiProxy = mkDpo();
      const fetchFn = vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ content: [{ type: "text", text: "ok" }] }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      );
      app = Fastify();
      registerAuth(app, { sharedKey: KEY });
      registerAnthropicPassthroughRoute(app, { piiProxy, fetchFn });
      await app.ready();

      await app.inject({
        method: "POST",
        url: "/anthropic/v1/messages",
        headers: { "x-api-key": "sk-ant", "content-type": "application/json" },
        payload: { model: "claude", messages: [{ role: "user", content: "hi" }] },
      });

      const sentHeaders = fetchFn.mock.calls[0]![1].headers as Record<string, string>;
      expect(sentHeaders["anthropic-version"]).toBe("2023-06-01");
    });

    it("preserves caller-supplied anthropic-version", async () => {
      const piiProxy = mkDpo();
      const fetchFn = vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ content: [{ type: "text", text: "ok" }] }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      );
      app = Fastify();
      registerAuth(app, { sharedKey: KEY });
      registerAnthropicPassthroughRoute(app, { piiProxy, fetchFn });
      await app.ready();

      await app.inject({
        method: "POST",
        url: "/anthropic/v1/messages",
        headers: {
          "x-api-key": "sk-ant",
          "content-type": "application/json",
          "anthropic-version": "2024-10-22",
        },
        payload: { model: "claude", messages: [{ role: "user", content: "hi" }] },
      });

      const sentHeaders = fetchFn.mock.calls[0]![1].headers as Record<string, string>;
      expect(sentHeaders["anthropic-version"]).toBe("2024-10-22");
    });
  });

  describe("debug-trail integration", () => {
    let trailDir: string;
    beforeEach(() => {
      trailDir = mkdtempSync(join(tmpdir(), "dpo-trail-"));
    });
    afterEach(() => {
      if (existsSync(trailDir)) rmSync(trailDir, { recursive: true, force: true });
    });

    function readTrail(dir: string): Array<Record<string, unknown>> {
      const day = new Date().toISOString().slice(0, 10);
      const file = join(dir, `dpo-debug-trail-${day}.jsonl`);
      if (!existsSync(file)) return [];
      return readFileSync(file, "utf8")
        .split("\n")
        .filter(Boolean)
        .map((line) => JSON.parse(line) as Record<string, unknown>);
    }

    it("writes request → anonymized → external_response_raw → deanonymized on happy path", async () => {
      const piiProxy = mkDpo();
      const fetchFn = vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ content: [{ type: "text", text: "Hi [PERSON_A]" }] }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      );
      const debugTrail = new DebugTrail({ enabled: true, dir: trailDir });
      app = Fastify();
      registerAuth(app, { sharedKey: KEY });
      registerAnthropicPassthroughRoute(app, { piiProxy, fetchFn, debugTrail });
      await app.ready();

      await app.inject({
        method: "POST",
        url: "/anthropic/v1/messages",
        headers: { "x-api-key": "sk-ant", "content-type": "application/json" },
        payload: {
          model: "claude-sonnet-4-6",
          messages: [{ role: "user", content: "Hi Max Mustermann" }],
        },
      });

      const entries = readTrail(trailDir);
      const stages = entries.map((e) => e.stage);
      expect(stages).toEqual(["request", "anonymized", "external_response_raw", "deanonymized"]);
      for (const e of entries) {
        expect(e.route).toBe("anthropic-passthrough");
      }
      const request = entries[0]!;
      expect(request.text).toBe("Hi Max Mustermann");
      expect(Array.isArray(request.forwardedHeaderNames)).toBe(true);
      expect(request.forwardedHeaderNames).toContain("x-api-key");
      expect(request.streaming).toBe(false);

      const anonymized = entries[1]!;
      expect(anonymized.text).toBe("Hi [PERSON_A]");
      expect(anonymized.mappingId).toBe("m-1");

      const external = entries[2]!;
      expect(external.httpStatus).toBe(200);

      const deanon = entries[3]!;
      expect(deanon.text).toContain("Max Mustermann");
    });

    it("writes request + error entries on upstream 401 (the exact e2e case)", async () => {
      const piiProxy = mkDpo();
      const fetchFn = vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            type: "error",
            error: { type: "authentication_error", message: "invalid x-api-key" },
          }),
          { status: 401, headers: { "content-type": "application/json" } },
        ),
      );
      const debugTrail = new DebugTrail({ enabled: true, dir: trailDir });
      app = Fastify();
      registerAuth(app, { sharedKey: KEY });
      registerAnthropicPassthroughRoute(app, { piiProxy, fetchFn, debugTrail });
      await app.ready();

      const res = await app.inject({
        method: "POST",
        url: "/anthropic/v1/messages",
        headers: { "x-api-key": "sk-ant-invalid", "content-type": "application/json" },
        payload: {
          model: "claude-sonnet-4-6",
          messages: [{ role: "user", content: "Hi Max Mustermann" }],
        },
      });
      expect(res.statusCode).toBe(401);

      const entries = readTrail(trailDir);
      const stages = entries.map((e) => e.stage);
      expect(stages).toEqual(["request", "anonymized", "error"]);
      const errorEntry = entries[2]!;
      expect(errorEntry.httpStatus).toBe(401);
      expect(errorEntry.errorCode).toBe("upstream_non_2xx");
      expect(typeof errorEntry.text).toBe("string");
      expect(errorEntry.text).toMatch(/authentication_error/);
    });

    it("writes a blocked entry when pii-proxy rejects the prompt", async () => {
      const piiProxy = mkDpo({
        anonymize: vi.fn().mockResolvedValue({ blocked: true, reason: "art_9_data_detected" }),
      } as Partial<Dpo>);
      const fetchFn = vi.fn();
      const debugTrail = new DebugTrail({ enabled: true, dir: trailDir });
      app = Fastify();
      registerAuth(app, { sharedKey: KEY });
      registerAnthropicPassthroughRoute(app, { piiProxy, fetchFn, debugTrail });
      await app.ready();

      await app.inject({
        method: "POST",
        url: "/anthropic/v1/messages",
        headers: { "x-api-key": "sk-ant", "content-type": "application/json" },
        payload: { model: "claude", messages: [{ role: "user", content: "Blutgruppe A+" }] },
      });

      const entries = readTrail(trailDir);
      const stages = entries.map((e) => e.stage);
      expect(stages).toEqual(["request", "blocked"]);
      expect(entries[1]!.blockedReason).toBe("art_9_data_detected");
      expect(fetchFn).not.toHaveBeenCalled();
    });

    it("writes nothing when debug-trail is disabled", async () => {
      const piiProxy = mkDpo();
      const fetchFn = vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ content: [{ type: "text", text: "ok" }] }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      );
      const debugTrail = new DebugTrail({ enabled: false });
      app = Fastify();
      registerAuth(app, { sharedKey: KEY });
      registerAnthropicPassthroughRoute(app, { piiProxy, fetchFn, debugTrail });
      await app.ready();

      await app.inject({
        method: "POST",
        url: "/anthropic/v1/messages",
        headers: { "x-api-key": "sk-ant", "content-type": "application/json" },
        payload: { model: "claude", messages: [{ role: "user", content: "hi" }] },
      });

      expect(readTrail(trailDir)).toHaveLength(0);
    });
  });
});
