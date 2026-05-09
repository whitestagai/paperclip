# paperclip-health-mcp

Local MCP server exposing Apple Health Postgres data as queryable tools.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Environment

- `PAPERCLIP_HEALTH_DB_URL` — Postgres connection string for the `health` database
  (e.g. `postgresql://paperclip_health_mcp:PASSWORD@localhost:5432/health`)

## Run

```bash
PAPERCLIP_HEALTH_DB_URL=... paperclip-health-mcp
```

## Test

```bash
PAPERCLIP_HEALTH_TEST_DB_URL=postgresql://...@localhost/health_test pytest -v
```

## Tools exposed

- `get_daily_summary(date)` — all metrics aggregated for one day
- `get_metric_range(metric, from, to, agg)` — time series for one metric, with stats + trend
- `get_workouts(from, to, type?)` — workout list in a date range
