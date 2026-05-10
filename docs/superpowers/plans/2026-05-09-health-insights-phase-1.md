# Health Insights Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the foundation of the Health Insights Company — Postgres schema, n8n ingest pipeline, local MCP server with 3 query tools, and one generalist Paperclip agent that can answer Q&A about Apple Health data.

**Architecture:** Apple Health data flows iPhone → Health Auto Export → iCloud Drive → n8n watcher → Postgres (raw samples + daily aggregates) + Markdown daily summaries. A local Python MCP server exposes Postgres-backed tools. A single "Health Generalist" Paperclip agent uses those tools via local LLM (LM Studio).

**Tech Stack:** Postgres 18, Python 3.14 (asyncpg + mcp), n8n, Paperclip CLI, LM Studio. Spec: [docs/superpowers/specs/2026-05-09-health-insights-company-design.md](../specs/2026-05-09-health-insights-company-design.md).

**Out of scope (Phase 2+):** specialist agents (Schlafcoach/Trainingscoach/Vitals-Monitor), daily briefing routine, anomaly detection, weekly reports, Telegram notifications.

---

## File Structure

All Phase 1 artifacts under `projekte/health-insights/`:

```
projekte/health-insights/
├── README.md                               # project overview, setup, runbook
├── db/
│   └── schema.sql                          # Postgres tables, indexes
├── mcp-server/
│   ├── pyproject.toml                      # Python deps + project metadata
│   ├── README.md                           # MCP server-specific docs
│   ├── src/paperclip_health_mcp/
│   │   ├── __init__.py
│   │   ├── server.py                       # MCP entrypoint + tool registration
│   │   ├── db.py                           # asyncpg pool wrapper
│   │   ├── stats.py                        # trend + summary stats helpers
│   │   └── tools.py                        # 3 tool implementations
│   └── tests/
│       ├── conftest.py                     # pytest fixtures (test DB, sample data)
│       ├── test_db.py
│       ├── test_stats.py
│       └── test_tools.py
├── n8n/
│   └── health-ingest V1.json               # exported workflow
├── scripts/
│   └── com.paperclip.health-mcp.plist      # launchd config
├── docs/
│   ├── health-auto-export-setup.md         # iPhone setup guide
│   └── metric-mapping.md                   # Health Auto Export → canonical metric names
└── company/
    └── health-generalist-system-prompt.md  # agent prompt
```

