"""MCP server entry point. Registers the 3 tools and runs over stdio."""
import logging
from datetime import date

from mcp.server.fastmcp import FastMCP

from . import tools as t
from .db import get_pool

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
    # Pool cleanup is intentionally omitted: mcp.run() owns its own anyio
    # event loop, and asyncpg connections are bound to that loop. Calling
    # asyncio.run(close_pool()) afterwards would create a new loop and
    # cross-loop-close the pool. The OS reclaims connections cleanly when
    # the stdio process exits, so this is safe in practice.
    mcp.run()


if __name__ == "__main__":
    main()
