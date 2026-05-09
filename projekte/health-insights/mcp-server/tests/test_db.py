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