**Why this structure:**
- One clear responsibility per file. `db.py` only owns the pool; `tools.py` only owns tool logic; `stats.py` only owns numerical helpers — easy to test in isolation
- `mcp-server/` is a self-contained Python package — can be developed, tested, packaged independently
- n8n workflow as JSON in repo (versioned per Walter's `V1, V2, V3` rule)
- `company/` only has the agent's prompt; the actual company is created via Paperclip CLI in Task 15

---

## Task 0: Project Scaffolding

**Files:**
- Create: `projekte/health-insights/README.md`
- Create: directory tree above (empty subdirs ok)

- [ ] **Step 1: Create directory tree**

```bash
cd "/Users/walterschoenenbroecher.de/SynologyDrive/2026/AI/Claude Code/Paperclip"
mkdir -p projekte/health-insights/{db,mcp-server/src/paperclip_health_mcp,mcp-server/tests,n8n,scripts,docs,company}
mkdir -p projekte/health-insights/data/{daily,weekly}
```

- [ ] **Step 2: Write README**

Create `projekte/health-insights/README.md`:

```markdown
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
```

- [ ] **Step 3: Add data/ to .gitignore**

Append to `projekte/health-insights/.gitignore`:

```
data/
mcp-server/.venv/
mcp-server/.pytest_cache/
mcp-server/**/__pycache__/
*.log
```

- [ ] **Step 4: Commit**

```bash
git add projekte/health-insights/README.md projekte/health-insights/.gitignore
git commit -m "feat(health): scaffold health-insights project structure"
```

---

## Task 1: Postgres Schema

**Files:**
- Create: `projekte/health-insights/db/schema.sql`

- [ ] **Step 1: Write schema.sql**

Create `projekte/health-insights/db/schema.sql`:

```sql
-- Health Insights Phase 1 schema
-- Database: health (created separately via createdb)
-- Schema: paperclip_health

CREATE SCHEMA IF NOT EXISTS paperclip_health;
SET search_path TO paperclip_health;

-- Raw samples: each Apple Health datum, JSONB for flexibility
CREATE TABLE IF NOT EXISTS health_samples (
  id BIGSERIAL PRIMARY KEY,
  metric VARCHAR(64) NOT NULL,
  source VARCHAR(64),
  start_ts TIMESTAMPTZ NOT NULL,
  end_ts TIMESTAMPTZ,
  value DOUBLE PRECISION,
  unit VARCHAR(32),
  raw JSONB,
  ingested_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (metric, source, start_ts)
);
CREATE INDEX IF NOT EXISTS idx_samples_metric_start
  ON health_samples (metric, start_ts DESC);
CREATE INDEX IF NOT EXISTS idx_samples_start_brin
  ON health_samples USING BRIN (start_ts);

-- Daily aggregates: pre-computed per (date, metric)
CREATE TABLE IF NOT EXISTS health_daily (
  date DATE NOT NULL,
  metric VARCHAR(64) NOT NULL,
  min DOUBLE PRECISION,
  max DOUBLE PRECISION,
  avg DOUBLE PRECISION,
  sum DOUBLE PRECISION,
  count INTEGER,
  computed_at TIMESTAMPTZ DEFAULT NOW(),
  PRIMARY KEY (date, metric)
);

-- Workouts: separate because of structure
CREATE TABLE IF NOT EXISTS health_workouts (
  id BIGSERIAL PRIMARY KEY,
  start_ts TIMESTAMPTZ NOT NULL,
  end_ts TIMESTAMPTZ NOT NULL,
  type VARCHAR(64),
  duration_sec INTEGER,
  active_energy_kcal DOUBLE PRECISION,
  distance_m DOUBLE PRECISION,
  avg_hr DOUBLE PRECISION,
  raw JSONB,
  UNIQUE (start_ts, type)
);
CREATE INDEX IF NOT EXISTS idx_workouts_start
  ON health_workouts (start_ts DESC);

-- Ingest run marker (used by Paperclip routine in Phase 2 to gate briefings)
CREATE TABLE IF NOT EXISTS health_ingest_runs (
  date DATE PRIMARY KEY,
  status VARCHAR(16) NOT NULL,
  files_processed INTEGER DEFAULT 0,
  samples_written INTEGER DEFAULT 0,
  finished_at TIMESTAMPTZ DEFAULT NOW()
);
```

- [ ] **Step 2: Create database and apply schema**

```bash
createdb health
psql -d health -f projekte/health-insights/db/schema.sql
```

Expected output: a series of `CREATE SCHEMA`, `CREATE TABLE`, `CREATE INDEX` lines, no errors.

- [ ] **Step 3: Verify schema**

```bash
psql -d health -c "\dt paperclip_health.*"
```

Expected: 4 rows — `health_samples`, `health_daily`, `health_workouts`, `health_ingest_runs`.

- [ ] **Step 4: Create dedicated DB role for the MCP server**

```bash
psql -d health <<'SQL'
CREATE ROLE paperclip_health_mcp WITH LOGIN PASSWORD 'change-me-after-task';
GRANT USAGE ON SCHEMA paperclip_health TO paperclip_health_mcp;
GRANT SELECT ON ALL TABLES IN SCHEMA paperclip_health TO paperclip_health_mcp;
ALTER DEFAULT PRIVILEGES IN SCHEMA paperclip_health
  GRANT SELECT ON TABLES TO paperclip_health_mcp;
SQL
```

Then prompt Walter to set a real password (manual step):

```bash
psql -d health -c "ALTER ROLE paperclip_health_mcp WITH PASSWORD '<chosen-by-walter>';"
```

- [ ] **Step 5: Commit**

```bash
git add projekte/health-insights/db/schema.sql
git commit -m "feat(health): add Postgres schema for samples, daily aggregates, workouts"
```

---

## Task 2: MCP Server Scaffolding

**Files:**
- Create: `projekte/health-insights/mcp-server/pyproject.toml`
- Create: `projekte/health-insights/mcp-server/README.md`
- Create: `projekte/health-insights/mcp-server/src/paperclip_health_mcp/__init__.py`

- [ ] **Step 1: Write pyproject.toml**

Create `projekte/health-insights/mcp-server/pyproject.toml`:

```toml
[project]
name = "paperclip-health-mcp"
version = "0.1.0"
description = "MCP server exposing Postgres-backed Apple Health query tools"
requires-python = ">=3.12"
dependencies = [
    "mcp>=1.0",
    "asyncpg>=0.29",
    "pydantic>=2.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
]

[project.scripts]
paperclip-health-mcp = "paperclip_health_mcp.server:main"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: Create venv and install**

```bash
cd projekte/health-insights/mcp-server
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Expected: `Successfully installed paperclip-health-mcp-0.1.0 mcp-... asyncpg-... pytest-...`

- [ ] **Step 3: Write empty package init**

Create `projekte/health-insights/mcp-server/src/paperclip_health_mcp/__init__.py`:

```python
"""Paperclip Health MCP server."""

__version__ = "0.1.0"
```

- [ ] **Step 4: Write MCP server README**

Create `projekte/health-insights/mcp-server/README.md`:

```markdown
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
```

- [ ] **Step 5: Commit**

```bash
git add projekte/health-insights/mcp-server/pyproject.toml \
        projekte/health-insights/mcp-server/README.md \
        projekte/health-insights/mcp-server/src/paperclip_health_mcp/__init__.py
git commit -m "feat(health-mcp): scaffold MCP server package"
```

---

## Task 3: DB Connection Layer (TDD)

**Files:**
- Create: `projekte/health-insights/mcp-server/tests/conftest.py`
- Create: `projekte/health-insights/mcp-server/tests/test_db.py`
- Create: `projekte/health-insights/mcp-server/src/paperclip_health_mcp/db.py`

- [ ] **Step 1: Set up test database**

Apply the same schema to a separate DB:

```bash
createdb health_test
psql -d health_test -f projekte/health-insights/db/schema.sql
```

Set an env var for tests:

```bash
echo 'export PAPERCLIP_HEALTH_TEST_DB_URL=postgresql://localhost/health_test' >> ~/.zshrc
# In current shell:
export PAPERCLIP_HEALTH_TEST_DB_URL=postgresql://localhost/health_test
```

- [ ] **Step 2: Write conftest.py with shared fixtures**

Create `projekte/health-insights/mcp-server/tests/conftest.py`:

```python
import os
import pytest
import asyncpg


TEST_DB_URL = os.environ["PAPERCLIP_HEALTH_TEST_DB_URL"]


@pytest.fixture
async def db_pool():
    """Fresh asyncpg pool against the test database."""
    pool = await asyncpg.create_pool(
        TEST_DB_URL,
        min_size=1,
        max_size=2,
        server_settings={"search_path": "paperclip_health"},
    )
    try:
        yield pool
    finally:
        await pool.close()


@pytest.fixture
async def clean_db(db_pool):
    """Truncate all tables before the test runs. Use when you need an empty slate."""
    async with db_pool.acquire() as conn:
        await conn.execute(
            "TRUNCATE health_samples, health_daily, health_workouts, "
            "health_ingest_runs RESTART IDENTITY"
        )
    yield db_pool
```

- [ ] **Step 3: Write the failing test**

Create `projekte/health-insights/mcp-server/tests/test_db.py`:

```python
import os
import pytest
from paperclip_health_mcp.db import create_pool, get_pool, close_pool


@pytest.mark.asyncio
async def test_create_pool_uses_env_url():
    os.environ["PAPERCLIP_HEALTH_DB_URL"] = os.environ["PAPERCLIP_HEALTH_TEST_DB_URL"]
    pool = await create_pool()
    try:
        async with pool.acquire() as conn:
            result = await conn.fetchval("SELECT 1")
        assert result == 1
    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_get_pool_returns_singleton():
    os.environ["PAPERCLIP_HEALTH_DB_URL"] = os.environ["PAPERCLIP_HEALTH_TEST_DB_URL"]
    p1 = await get_pool()
    p2 = await get_pool()
    assert p1 is p2
    await close_pool()
```

- [ ] **Step 4: Run test and verify it fails**

```bash
cd projekte/health-insights/mcp-server
source .venv/bin/activate
pytest tests/test_db.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'paperclip_health_mcp.db'`

- [ ] **Step 5: Implement db.py**

Create `projekte/health-insights/mcp-server/src/paperclip_health_mcp/db.py`:

```python
"""Postgres connection pool for the health MCP server."""
import os
import asyncpg

_pool: asyncpg.Pool | None = None


async def create_pool() -> asyncpg.Pool:
    """Create a new asyncpg pool from PAPERCLIP_HEALTH_DB_URL."""
    url = os.environ["PAPERCLIP_HEALTH_DB_URL"]
    return await asyncpg.create_pool(
        url,
        min_size=1,
        max_size=4,
        server_settings={"search_path": "paperclip_health"},
    )


async def get_pool() -> asyncpg.Pool:
    """Lazily create and cache a process-wide pool."""
    global _pool
    if _pool is None:
        _pool = await create_pool()
    return _pool


async def close_pool() -> None:
    """Close the cached pool. Mainly for tests."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
```

- [ ] **Step 6: Run tests and verify they pass**

```bash
pytest tests/test_db.py -v
```

Expected: 2 PASSED.

- [ ] **Step 7: Commit**

```bash
git add projekte/health-insights/mcp-server/tests/conftest.py \
        projekte/health-insights/mcp-server/tests/test_db.py \
        projekte/health-insights/mcp-server/src/paperclip_health_mcp/db.py
git commit -m "feat(health-mcp): asyncpg connection pool with env-driven config"
```

---

## Task 4: Stats Helper (TDD)

**Files:**
- Create: `projekte/health-insights/mcp-server/tests/test_stats.py`
- Create: `projekte/health-insights/mcp-server/src/paperclip_health_mcp/stats.py`

- [ ] **Step 1: Write failing tests**

Create `projekte/health-insights/mcp-server/tests/test_stats.py`:

```python
import pytest
from paperclip_health_mcp.stats import summary_stats, linear_trend


def test_summary_stats_basic():
    s = summary_stats([1.0, 2.0, 3.0, 4.0, 5.0])
    assert s["min"] == 1.0
    assert s["max"] == 5.0
    assert s["mean"] == 3.0
    assert s["median"] == 3.0
    assert s["count"] == 5
    assert s["stddev"] == pytest.approx(1.5811, abs=1e-3)


def test_summary_stats_empty():
    assert summary_stats([]) == {
        "min": None, "max": None, "mean": None,
        "median": None, "stddev": None, "count": 0,
    }


def test_summary_stats_single_value():
    s = summary_stats([42.0])
    assert s["min"] == s["max"] == s["mean"] == s["median"] == 42.0
    assert s["stddev"] == 0.0
    assert s["count"] == 1


def test_linear_trend_rising():
    # values rise by 1 per index
    t = linear_trend([1.0, 2.0, 3.0, 4.0, 5.0])
    assert t["slope_per_step"] == pytest.approx(1.0, abs=1e-6)
    assert t["direction"] == "rising"


def test_linear_trend_flat():
    t = linear_trend([3.0, 3.0, 3.0, 3.0])
    assert t["slope_per_step"] == pytest.approx(0.0, abs=1e-6)
    assert t["direction"] == "flat"


def test_linear_trend_falling():
    t = linear_trend([10.0, 8.0, 6.0, 4.0])
    assert t["slope_per_step"] == pytest.approx(-2.0, abs=1e-6)
    assert t["direction"] == "falling"


def test_linear_trend_too_few_points():
    assert linear_trend([5.0])["direction"] == "insufficient_data"
    assert linear_trend([])["direction"] == "insufficient_data"
```

- [ ] **Step 2: Run tests and verify they fail**

```bash
pytest tests/test_stats.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'paperclip_health_mcp.stats'`

- [ ] **Step 3: Implement stats.py**

Create `projekte/health-insights/mcp-server/src/paperclip_health_mcp/stats.py`:

```python
"""Numerical helpers for time-series summaries.

These run in Python (not Postgres) because the row counts are small —
we only operate on already-aggregated daily values.
"""
import statistics
from typing import Sequence


def summary_stats(values: Sequence[float]) -> dict:
    """min/max/mean/median/stddev for a list of floats. Empty list -> all None."""
    if not values:
        return {"min": None, "max": None, "mean": None,
                "median": None, "stddev": None, "count": 0}
    if len(values) == 1:
        v = float(values[0])
        return {"min": v, "max": v, "mean": v, "median": v,
                "stddev": 0.0, "count": 1}
    return {
        "min": min(values),
        "max": max(values),
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "stddev": statistics.stdev(values),
        "count": len(values),
    }


def linear_trend(values: Sequence[float], flat_threshold: float = 0.05) -> dict:
    """Least-squares slope per step plus direction label.

    Direction labels: rising | falling | flat | insufficient_data.
    flat_threshold is in absolute slope_per_step terms; below it we report flat.
    """
    n = len(values)
    if n < 2:
        return {"slope_per_step": None, "direction": "insufficient_data"}
    # least-squares slope: sum((x - x_mean)(y - y_mean)) / sum((x - x_mean)^2)
    x_mean = (n - 1) / 2.0
    y_mean = sum(values) / n
    num = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    den = sum((i - x_mean) ** 2 for i in range(n))
    slope = num / den if den else 0.0
    if abs(slope) < flat_threshold:
        direction = "flat"
    elif slope > 0:
        direction = "rising"
    else:
        direction = "falling"
    return {"slope_per_step": slope, "direction": direction}
```

- [ ] **Step 4: Run tests and verify they pass**

```bash
pytest tests/test_stats.py -v
```

Expected: 7 PASSED.

- [ ] **Step 5: Commit**

```bash
git add projekte/health-insights/mcp-server/tests/test_stats.py \
        projekte/health-insights/mcp-server/src/paperclip_health_mcp/stats.py
git commit -m "feat(health-mcp): summary stats and linear trend helpers"
```

---

## Task 5: Tool — get_daily_summary (TDD)

**Files:**
- Modify: `projekte/health-insights/mcp-server/tests/test_tools.py` (create)
- Create: `projekte/health-insights/mcp-server/src/paperclip_health_mcp/tools.py`

- [ ] **Step 1: Write failing test**

Create `projekte/health-insights/mcp-server/tests/test_tools.py`:

```python
import pytest
from datetime import date
from paperclip_health_mcp.tools import get_daily_summary


@pytest.mark.asyncio
async def test_get_daily_summary_returns_aggregates(clean_db):
    pool = clean_db
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO health_daily (date, metric, min, max, avg, sum, count) VALUES "
            "($1, 'sleep_asleep_seconds', NULL, NULL, NULL, 25920, 1), "
            "($1, 'hrv_sdnn',           42.0, 58.0, 50.0,  NULL, 12), "
            "($1, 'step_count',         NULL, NULL, NULL, 8412, 24)",
            date(2026, 5, 8),
        )
    result = await get_daily_summary(pool, date(2026, 5, 8))
    assert result["date"] == "2026-05-08"
    assert len(result["metrics"]) == 3
    sleep = next(m for m in result["metrics"] if m["metric"] == "sleep_asleep_seconds")
    assert sleep["sum"] == 25920
    hrv = next(m for m in result["metrics"] if m["metric"] == "hrv_sdnn")
    assert hrv["avg"] == 50.0


@pytest.mark.asyncio
async def test_get_daily_summary_empty_date(clean_db):
    pool = clean_db
    result = await get_daily_summary(pool, date(2026, 5, 8))
    assert result == {"date": "2026-05-08", "metrics": []}
```

- [ ] **Step 2: Run test, verify failure**

```bash
pytest tests/test_tools.py::test_get_daily_summary_returns_aggregates -v
```

Expected: FAIL — `ImportError: cannot import name 'get_daily_summary'`.

- [ ] **Step 3: Implement get_daily_summary**

Create `projekte/health-insights/mcp-server/src/paperclip_health_mcp/tools.py`:

```python
"""Tool implementations. All tools take an asyncpg.Pool plus typed args
and return JSON-serializable dicts."""
from datetime import date
import asyncpg


async def get_daily_summary(pool: asyncpg.Pool, target_date: date) -> dict:
    """All metrics aggregated for a single calendar date."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT metric, min, max, avg, sum, count "
            "FROM health_daily WHERE date = $1 ORDER BY metric",
            target_date,
        )
    return {
        "date": target_date.isoformat(),
        "metrics": [
            {
                "metric": r["metric"],
                "min": r["min"],
                "max": r["max"],
                "avg": r["avg"],
                "sum": r["sum"],
                "count": r["count"],
            }
            for r in rows
        ],
    }
```

- [ ] **Step 4: Run tests, verify pass**

```bash
pytest tests/test_tools.py -v
```

Expected: 2 PASSED.

- [ ] **Step 5: Commit**

```bash
git add projekte/health-insights/mcp-server/tests/test_tools.py \
        projekte/health-insights/mcp-server/src/paperclip_health_mcp/tools.py
git commit -m "feat(health-mcp): get_daily_summary tool"
```

---

## Task 6: Tool — get_metric_range (TDD)

**Files:**
- Modify: `projekte/health-insights/mcp-server/tests/test_tools.py`
- Modify: `projekte/health-insights/mcp-server/src/paperclip_health_mcp/tools.py`

- [ ] **Step 1: Append failing test**

Append to `projekte/health-insights/mcp-server/tests/test_tools.py`:

```python
from paperclip_health_mcp.tools import get_metric_range


@pytest.mark.asyncio
async def test_get_metric_range_daily_with_stats_and_trend(clean_db):
    pool = clean_db
    async with pool.acquire() as conn:
        # 7 days of HRV, slowly declining
        for i, v in enumerate([55, 53, 52, 50, 49, 47, 46]):
            await conn.execute(
                "INSERT INTO health_daily (date, metric, avg, count) VALUES ($1, 'hrv_sdnn', $2, 12)",
                date(2026, 5, 1 + i), float(v),
            )
    result = await get_metric_range(
        pool, "hrv_sdnn", date(2026, 5, 1), date(2026, 5, 7), agg="daily"
    )
    assert result["metric"] == "hrv_sdnn"
    assert result["agg"] == "daily"
    assert len(result["values"]) == 7
    assert result["values"][0] == {"date": "2026-05-01", "value": 55.0}
    assert result["stats"]["count"] == 7
    assert result["stats"]["min"] == 46.0
    assert result["stats"]["max"] == 55.0
    assert result["trend"]["direction"] == "falling"
    assert result["trend"]["slope_per_step"] < 0


@pytest.mark.asyncio
async def test_get_metric_range_unknown_agg_raises(clean_db):
    with pytest.raises(ValueError, match="agg"):
        await get_metric_range(
            clean_db, "hrv_sdnn", date(2026, 5, 1), date(2026, 5, 7), agg="hourly"
        )


@pytest.mark.asyncio
async def test_get_metric_range_no_data(clean_db):
    result = await get_metric_range(
        clean_db, "hrv_sdnn", date(2026, 5, 1), date(2026, 5, 7), agg="daily"
    )
    assert result["values"] == []
    assert result["stats"]["count"] == 0
    assert result["trend"]["direction"] == "insufficient_data"
```

- [ ] **Step 2: Run tests, verify failure**

```bash
pytest tests/test_tools.py -v
```

Expected: 3 NEW failures (`ImportError: cannot import name 'get_metric_range'`).

- [ ] **Step 3: Append get_metric_range to tools.py**

Append to `projekte/health-insights/mcp-server/src/paperclip_health_mcp/tools.py`:

```python
from .stats import summary_stats, linear_trend


VALID_AGGS = {"daily"}  # Phase 1 supports daily only; weekly/hourly later


async def get_metric_range(
    pool: asyncpg.Pool,
    metric: str,
    from_date: date,
    to_date: date,
    agg: str = "daily",
) -> dict:
    """Time series of a single metric over a date range, with stats and trend.

    For agg='daily' we read from health_daily.avg (or sum if avg is NULL —
    cumulative metrics like step_count store in sum). One row per day in range.
    """
    if agg not in VALID_AGGS:
        raise ValueError(f"Unsupported agg={agg!r}; valid: {sorted(VALID_AGGS)}")

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT date, COALESCE(avg, sum) AS value "
            "FROM health_daily "
            "WHERE metric = $1 AND date BETWEEN $2 AND $3 "
            "ORDER BY date",
            metric, from_date, to_date,
        )

    values = [{"date": r["date"].isoformat(), "value": r["value"]} for r in rows]
    numeric_values = [r["value"] for r in rows if r["value"] is not None]
    return {
        "metric": metric,
        "from": from_date.isoformat(),
        "to": to_date.isoformat(),
        "agg": agg,
        "stats": summary_stats(numeric_values),
        "trend": linear_trend(numeric_values),
        "values": values,
    }
```

- [ ] **Step 4: Run tests, verify pass**

```bash
pytest tests/test_tools.py -v
```

Expected: all 5 PASSED.

- [ ] **Step 5: Commit**

```bash
git add projekte/health-insights/mcp-server/tests/test_tools.py \
        projekte/health-insights/mcp-server/src/paperclip_health_mcp/tools.py
git commit -m "feat(health-mcp): get_metric_range tool with stats and trend"
```

---

## Task 7: Tool — get_workouts (TDD)

**Files:**
- Modify: `projekte/health-insights/mcp-server/tests/test_tools.py`
- Modify: `projekte/health-insights/mcp-server/src/paperclip_health_mcp/tools.py`

- [ ] **Step 1: Append failing test**

Append to `tests/test_tools.py`:

```python
from datetime import datetime, timezone
from paperclip_health_mcp.tools import get_workouts


@pytest.mark.asyncio
async def test_get_workouts_returns_list_in_range(clean_db):
    pool = clean_db
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO health_workouts "
            "(start_ts, end_ts, type, duration_sec, active_energy_kcal, distance_m, avg_hr) "
            "VALUES ($1, $2, 'Running', 1800, 320, 5200, 148)",
            datetime(2026, 5, 5, 7, 0, tzinfo=timezone.utc),
            datetime(2026, 5, 5, 7, 30, tzinfo=timezone.utc),
        )
        await conn.execute(
            "INSERT INTO health_workouts "
            "(start_ts, end_ts, type, duration_sec, active_energy_kcal) "
            "VALUES ($1, $2, 'Strength', 2700, 180)",
            datetime(2026, 5, 6, 18, 0, tzinfo=timezone.utc),
            datetime(2026, 5, 6, 18, 45, tzinfo=timezone.utc),
        )
    result = await get_workouts(pool, date(2026, 5, 1), date(2026, 5, 7))
    assert len(result["workouts"]) == 2
    assert result["workouts"][0]["type"] == "Running"
    assert result["workouts"][0]["duration_sec"] == 1800
    assert result["count"] == 2


@pytest.mark.asyncio
async def test_get_workouts_filtered_by_type(clean_db):
    pool = clean_db
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO health_workouts (start_ts, end_ts, type, duration_sec) VALUES "
            "($1, $2, 'Running', 1800), ($3, $4, 'Strength', 2700)",
            datetime(2026, 5, 5, 7, 0, tzinfo=timezone.utc),
            datetime(2026, 5, 5, 7, 30, tzinfo=timezone.utc),
            datetime(2026, 5, 6, 18, 0, tzinfo=timezone.utc),
            datetime(2026, 5, 6, 18, 45, tzinfo=timezone.utc),
        )
    result = await get_workouts(
        pool, date(2026, 5, 1), date(2026, 5, 7), workout_type="Running"
    )
    assert result["count"] == 1
    assert result["workouts"][0]["type"] == "Running"
```

- [ ] **Step 2: Run, verify failure**

```bash
pytest tests/test_tools.py -v
```

Expected: 2 NEW failures.

- [ ] **Step 3: Append get_workouts to tools.py**

Append to `tools.py`:

```python
async def get_workouts(
    pool: asyncpg.Pool,
    from_date: date,
    to_date: date,
    workout_type: str | None = None,
) -> dict:
    """All workouts whose start_ts falls within [from_date, to_date] inclusive."""
    query = (
        "SELECT start_ts, end_ts, type, duration_sec, "
        "active_energy_kcal, distance_m, avg_hr "
        "FROM health_workouts "
        "WHERE start_ts::date BETWEEN $1 AND $2"
    )
    params: list = [from_date, to_date]
    if workout_type is not None:
        query += " AND type = $3"
        params.append(workout_type)
    query += " ORDER BY start_ts"

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)

    return {
        "from": from_date.isoformat(),
        "to": to_date.isoformat(),
        "type_filter": workout_type,
        "count": len(rows),
        "workouts": [
            {
                "start_ts": r["start_ts"].isoformat(),
                "end_ts": r["end_ts"].isoformat(),
                "type": r["type"],
                "duration_sec": r["duration_sec"],
                "active_energy_kcal": r["active_energy_kcal"],
                "distance_m": r["distance_m"],
                "avg_hr": r["avg_hr"],
            }
            for r in rows
        ],
    }
```

- [ ] **Step 4: Run, verify pass**

```bash
pytest tests/test_tools.py -v
```

Expected: all 7 PASSED (5 prior + 2 new).

- [ ] **Step 5: Commit**

```bash
git add projekte/health-insights/mcp-server/tests/test_tools.py \
        projekte/health-insights/mcp-server/src/paperclip_health_mcp/tools.py
git commit -m "feat(health-mcp): get_workouts tool with optional type filter"
```

---

## Task 8: MCP Server Wiring

**Files:**
- Create: `projekte/health-insights/mcp-server/src/paperclip_health_mcp/server.py`

- [ ] **Step 1: Write server.py**

Create `projekte/health-insights/mcp-server/src/paperclip_health_mcp/server.py`:

```python
"""MCP server entry point. Registers the 3 tools and runs over stdio."""
import asyncio
import logging
from datetime import date

from mcp.server.fastmcp import FastMCP

from . import tools as t
from .db import get_pool, close_pool

log = logging.getLogger("paperclip_health_mcp")

mcp = FastMCP("paperclip-health")


@mcp.tool()
async def get_daily_summary(target_date: str) -> dict:
    """Aggregated values for all metrics on a given date.

    Args:
        target_date: ISO date string, e.g. "2026-05-08"
    """
    pool = await get_pool()
    return await t.get_daily_summary(pool, date.fromisoformat(target_date))


@mcp.tool()
async def get_metric_range(
    metric: str,
    from_date: str,
    to_date: str,
    agg: str = "daily",
) -> dict:
    """Time series for one metric over a date range, with summary stats and trend.

    Args:
        metric: canonical metric name, e.g. "hrv_sdnn", "step_count"
        from_date: ISO date string (inclusive)
        to_date: ISO date string (inclusive)
        agg: aggregation level, currently only "daily"
    """
    pool = await get_pool()
    return await t.get_metric_range(
        pool, metric,
        date.fromisoformat(from_date),
        date.fromisoformat(to_date),
        agg=agg,
    )


@mcp.tool()
async def get_workouts(
    from_date: str,
    to_date: str,
    workout_type: str | None = None,
) -> dict:
    """List workouts in a date range, optionally filtered by type.

    Args:
        from_date: ISO date string (inclusive)
        to_date: ISO date string (inclusive)
        workout_type: optional, e.g. "Running", "Cycling", "Strength"
    """
    pool = await get_pool()
    return await t.get_workouts(
        pool,
        date.fromisoformat(from_date),
        date.fromisoformat(to_date),
        workout_type=workout_type,
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    try:
        mcp.run()
    finally:
        asyncio.run(close_pool())


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Add a server-startup smoke test**

Append to `tests/test_tools.py`:

```python
def test_server_imports_and_registers_three_tools():
    """The server module imports and FastMCP has the 3 tools registered."""
    from paperclip_health_mcp.server import mcp
    tool_names = {tool.name for tool in mcp._tool_manager.list_tools()}
    assert tool_names == {"get_daily_summary", "get_metric_range", "get_workouts"}
```

Note: this reaches into FastMCP internals; if the API differs, fall back to running `mcp` and checking `list_tools` over stdio.

- [ ] **Step 3: Run all tests**

```bash
pytest -v
```

Expected: 13 passed total (2 db + 7 stats + 7 tools + 1 server).

- [ ] **Step 4: Manually run the server briefly**

```bash
export PAPERCLIP_HEALTH_DB_URL=postgresql://paperclip_health_mcp:<password>@localhost/health
timeout 2 paperclip-health-mcp || true
```

Expected: starts without error, exits on timeout. (No data flows because no client is connected — we just verify it starts.)

- [ ] **Step 5: Commit**

```bash
git add projekte/health-insights/mcp-server/src/paperclip_health_mcp/server.py \
        projekte/health-insights/mcp-server/tests/test_tools.py
git commit -m "feat(health-mcp): register 3 tools, add stdio entry point"
```

---

## Task 9: launchd Service

**Files:**
- Create: `projekte/health-insights/scripts/com.paperclip.health-mcp.plist`

> Note: MCP servers usually run on-demand by the client, not as a long-running service. Paperclip's adapter typically spawns the configured `command` per session. This launchd file is therefore **optional** and provided for the case where Walter wants a always-on warm pool. If Paperclip spawns the MCP server itself, skip this task.

- [ ] **Step 1: Decide if launchd is needed**

Check Paperclip's MCP integration model — does it spawn the server process or expect a long-running one? If it spawns: skip to Step 5 (commit a no-op marker file or skip entirely). If it expects a running server: continue.

- [ ] **Step 2: Write plist**

Create `projekte/health-insights/scripts/com.paperclip.health-mcp.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.paperclip.health-mcp</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/walterschoenenbroecher.de/SynologyDrive/2026/AI/Claude Code/Paperclip/projekte/health-insights/mcp-server/.venv/bin/paperclip-health-mcp</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PAPERCLIP_HEALTH_DB_URL</key>
        <string>postgresql://paperclip_health_mcp:CHANGE_ME@localhost:5432/health</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/Users/walterschoenenbroecher.de/Library/Logs/paperclip-health-mcp.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/walterschoenenbroecher.de/Library/Logs/paperclip-health-mcp.err</string>
</dict>
</plist>
```

- [ ] **Step 3: Install (manual, after replacing CHANGE_ME)**

```bash
cp projekte/health-insights/scripts/com.paperclip.health-mcp.plist \
   ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.paperclip.health-mcp.plist
```

- [ ] **Step 4: Verify**

```bash
launchctl list | grep paperclip.health-mcp
tail -f ~/Library/Logs/paperclip-health-mcp.log
```

Expected: process listed, logs show server startup.

- [ ] **Step 5: Commit**

```bash
git add projekte/health-insights/scripts/com.paperclip.health-mcp.plist
git commit -m "chore(health-mcp): launchd plist for always-on MCP server"
```

---

## Task 10: n8n Workflow — Read + Parse Daily Export

**Files:**
- Create: `projekte/health-insights/n8n/health-ingest V1.json` (exported from n8n UI at end of task series)
- Create: `projekte/health-insights/docs/metric-shapes.md`

**Note on n8n tasks (10–13):** The workflow is built incrementally in the n8n UI. Each task adds a node group, tested with a manual run before proceeding. JSON is exported only after all four tasks complete.

**Real-world iCloud path (verified 2026-05-10):**

```
~/Library/Mobile Documents/iCloud~com~ifunography~HealthExport/Documents/Daily Export Gesundheit/Gesundheitsdaten-YYYY-MM-DD.json
```

App is **Health Auto Export by Ifunography** (bundle `com.ifunography.HealthExport`). Files are 500-700 KB JSON each, one per day, written by the iPhone's Daily Export automation.

**Workouts:** the daily export does NOT include workouts by default. Workouts in `AutoSync/Workouts/*.hae` are LZFSE-compressed (n8n cannot decompress without a plugin). Two options:
- **Recommended:** in Health Auto Export iPhone app → Daily Export config → enable "Workouts" so they appear in the daily JSON as `data.workouts[]`
- **Fallback:** defer workouts to Phase 2 (the `get_workouts` MCP tool already handles empty results gracefully)

This plan assumes Walter enables daily-export workouts before Task 11 step 4. If not, skip the workouts branch.

- [ ] **Step 1: Write metric-shapes reference**

Create `projekte/health-insights/docs/metric-shapes.md`:

```markdown
# Health Auto Export — Metric Shapes Reference

Health Auto Export by Ifunography exports metrics already as canonical
snake_case names — no Apple Health identifier mapping is needed. The JSON
shape *of each sample* varies by metric type, though.

## Sample shapes (verified from real exports)

### Shape A: Simple quantity (27 of 29 metrics)

```json
{ "date": "2026-05-09 16:39:00 +0200", "qty": 9.218, "source": "Ultra 3" }
```

Metrics with this shape (non-exhaustive): `step_count`, `active_energy`,
`basal_energy_burned`, `flights_climbed`, `apple_exercise_time`,
`apple_stand_hour`, `apple_stand_time`, `heart_rate_variability`,
`resting_heart_rate`, `respiratory_rate`, `blood_oxygen_saturation`,
`blood_glucose`, `mindful_minutes`, `breathing_disturbances`,
`time_in_daylight`, `environmental_audio_exposure`, `headphone_audio_exposure`,
`walking_running_distance`, `walking_speed`, `walking_step_length`,
`walking_heart_rate_average`, `walking_asymmetry_percentage`,
`walking_double_support_percentage`, `stair_speed_up`, `stair_speed_down`,
`physical_effort`, `apple_sleeping_wrist_temperature`.

### Shape B: HR aggregate (1 metric: `heart_rate`)

```json
{ "date": "2026-05-09 00:07:00 +0200", "source": "Ultra 3",
  "Min": 68, "Max": 68, "Avg": 68 }
```

For `heart_rate` we store `Avg` as the canonical value. Daily aggregate's
`MIN(value)` / `MAX(value)` / `AVG(value)` over all 5-minute Avg samples
gives a useful daily summary.

### Shape C: Sleep session (1 metric: `sleep_analysis`)

```json
{ "date": "2026-05-09 00:00:00 +0200", "source": "Ultra 3",
  "totalSleep": 5.17, "core": 3.50, "deep": 0.27, "rem": 1.41,
  "awake": 0.44, "asleep": 0,
  "inBedStart": "...", "sleepStart": "...", "sleepEnd": "...", "inBedEnd": "...", "inBed": 0 }
```

Values are in **hours**. We explode each sleep sample into six canonical
metrics: `sleep_total_hours`, `sleep_core_hours`, `sleep_deep_hours`,
`sleep_rem_hours`, `sleep_awake_hours`, `sleep_in_bed_hours`.

## Date format

All `date` fields use `"YYYY-MM-DD HH:MM:SS +ZZZZ"` (with a space, not the
ISO-8601 `T`). Postgres `TIMESTAMPTZ` accepts this directly without
preprocessing — pass the raw string to a `$N::timestamptz` parameter.

## Unit normalization

Health Auto Export emits `active_energy` and `basal_energy_burned` in **kJ**,
not kcal. We rename to `active_energy_kcal` / `basal_energy_kcal` and
divide by 4.184 during normalization so canonical metrics are always in kcal.

## Aggregation choices

- **Cumulative (daily sum):** `step_count`, `active_energy_kcal`,
  `basal_energy_kcal`, `flights_climbed`, `apple_exercise_time`,
  `apple_stand_time`, `time_in_daylight`, `mindful_minutes`,
  `walking_running_distance`, `breathing_disturbances`,
  `sleep_*_hours`
- **Instant readings (daily avg + min + max):** `heart_rate`,
  `heart_rate_variability`, `respiratory_rate`, `blood_oxygen_saturation`,
  `walking_speed`, `walking_step_length`, `walking_heart_rate_average`,
  `apple_sleeping_wrist_temperature`, `environmental_audio_exposure`,
  `headphone_audio_exposure`, `physical_effort`, `stair_speed_up`,
  `stair_speed_down`, `walking_asymmetry_percentage`,
  `walking_double_support_percentage`, `blood_glucose`
- **Daily-frequency (avg only):** `resting_heart_rate`, `apple_stand_hour`
```

- [ ] **Step 2: Build the n8n workflow base in the UI**

In n8n UI, create new workflow named **`health-ingest V1`** with these nodes:

1. **Schedule Trigger** — every 30 min (Cron `*/30 * * * *`)
2. **Read Binary Files** node — file path glob:
   ```
   /Users/walterschoenenbroecher.de/Library/Mobile Documents/iCloud~com~ifunography~HealthExport/Documents/Daily Export Gesundheit/Gesundheitsdaten-*.json
   ```
3. **Function (JS)** node `Normalize Samples` — parse binary, walk `data.metrics`, emit one item per (metric, sample) tuple. Function body:

```javascript
const KCAL_PER_KJ = 1 / 4.184;

// Cumulative metrics that need daily-sum aggregation. Used downstream
// in Compute Daily Aggregate; just informational here for the reader.
// Most metrics fall into "instant reading" (avg/min/max). See metric-shapes.md.

function normalizeSimple(metricName, units, sample) {
  // Shape A: { date, qty, source }
  let metric = metricName;
  let value = sample.qty;
  let unit = units;
  // Energy: kJ → kcal, rename metric
  if (metric === 'active_energy' || metric === 'basal_energy_burned') {
    if (units === 'kJ') {
      value = value * KCAL_PER_KJ;
      unit = 'kcal';
    }
    metric = metric === 'active_energy' ? 'active_energy_kcal' : 'basal_energy_kcal';
  }
  return [{
    metric, source: sample.source || null,
    start_ts: sample.date,
    end_ts: null,
    value, unit,
    raw: sample,
  }];
}

function normalizeHeartRate(units, sample) {
  // Shape B: { date, Min, Max, Avg, source } — store Avg as the value.
  // (Daily Min/Max are derived from MIN/MAX(value) across 5-minute Avg samples.)
  return [{
    metric: 'heart_rate',
    source: sample.source || null,
    start_ts: sample.date,
    end_ts: null,
    value: sample.Avg,
    unit: units,
    raw: sample,
  }];
}

function normalizeSleep(sample) {
  // Shape C: explode into six per-phase metrics in hours.
  const fields = [
    ['sleep_total_hours',  sample.totalSleep],
    ['sleep_core_hours',   sample.core],
    ['sleep_deep_hours',   sample.deep],
    ['sleep_rem_hours',    sample.rem],
    ['sleep_awake_hours',  sample.awake],
    ['sleep_in_bed_hours', sample.inBed],
  ];
  return fields
    .filter(([, v]) => v != null)
    .map(([metric, value]) => ({
      metric,
      source: sample.source || null,
      start_ts: sample.date,
      end_ts: null,
      value,
      unit: 'h',
      raw: sample,
    }));
}

function normalizeMetric(m) {
  const samples = m.data ?? [];
  if (m.name === 'heart_rate') {
    return samples.flatMap(s => normalizeHeartRate(m.units, s));
  }
  if (m.name === 'sleep_analysis') {
    return samples.flatMap(s => normalizeSleep(s));
  }
  return samples.flatMap(s => normalizeSimple(m.name, m.units, s));
}

// n8n binary input → parse JSON
const out = [];
for (const item of $input.all()) {
  const binary = item.binary?.data;
  if (!binary) continue;
  const text = Buffer.from(binary.data, 'base64').toString('utf8');
  let parsed;
  try { parsed = JSON.parse(text); } catch (e) { continue; }
  const metrics = parsed?.data?.metrics ?? [];
  for (const m of metrics) {
    out.push(...normalizeMetric(m));
  }
}
return out.map(json => ({ json }));
```

- [ ] **Step 3: Run workflow with the existing exports**

Walter has files in the iCloud folder already (`Gesundheitsdaten-2026-05-08.json`, `Gesundheitsdaten-2026-05-09.json`). Click **Execute Workflow**.

Expected: `Normalize Samples` outputs ~5000-10000 items per file, each with `{metric, source, start_ts, value, unit, raw}` shape. No errors.

- [ ] **Step 4: Commit metric-shapes doc**

```bash
git add projekte/health-insights/docs/metric-shapes.md
git commit -m "docs(health): document Health Auto Export metric shapes"
```

(Workflow JSON commit happens in Task 13 after the workflow is complete.)

---

## Task 11: n8n Workflow — Postgres Insert with Dedup

**Files:**
- Modify: `health-ingest V1` workflow in n8n UI

- [ ] **Step 1: Add Postgres credentials in n8n**

Create a dedicated INGEST role with INSERT/UPDATE rights (kept separate from the read-only MCP role):

```bash
PGHOST=127.0.0.1 PGPORT=5432 psql -d health <<'SQL'
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'paperclip_health_ingest') THEN
    CREATE ROLE paperclip_health_ingest WITH LOGIN PASSWORD 'temp-change-me-walter';
  END IF;
