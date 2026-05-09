import pytest
from datetime import date
from paperclip_health_mcp.tools import get_daily_summary, get_metric_range


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
