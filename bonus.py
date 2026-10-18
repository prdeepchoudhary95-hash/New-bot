from services import ledger, settings
from utils import timeutil


class BonusDisabled(Exception):
    pass


class AlreadyClaimed(Exception):
    pass


async def claim(pool, uid):
    """Aaj (IST) ka daily bonus. Return amount (paise)."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            if not await settings.get_bool(conn, "daily_bonus_enabled"):
                raise BonusDisabled()
            amount = await settings.get_int(conn, "daily_bonus")
            today = timeutil.today_ist()
            row = await conn.fetchval(
                "INSERT INTO daily_bonuses(user_id, bonus_date, amount) VALUES($1,$2,$3) "
                "ON CONFLICT (user_id, bonus_date) DO NOTHING RETURNING id",
                uid, today, amount,
            )
            if row is None:
                raise AlreadyClaimed()
            await ledger.apply(conn, uid, amount, "daily_bonus", ref_key=today.isoformat(),
                               note="Daily bonus")
            return amount
