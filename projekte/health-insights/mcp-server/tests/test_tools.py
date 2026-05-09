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
