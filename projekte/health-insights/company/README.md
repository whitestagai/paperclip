# Health Insights — Agent Company

A small, personal Hub-and-Spoke company that analyses Walter's Apple-Health data locally. All processing — including the LLM (LM Studio) — runs on the same Mac. No data leaves the device.

## Workflow

```
Apple Health (iPhone)
    ↓ Health Auto Export
iCloud Drive → n8n → Postgres + Obsidian Markdown
                              ↓
                            CHO  ←─── User Q&A
                          ↙  ↓  ↘
            Schlafcoach   Trainingscoach   Vitals-Monitor
                          ↓  ↓  ↓
                        CHO consolidates
                              ↓
                        Briefing Issue
                        + Obsidian block
```

The data pipeline (Apple Health → Postgres) lives **outside** the company. The company's job is interpretation: turn aggregated daily values into a coherent briefing or answer a Q&A question.

## Org Chart

| Agent | Role | Reports to | Domain |
|---|---|---|---|
| **CHO** | Chief Health Officer (CEO equivalent) | — | Briefing orchestration, Q&A routing, consolidation |
| **Schlafcoach** | Sleep & recovery specialist | CHO | Sleep stages, HRV, resting HR, respiratory rate, recovery |
| **Trainingscoach** | Activity & performance specialist | CHO | Workouts, steps, energy, training load, gait |
| **Vitals-Monitor** | Vitals & anomaly specialist | CHO | Heart rate, SpO₂, wrist temperature, audio exposure, anomalies |

Specialists never talk to each other directly — the CHO is the only consolidation point. This avoids agent loops and keeps each prompt small (helpful for local LLMs).

## Data Access

All agents read from the local `paperclip-health` MCP server, which exposes Postgres-backed tools:

- `get_daily_summary(target_date)` — all metrics for one day with min/max/avg/sum
- `get_metric_range(metric, from_date, to_date, agg='daily')` — trend over time with stats
- `get_workouts(from_date, to_date, workout_type?)` — workout records

Agents have **no** write access to the database. Their only output channels are Paperclip issues/comments and (via the CHO) a Markdown block in Walter's Obsidian vault.

## Privacy

- Postgres binds to `localhost:5432`
- The MCP server runs locally as a launchd service
- The LLM is LM Studio (local) via the `paperclip-adapter-lmstudio` adapter
- No outbound traffic during agent operation

If you import this company onto a different machine, you must reproduce the data pipeline there — the company assumes a populated `paperclip_health.health_*` schema and an MCP server reachable as `paperclip-health`.

## Getting Started

```bash
paperclipai company import --from /path/to/this/folder
```

After import, configure each agent in the Paperclip UI:

1. Bind the `paperclip-health` MCP server to all four agents
2. Set the LLM adapter to LM Studio with a model that supports tool use (e.g. Qwen 2.5 32B Instruct, Llama 3.1 70B Instruct)
3. Smoke-test by asking the CHO: *"Welche Metriken hast du für heute?"*

Phase-2 onwards adds a daily briefing routine, anomaly detection, weekly trend reports and voice input — see the [spec](../../docs/superpowers/specs/2026-05-09-health-insights-company-design.md) and [phase-1 plan](../../docs/superpowers/plans/2026-05-09-health-insights-phase-1.md).

## References

- [Agent Companies Specification](https://agentcompanies.io/specification)
- [Paperclip](https://github.com/paperclipai/paperclip)
- Internal spec: [docs/superpowers/specs/2026-05-09-health-insights-company-design.md](../../docs/superpowers/specs/2026-05-09-health-insights-company-design.md)