END $$;
GRANT USAGE ON SCHEMA paperclip_health TO paperclip_health_ingest;
GRANT INSERT, SELECT, UPDATE ON ALL TABLES IN SCHEMA paperclip_health
  TO paperclip_health_ingest;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA paperclip_health
  TO paperclip_health_ingest;
ALTER DEFAULT PRIVILEGES IN SCHEMA paperclip_health
  GRANT INSERT, SELECT, UPDATE ON TABLES TO paperclip_health_ingest;
ALTER DEFAULT PRIVILEGES IN SCHEMA paperclip_health
  GRANT USAGE, SELECT ON SEQUENCES TO paperclip_health_ingest;
SQL
```

Then **change the password** to a real one:

```bash
PGHOST=127.0.0.1 PGPORT=5432 psql -d health -c "ALTER ROLE paperclip_health_ingest WITH PASSWORD '<real-password>';"
```

In n8n UI → **Credentials** → **+ Add credential** → **Postgres**:
- Host: `127.0.0.1` · Port: `5432` · Database: `health`
- User: `paperclip_health_ingest` · Password: `<real-password>`
- SSL: Disable (loopback)

- [ ] **Step 2: Add `Insert Samples` Postgres node**

After `Normalize Samples`, add a **Postgres** node `Insert Samples`:

- Operation: **Execute Query**
- Query:

```sql
INSERT INTO paperclip_health.health_samples
  (metric, source, start_ts, end_ts, value, unit, raw)
