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
