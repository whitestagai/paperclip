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
        server_settings={
            "search_path": "paperclip_health",
            "TimeZone": "Europe/Berlin",
        },
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
