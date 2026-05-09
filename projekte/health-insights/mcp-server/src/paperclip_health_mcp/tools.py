"""Tool implementations. All tools take an asyncpg.Pool plus typed args
and return JSON-serializable dicts."""
from datetime import date
import asyncpg

from .stats import summary_stats, linear_trend


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
