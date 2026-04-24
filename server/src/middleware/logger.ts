import path from "node:path";
import fs from "node:fs";
import pino from "pino";
import { pinoHttp } from "pino-http";
import { readConfigFile } from "../config-file.js";
import { resolveDefaultLogsDir, resolveHomeAwarePath } from "../home-paths.js";
import { shouldSilenceHttpSuccessLog } from "./http-log-policy.js";

function resolveServerLogDir(): string {
  const envOverride = process.env.PAPERCLIP_LOG_DIR?.trim();
  if (envOverride) return resolveHomeAwarePath(envOverride);

  const fileLogDir = readConfigFile()?.logging.logDir?.trim();
  if (fileLogDir) return resolveHomeAwarePath(fileLogDir);

  return resolveDefaultLogsDir();
}

const logDir = resolveServerLogDir();
fs.mkdirSync(logDir, { recursive: true });

const sharedOpts = {
  translateTime: "SYS:HH:MM:ss",
  ignore: "pid,hostname",
  singleLine: true,
};

/**
 * Reduziert das Log-Volumen durch Begrenzung der Request-Header.
 * Nur relevante Felder werden geloggt; Cookies und große Header werden redactet.
 */
const reqSerializer = pino.stdSerializers.req;

export const logger = pino({
  level: "debug",
  redact: [
    "req.headers.authorization",
    "req.headers.cookie",
    'req.headers["referer"]',
    'req.headers["x-forwarded-for"]',
  ],
  serializers: {
    req: (req) => {
      const serialized = reqSerializer(req);
      // Nur relevante Header behalten, große Werte redacten
      if (serialized?.headers) {
        const headers: Record<string, string> = {};
        const keepHeaders = new Set([
          "host",
          "content-type",
          "accept",
          "user-agent",
          "x-request-id",
        ]);
        for (const [key, value] of Object.entries(serialized.headers)) {
          const lowerKey = key.toLowerCase();
          if (keepHeaders.has(lowerKey)) {
            headers[key] = String(value);
          } else if (lowerKey === "cookie" || lowerKey.startsWith("x-")) {
            headers[key] = "[redacted]";
          } else {
            // Alle anderen Header beibehalten, aber kürzen
            const strVal = String(value);
            headers[key] = strVal.length > 200 ? `${strVal.slice(0, 197)}...` : strVal;
          }
        }
        serialized.headers = headers;
      }
      return serialized;
    },
  },
}, pino.transport({
  targets: [
    {
      target: "pino-pretty",
      options: { ...sharedOpts, ignore: "pid,hostname,req,res,responseTime", colorize: true, destination: 1 },
      level: "info",
    },
    {
      target: "pino-roll",
      options: {
        file: "server.log",
        directory: logDir,
        size: "50m",
        frequency: "daily",
        limit: { count: 7 },
        mkdir: true,
        ...sharedOpts,
      },
      level: "debug",
    },
  ],
}));

export const httpLogger = pinoHttp({
  logger,
  customLogLevel(_req, res, err) {
    if (shouldSilenceHttpSuccessLog(_req.method, _req.url, res.statusCode)) {
      return "silent";
    }
    if (err || res.statusCode >= 500) return "error";
    if (res.statusCode >= 400) return "warn";
    return "info";
  },
  customSuccessMessage(req, res) {
    return `${req.method} ${req.url} ${res.statusCode}`;
  },
  customErrorMessage(req, res, err) {
    const ctx = (res as any).__errorContext;
    const errMsg = ctx?.error?.message || err?.message || (res as any).err?.message || "unknown error";
    return `${req.method} ${req.url} ${res.statusCode} — ${errMsg}`;
  },
  customProps(req, res) {
    if (res.statusCode >= 400) {
      const ctx = (res as any).__errorContext;
      if (ctx) {
        return {
          errorContext: ctx.error,
          reqBody: ctx.reqBody,
          reqParams: ctx.reqParams,
          reqQuery: ctx.reqQuery,
        };
      }
      const props: Record<string, unknown> = {};
      const { body, params, query } = req as any;
      if (body && typeof body === "object" && Object.keys(body).length > 0) {
        props.reqBody = body;
      }
      if (params && typeof params === "object" && Object.keys(params).length > 0) {
        props.reqParams = params;
      }
      if (query && typeof query === "object" && Object.keys(query).length > 0) {
        props.reqQuery = query;
      }
      if ((req as any).route?.path) {
        props.routePath = (req as any).route.path;
      }
      return props;
    }
    return {};
  },
});
