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