VALUES ($1, $2, $3::timestamptz, $4::timestamptz, $5, $6, $7::jsonb)
ON CONFLICT (metric, source, start_ts) DO NOTHING
RETURNING id;
```

Parameters (one expression per `$N`, in n8n's "Query Parameters" field):

```
={{ $json.metric }}
={{ $json.source }}
={{ $json.start_ts }}
={{ $json.end_ts }}
={{ $json.value }}
={{ $json.unit }}
={{ JSON.stringify($json.raw) }}
```

The `::timestamptz` casts handle Health Auto Export's `"YYYY-MM-DD HH:MM:SS +0200"` format directly — Postgres parses it natively.

- [ ] **Step 3: Test idempotency with the existing two daily files**

Run the workflow twice. After both runs:

```bash
PGHOST=127.0.0.1 PGPORT=5432 psql -d health -c "SELECT COUNT(*) FROM paperclip_health.health_samples;"
PGHOST=127.0.0.1 PGPORT=5432 psql -d health -c "SELECT metric, COUNT(*) FROM paperclip_health.health_samples GROUP BY metric ORDER BY 2 DESC LIMIT 10;"
```

Expected: same count after second run as after first; >20 distinct metrics with multi-thousand sample counts (heart_rate ~380/day, active_energy ~880/day, etc.).

- [ ] **Step 4 (optional, requires daily-export workouts enabled): Add `Insert Workouts` branch**

**Skip this step entirely if workouts aren't enabled in Health Auto Export's daily-export config.** The `get_workouts` MCP tool already handles empty results. Defer to Phase 2.

If workouts ARE enabled, the daily JSON contains `data.workouts[]` with this shape (as observed in `AutoSync/Workouts/*.hae` after decompression — the daily-export shape is documented as similar but Walter should run one export and check):

```javascript
// Verify the actual shape with:
//   jq '.data.workouts[0]' "<latest export>.json"
// before relying on these field names.
```

Add a parallel branch from the file-read node:

- **Function (JS)** `Extract Workouts`:

```javascript
const out = [];
for (const item of $input.all()) {
  const binary = item.binary?.data;
  if (!binary) continue;
  const text = Buffer.from(binary.data, 'base64').toString('utf8');
  const parsed = JSON.parse(text);
  for (const w of (parsed?.data?.workouts ?? [])) {
    out.push({ json: {
      start_ts: w.start ?? w.startDate,
      end_ts:   w.end   ?? w.endDate,
      type:     w.name  ?? 'Unknown',
      duration_sec: w.duration ? Math.round(w.duration * 60) : null,
      active_energy_kcal: w.activeEnergy ?? w.activeEnergyBurned?.qty ?? null,
      distance_m:  w.totalDistance ? w.totalDistance * 1000 : null,
      avg_hr:      w.avgHeartRate ?? null,
      raw: w,
    }});
  }
}
return out;
```

- **Postgres** node `Insert Workouts`:

```sql
INSERT INTO paperclip_health.health_workouts
  (start_ts, end_ts, type, duration_sec, active_energy_kcal, distance_m, avg_hr, raw)
VALUES ($1::timestamptz, $2::timestamptz, $3, $4, $5, $6, $7, $8::jsonb)
ON CONFLICT (start_ts, type) DO NOTHING
RETURNING id;
```

- [ ] **Step 5: Spot-check the data**

```bash
PGHOST=127.0.0.1 PGPORT=5432 psql -d health <<'SQL'
SELECT metric, COUNT(*) FROM paperclip_health.health_samples GROUP BY metric ORDER BY 2 DESC LIMIT 15;
SELECT MIN(start_ts), MAX(start_ts) FROM paperclip_health.health_samples;
SELECT type, COUNT(*) FROM paperclip_health.health_workouts GROUP BY type;
SQL
```

Expected: heart_rate, active_energy_kcal, basal_energy_kcal, step_count near the top with hundreds-to-thousands of samples; min/max timestamps cover 2026-05-08 and 2026-05-09; workouts table empty unless Step 4 was completed.

- [ ] **Step 6: No commit yet** (workflow JSON committed in Task 13)

---

## Task 12: n8n Workflow — Daily Aggregate

**Files:**
- Modify: `health-ingest V1` in n8n UI

The aggregation logic uses a **list of cumulative metrics** to decide whether to emit `sum` or `min/max/avg` per row in `health_daily`. The list is duplicated between this node and the Markdown formatter (Task 13) — keep them in sync, or move to a `health_metric_meta` table in a future iteration.

- [ ] **Step 1: Add `Compute Daily Aggregate` Postgres node**

After `Insert Samples` (and `Insert Workouts` if added in Task 11.4), use a **Merge** node (mode: "Combine" → "Multiplex") to converge the branches, then add a **Postgres** node `Compute Daily Aggregate`:

```sql
WITH cumulative AS (
  SELECT unnest(ARRAY[
    'step_count', 'active_energy_kcal', 'basal_energy_kcal',
    'flights_climbed', 'apple_exercise_time', 'apple_stand_time',
    'time_in_daylight', 'mindful_minutes', 'walking_running_distance',
    'breathing_disturbances',
    'sleep_total_hours', 'sleep_core_hours', 'sleep_deep_hours',
    'sleep_rem_hours', 'sleep_awake_hours', 'sleep_in_bed_hours'
  ])::varchar AS metric
)
INSERT INTO paperclip_health.health_daily (date, metric, min, max, avg, sum, count)
SELECT
  (start_ts AT TIME ZONE 'Europe/Berlin')::date AS date,
  s.metric,
  CASE WHEN s.metric IN (SELECT metric FROM cumulative) THEN NULL ELSE MIN(value) END,
  CASE WHEN s.metric IN (SELECT metric FROM cumulative) THEN NULL ELSE MAX(value) END,
  CASE WHEN s.metric IN (SELECT metric FROM cumulative) THEN NULL ELSE AVG(value) END,
  CASE WHEN s.metric IN (SELECT metric FROM cumulative) THEN SUM(value) ELSE NULL END,
  COUNT(*) AS count
FROM paperclip_health.health_samples s
WHERE start_ts >= NOW() - INTERVAL '8 days'   -- recompute last 8 days every run
GROUP BY (start_ts AT TIME ZONE 'Europe/Berlin')::date, s.metric
ON CONFLICT (date, metric) DO UPDATE SET
  min = EXCLUDED.min, max = EXCLUDED.max, avg = EXCLUDED.avg,
  sum = EXCLUDED.sum, count = EXCLUDED.count,
  computed_at = NOW();
```

`AT TIME ZONE 'Europe/Berlin'` ensures a sample at 23:30 CET on May 8 is bucketed to the May 8 date, not May 9 UTC. The pool's `TimeZone` setting from Task 1's fix would also handle this, but pinning it here makes the query independent of session settings.

The recompute window of 8 days is cheap (each metric × 7 days × ~few-hundred samples) and absorbs late-arriving samples from previous days.

- [ ] **Step 2: Add `Mark Ingest Run` Postgres node**

After the aggregate, add a **Postgres** node:

```sql
INSERT INTO paperclip_health.health_ingest_runs
  (date, status, files_processed, samples_written)
VALUES (CURRENT_DATE, 'ready', 1, 0)
ON CONFLICT (date) DO UPDATE SET
  status = 'ready',
  files_processed = paperclip_health.health_ingest_runs.files_processed + 1,
  finished_at = NOW();
```

(Phase 2's daily briefing routine polls this row to decide if the day's data is "ready".)

- [ ] **Step 3: Test**

Click **Execute Workflow**. Verify:

```bash
PGHOST=127.0.0.1 PGPORT=5432 psql -d health <<'SQL'
SELECT date, COUNT(*) AS metric_count
FROM paperclip_health.health_daily
GROUP BY date ORDER BY date DESC;

SELECT date, metric, min, max, avg, sum, count
FROM paperclip_health.health_daily
WHERE date = '2026-05-09' AND metric IN ('step_count', 'heart_rate', 'sleep_total_hours', 'hrv_sdnn');

SELECT * FROM paperclip_health.health_ingest_runs;
SQL
```

Expected: rows for 2026-05-08 and 2026-05-09 with ~25-30 metrics each; `step_count.sum` around your daily total; `heart_rate.avg/min/max` populated; `sleep_total_hours.sum` near the totalSleep value from the JSON; ingest_runs row for today with status=`ready`.

---

## Task 13: n8n Workflow — Daily Markdown Writer

**Files:**
- Modify: `health-ingest V1` in n8n UI
- Create (export): `projekte/health-insights/n8n/health-ingest V1.json`

- [ ] **Step 1: Add `Read Daily for Today` Postgres node**

After `Compute Daily Aggregate`:

```sql
SELECT date, metric, min, max, avg, sum, count
FROM paperclip_health.health_daily
WHERE date = CURRENT_DATE
ORDER BY metric;
```

- [ ] **Step 2: Add `Format Daily Markdown` Function (JS) node**

```javascript
const rows = $input.all().map(i => i.json);
if (rows.length === 0) return [{ json: { skip: true } }];

const date = rows[0].date;
const isoDate = typeof date === 'string' ? date.slice(0, 10) : date.toISOString().slice(0, 10);

const byMetric = Object.fromEntries(rows.map(r => [r.metric, r]));

const fmtH  = h => (h == null ? '—' : `${Math.floor(h)}h${String(Math.round((h - Math.floor(h)) * 60)).padStart(2, '0')}`);
const fmt1  = v => (v == null ? '—' : Math.round(v * 10) / 10);
const fmtI  = v => (v == null ? '—' : Math.round(v));
const get   = (m, k) => byMetric[m]?.[k] ?? null;

let md = `# Health Daily — ${isoDate}\n\n`;

md += `## Sleep\n`;
md += `- Total: ${fmtH(get('sleep_total_hours', 'sum'))}\n`;
md += `- Deep: ${fmtH(get('sleep_deep_hours', 'sum'))}, REM: ${fmtH(get('sleep_rem_hours', 'sum'))}, Core: ${fmtH(get('sleep_core_hours', 'sum'))}, Awake: ${fmtH(get('sleep_awake_hours', 'sum'))}\n\n`;

md += `## Recovery\n`;
md += `- HRV (avg): ${fmt1(get('heart_rate_variability', 'avg'))} ms\n`;
md += `- Resting HR: ${fmt1(get('resting_heart_rate', 'avg'))} bpm\n`;
md += `- Respiratory rate (avg): ${fmt1(get('respiratory_rate', 'avg'))} /min\n`;
md += `- Wrist temp (avg): ${fmt1(get('apple_sleeping_wrist_temperature', 'avg'))} °C\n\n`;

md += `## Activity\n`;
md += `- Steps: ${fmtI(get('step_count', 'sum'))}\n`;
md += `- Active energy: ${fmtI(get('active_energy_kcal', 'sum'))} kcal\n`;
md += `- Basal energy: ${fmtI(get('basal_energy_kcal', 'sum'))} kcal\n`;
md += `- Exercise time: ${fmtI(get('apple_exercise_time', 'sum'))} min\n`;
md += `- Stand time: ${fmtI(get('apple_stand_time', 'sum'))} min\n`;
md += `- Distance: ${fmt1(get('walking_running_distance', 'sum'))} km\n`;
md += `- Mindful: ${fmtI(get('mindful_minutes', 'sum'))} min\n\n`;

md += `## Vitals\n`;
md += `- Heart rate (avg / min / max): ${fmt1(get('heart_rate', 'avg'))} / ${fmt1(get('heart_rate', 'min'))} / ${fmt1(get('heart_rate', 'max'))} bpm\n`;
md += `- SpO₂ (avg / min): ${fmt1(get('blood_oxygen_saturation', 'avg'))} / ${fmt1(get('blood_oxygen_saturation', 'min'))} %\n`;
md += `- Daylight: ${fmtI(get('time_in_daylight', 'sum'))} min\n`;

return [{ json: { date: isoDate, content: md } }];
```

- [ ] **Step 3: Add `Write Daily Markdown` Write Binary File node**

- File path: `={{ "/Users/walterschoenenbroecher.de/SynologyDrive/2026/AI/Claude Code/Paperclip/projekte/health-insights/data/daily/" + $json.date + ".md" }}`
- Property name: `content`
- Skip if `$json.skip === true`

- [ ] **Step 4: Test end-to-end**

Run workflow. Verify:

```bash
ls projekte/health-insights/data/daily/
cat projekte/health-insights/data/daily/$(date +%F).md
```

Expected: today's `.md` file exists with all four sections populated.

- [ ] **Step 5: Export workflow JSON**

In n8n UI: workflow menu → Download / Export. Save to:

```
projekte/health-insights/n8n/health-ingest V1.json
```

- [ ] **Step 6: Sanity-check the exported JSON**

```bash
jq '.name, (.nodes | length)' "projekte/health-insights/n8n/health-ingest V1.json"
```

Expected: `"health-ingest V1"` and a node count of ~10.

- [ ] **Step 7: Commit**

```bash
git add "projekte/health-insights/n8n/health-ingest V1.json"
git commit -m "feat(health): n8n workflow health-ingest V1 (parse, dedup, aggregate, markdown)"
```

---

## Task 14: Health Auto Export Setup Doc

**Files:**
- Create: `projekte/health-insights/docs/health-auto-export-setup.md`

- [ ] **Step 1: Write the setup guide**

Create `projekte/health-insights/docs/health-auto-export-setup.md`:

```markdown
# Health Auto Export — iPhone Setup

## Install

1. App Store → install **Health Auto Export** by Lybrary (free version is sufficient)
2. On first launch, grant access to all Apple Health categories you want to track:
   Schlaf, Vital, Aktivität, Workouts, Atmung
3. Settings → enable iCloud Drive

## Configure Automatic Export

1. App → tab **Automations** → tap **+**
2. Settings:
   - **Output:** JSON
   - **Aggregate Data:** Hour for HR/HRV, Sample for sleep/workouts
   - **Sync Service:** iCloud Drive
   - **Folder:** create or choose `Health Auto Export`
   - **Frequency:** Daily, 06:00
   - **Date Range:** Last 2 days (overlaps to catch late-syncing watch data)
3. Save automation

## Verify

After saving the automation:

1. Run it manually once (long-press automation → Run Now)
2. On the Mac, check iCloud Drive:
   ```bash
   ls "/Users/walterschoenenbroecher.de/Library/Mobile Documents/iCloud~com~lybrary~HealthAutoExport/Documents/"
   ```
   You should see one or more `.json` files.
3. Inspect a file:
   ```bash
   jq '.data | keys' "<path-to-file>.json"
   ```
   Expected: array including `metrics` and possibly `workouts`.

## Troubleshooting

- **No files on Mac:** iCloud Drive may not be synced. System Settings → Apple ID → iCloud → iCloud Drive → check status. Force a sync via `brctl monitor com.apple.CloudDocs`.
- **iCloud bundle ID differs:** Health Auto Export uses `iCloud~com~lybrary~HealthAutoExport`. If your version uses a different ID, run `ls ~/Library/Mobile\ Documents/` to find it and update the n8n watcher path.
- **App crashes during export:** disable categories one at a time to isolate; usually a corrupted Health entry from a deleted device.
```

- [ ] **Step 2: Commit**

```bash
git add projekte/health-insights/docs/health-auto-export-setup.md
git commit -m "docs(health): add Health Auto Export iPhone setup guide"
```

---

## Task 15: Paperclip Company + Health Generalist Agent

**Files:**
- Create: `projekte/health-insights/company/health-generalist-system-prompt.md`

> Note: this task uses Walter's local Paperclip CLI / control plane. The exact CLI invocation may vary by Paperclip version — adapt the `paperclip` command syntax to what's installed.

- [ ] **Step 1: Write the system prompt**

Create `projekte/health-insights/company/health-generalist-system-prompt.md`:

```markdown
# Health Generalist — System Prompt

You are the **Health Generalist** for Walter's personal Apple Health data. You answer questions about his sleep, recovery, training, and vital metrics using a small set of MCP tools backed by a local Postgres database. All processing is local; no data leaves Walter's machine.

## What you can see

- `health_daily`: pre-aggregated values per (date, metric) — your primary data source
- `health_workouts`: structured workout records
- `health_samples`: raw samples (only via tool drill-down — usually unnecessary)

You access data only via these tools:

- `get_daily_summary(target_date)` — all metrics for one day
- `get_metric_range(metric, from_date, to_date, agg='daily')` — a single metric over a range, with summary stats and trend
- `get_workouts(from_date, to_date, workout_type?)` — workouts in a range

## How to answer

1. **Start small.** For "How was my sleep yesterday?" — one `get_daily_summary` call is enough.
2. **Use trends, not point values, for "how am I doing" questions.** A single bad night isn't a pattern.
3. **Compare to baselines.** If asked "is X normal?", fetch a 14- or 30-day range and compare today's value to median/stddev.
4. **Cite numbers.** When you state a value, include the unit and a short context ("HRV 48 ms, slightly below your 14-day median of 52").
5. **Acknowledge gaps.** If a metric is missing for the requested date, say so — don't guess.

## What you MUST NOT do

- **You are not a doctor.** Never give a diagnosis, never recommend medication, never speculate about specific medical conditions.
- For unusual or persistent values, recommend consulting a physician.
- Don't invent metrics you don't have. Available canonical names: `step_count`, `active_energy_kcal`, `heart_rate`, `resting_heart_rate`, `hrv_sdnn`, `respiratory_rate`, `spo2`, `body_temperature`, `sleep_asleep_seconds`, `sleep_in_bed_seconds`.

## Tone

German answers if asked in German, English if asked in English. Concise. Direct. Numerical. Not motivational.
```

- [ ] **Step 2: Create the company via Paperclip CLI**

```bash
paperclip company create --name "Health Insights" --description "Lokale Apple-Health-Analyse via Health Auto Export"
```

Capture the returned company ID — let's call it `<COMPANY_ID>`.

- [ ] **Step 3: Create the agent**

```bash
paperclip agent create \
  --company "<COMPANY_ID>" \
  --name "Health Generalist" \
  --role "generalist" \
  --instructions-file "projekte/health-insights/company/health-generalist-system-prompt.md"
```

If the CLI flag names differ in Walter's Paperclip version, use the equivalent. Capture `<AGENT_ID>`.

- [ ] **Step 4: Wire up MCP server to the agent**

Configure the Health Generalist agent to use `paperclip-health-mcp` as an MCP server. Method depends on Paperclip version — typically either:

- **Per-agent MCP config** (preferred): edit the agent's `.mcp.json` (or equivalent) to register:

  ```json
  {
    "mcpServers": {
      "paperclip-health": {
        "command": "/Users/walterschoenenbroecher.de/SynologyDrive/2026/AI/Claude Code/Paperclip/projekte/health-insights/mcp-server/.venv/bin/paperclip-health-mcp",
        "env": {
          "PAPERCLIP_HEALTH_DB_URL": "postgresql://paperclip_health_mcp:<password>@localhost:5432/health"
        }
      }
    }
  }
  ```

- **Global MCP config** (if per-agent isn't supported): same entry in the global Paperclip MCP config.

- [ ] **Step 5: Wire up local LLM (LM Studio)**

Configure the agent to use the LM Studio adapter (Walter has the `paperclip-adapter-lmstudio` already running). Choose a model with solid tool-use:

- Recommended: **Qwen 2.5 32B Instruct** (q4_K_M, fits comfortably in 32GB Mac RAM) or **Llama 3.1 70B Instruct** (q3 if hardware allows)
- Verify in LM Studio that the model is loaded and tool-use is enabled

- [ ] **Step 6: Smoke-test from Paperclip UI**

Open the Health Insights company in Paperclip UI. Open a chat with Health Generalist. Send:

> "Welche Metriken hast du für heute?"

Expected: agent calls `get_daily_summary` for today and lists the available metrics with values.

- [ ] **Step 7: Commit**

```bash
git add projekte/health-insights/company/health-generalist-system-prompt.md
git commit -m "feat(health): add Health Generalist system prompt and Paperclip wiring docs"
```

---

## Task 16: End-to-End Smoke Test

**Files:**
- Create: `projekte/health-insights/docs/smoke-test-checklist.md`

- [ ] **Step 1: Write the smoke-test checklist**

Create `projekte/health-insights/docs/smoke-test-checklist.md`:

```markdown
# Health Insights Phase 1 — Smoke Test Checklist

Run after a full setup or after any significant change. Tests the complete flow from iPhone export to agent response.

## Preconditions

- [ ] Health Auto Export ran on iPhone in the last 24h
- [ ] iCloud Drive sync to Mac is current
- [ ] Postgres `health` database is reachable
- [ ] MCP server runs: `psql -h localhost -U paperclip_health_mcp -d health -c "SELECT 1"` returns 1
- [ ] LM Studio model is loaded
- [ ] Paperclip Health Insights company exists with Health Generalist agent

## Pipeline tests

- [ ] **n8n manual run:** trigger `health-ingest V1` workflow manually, completes with no errors
- [ ] **Sample count grew:** `SELECT COUNT(*) FROM paperclip_health.health_samples` is higher than before the run
- [ ] **Daily aggregate refreshed:** `SELECT MAX(computed_at) FROM paperclip_health.health_daily` is recent (within last few minutes)
- [ ] **Markdown for today exists:** `ls projekte/health-insights/data/daily/$(date +%F).md` succeeds and the file contains all 4 sections
- [ ] **Ingest run marker:** `SELECT * FROM paperclip_health.health_ingest_runs WHERE date = CURRENT_DATE` shows `status = 'ready'`

## Agent tests (in Paperclip UI chat with Health Generalist)

For each prompt, verify the agent responds with concrete numbers (not hallucinated):

- [ ] **"Wie war mein Schlaf gestern?"** → calls `get_daily_summary`, reports asleep duration with unit
- [ ] **"Wie hat sich meine HRV in den letzten 14 Tagen entwickelt?"** → calls `get_metric_range` for `hrv_sdnn` over 14 days, reports stats and trend direction
- [ ] **"Welche Workouts hatte ich diese Woche?"** → calls `get_workouts` with this Monday → today, lists them
- [ ] **"Bin ich auffällig?"** → reasonably refuses speculation, points to physician

## Privacy verification

- [ ] **Network monitor (Little Snitch / equivalent):** During the agent test conversation, no outbound traffic to Anthropic/OpenAI/etc. — only localhost and LM Studio
- [ ] **`pg_stat_activity`:** during the smoke test, all connections to Postgres are from `paperclip_health_mcp` or `paperclip_health_ingest`, not from elsewhere
```

- [ ] **Step 2: Run the checklist manually**

Walter (or executor) goes through every checkbox and confirms. Any failure → file an issue, don't merge until all pass.

- [ ] **Step 3: Commit**

```bash
git add projekte/health-insights/docs/smoke-test-checklist.md
git commit -m "docs(health): add Phase 1 smoke test checklist"
```

---

## Final Tasks

- [ ] **Run full test suite one more time**

```bash
cd projekte/health-insights/mcp-server
source .venv/bin/activate
pytest -v
```

Expected: all tests pass.

- [ ] **Push branch**

```bash
git push -u origin feat/health-insights-company
```

- [ ] **Hand off to Phase 2**

Phase 2 plan covers: split generalist into CHO + 3 specialists, daily briefing routine, Obsidian integration. Use this Phase 1 codebase as foundation. Brainstorm Phase 2 separately when Phase 1 is in stable use for ≥1 week.

---

## Self-Review Notes

- All 7 spec sections (Datenpipeline, Schema, Company, MCP, Daily Briefing — partial as Phase 2, Q&A, Privacy) — Phase 1 covers Datenpipeline + Schema + MCP + Q&A + Privacy. Daily Briefing/specialists/Notifications deferred to Phase 2 by design.
- Type names are consistent throughout: `metric` (string), `target_date`/`from_date`/`to_date` (date), `agg` (string).
- All code blocks contain runnable code; no TBD/TODO placeholders.
- Test data is concrete (specific values, dates, expected results).
- n8n workflow described node-by-node since the artifact is a UI-built JSON, not hand-written code; final JSON committed in Task 13.
