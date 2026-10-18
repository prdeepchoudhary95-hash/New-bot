import logging

import asyncpg

from db.schema import MIGRATIONS

log = logging.getLogger(__name__)
_LOCK_ID = 727272  # advisory lock, taaki do instances ek saath migrate na karein


async def create_pool(dsn):
    return await asyncpg.create_pool(dsn, min_size=1, max_size=5, command_timeout=30)


async def init_schema(pool):
    async with pool.acquire() as conn:
        await conn.execute("SELECT pg_advisory_lock($1)", _LOCK_ID)
        try:
            await conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY, "
                "applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
            )
            applied = {r["version"] for r in await conn.fetch("SELECT version FROM schema_version")}
            for version, sql in MIGRATIONS:
                if version in applied:
                    continue
                async with conn.transaction():
                    await conn.execute(sql)
                    await conn.execute("INSERT INTO schema_version(version) VALUES($1)", version)
                log.info("Migration %s apply hua", version)
        finally:
            await conn.execute("SELECT pg_advisory_unlock($1)", _LOCK_ID)
    from services import settings

    await settings.ensure_defaults(pool)
