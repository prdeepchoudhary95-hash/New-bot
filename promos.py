import asyncpg

from services import ledger
from utils import timeutil


class CodeExists(Exception):
    pass


class PromoNotFound(Exception):
    pass


class PromoInactive(Exception):
    pass


class PromoExpired(Exception):
    pass


class PromoLimitReached(Exception):
    pass


class PromoAlreadyUsed(Exception):
    pass


async def create(db, code, reward, max_uses, expires_at):
    try:
        await db.execute(
            "INSERT INTO promo_codes(code, reward, max_uses, expires_at) VALUES($1,$2,$3,$4)",
            code, reward, max_uses, expires_at)
    except asyncpg.UniqueViolationError:
        raise CodeExists()


_UPDATES = {
    "reward": "UPDATE promo_codes SET reward=$2 WHERE code=$1",
    "max_uses": "UPDATE promo_codes SET max_uses=$2 WHERE code=$1",
    "expires_at": "UPDATE promo_codes SET expires_at=$2 WHERE code=$1",
}


async def update_field(db, code, field, value):
    sql = _UPDATES[field]  # whitelist: unknown field KeyError deta hai
    res = await db.execute(sql, code, value)
    return res.endswith("1")


async def set_active(db, code, active):
    res = await db.execute("UPDATE promo_codes SET is_active=$2 WHERE code=$1", code, active)
    return res.endswith("1")


async def delete(db, code):
    res = await db.execute("DELETE FROM promo_codes WHERE code=$1", code)
    return res.endswith("1")


async def get(db, code):
    return await db.fetchrow("SELECT * FROM promo_codes WHERE code=$1", code)


async def list_all(db, limit=30):
    return await db.fetch("SELECT * FROM promo_codes ORDER BY created_at DESC LIMIT $1", limit)


async def redeem(pool, uid, code):
    """Return reward (paise). Row lock se global limit race-safe hai; PK se ek user ek baar."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            p = await conn.fetchrow("SELECT * FROM promo_codes WHERE code=$1 FOR UPDATE", code)
            if p is None:
                raise PromoNotFound()
            if not p["is_active"]:
                raise PromoInactive()
            if p["expires_at"] is not None and p["expires_at"] <= timeutil.now_utc():
                raise PromoExpired()
            if p["max_uses"] is not None and p["used_count"] >= p["max_uses"]:
                raise PromoLimitReached()
            ins = await conn.fetchval(
                "INSERT INTO promo_redemptions(code, user_id) VALUES($1,$2) "
                "ON CONFLICT (code, user_id) DO NOTHING RETURNING user_id", code, uid)
            if ins is None:
                raise PromoAlreadyUsed()
            await conn.execute(
                "UPDATE promo_codes SET used_count = used_count + 1 WHERE code=$1", code)
            await ledger.apply(conn, uid, p["reward"], "promo", ref_key=code, note=f"Promo {code}")
            return p["reward"]
