# Health Insights Company (Paperclip)

Local Apple Health data analysis via Paperclip multi-agent company.

**Spec:** [../../docs/superpowers/specs/2026-05-09-health-insights-company-design.md](../../docs/superpowers/specs/2026-05-09-health-insights-company-design.md)

**Phase 1 scope:**
- Postgres schema for health samples + daily aggregates
- n8n ingest workflow (iCloud → Postgres + Markdown)
- Local MCP server with 3 query tools
- One generalist Health agent for Q&A

## Components

- `db/` — Postgres schema
- `mcp-server/` — Python MCP server (asyncpg)
- `n8n/` — exported `health-ingest V1` workflow
- `scripts/` — launchd config for MCP server
- `docs/` — iPhone setup guide and metric mapping
- `company/` — Paperclip agent system prompt
- `data/` — generated daily/weekly Markdown summaries (not committed)

## Setup

See [docs/health-auto-export-setup.md](docs/health-auto-export-setup.md) for iPhone setup.
See `mcp-server/README.md` for server setup.

## Privacy

All processing local. No cloud LLM. See spec for details.
