import asyncpg

import ledger
import settings
from ledger import InsufficientFunds  # noqa: F401  (handlers import karte hain)


class WithdrawalsDisabled(Exception):
    pass


class BelowMinimum(Exception):
    def __init__(self, minimum):
        self.minimum = minimum


class ActiveExists(Exception):
    pass


class InvalidState(Exception):
    pass


async def create(pool, uid, amount, upi_id):
    """Request banata hai aur balance TURANT hold (debit) karta hai. Return withdrawal id."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            if not await settings.get_bool(conn, "withdrawals_enabled"):
                raise WithdrawalsDisabled()
            minimum = await settings.get_int(conn, "min_withdrawal")
            if amount < minimum:
                raise BelowMinimum(minimum)
            try:
                wid = await conn.fetchval(
                    "INSERT INTO withdrawals(user_id, amount, upi_id) VALUES($1,$2,$3) RETURNING id",
                    uid, amount, upi_id,
                )
            except asyncpg.UniqueViolationError:
                raise ActiveExists()
            await ledger.apply(conn, uid, -amount, "withdraw_hold", ref_key=f"w{wid}",
                               note=f"Withdrawal #{wid} hold")
            return wid


async def _move(conn, wid, admin_id, from_statuses, to_status):
    row = await conn.fetchrow(
        "UPDATE withdrawals SET status=$2, updated_at=now(), "
        "reviewed_by=COALESCE(reviewed_by,$3), "
        "paid_by=CASE WHEN $2='paid' THEN $3 ELSE paid_by END "
        "WHERE id=$1 AND status = ANY($4::text[]) RETURNING *",
        wid, to_status, admin_id, list(from_statuses),
    )
    if row is None:
        raise InvalidState()
    return row


async def approve(pool, wid, admin_id):
    async with pool.acquire() as conn:
        async with conn.transaction():
            return await _move(conn, wid, admin_id, ["pending"], "approved")


async def reject(pool, wid, admin_id):
    """Reject + refund, ek hi transaction mein. Status guard + ledger unique key = refund sirf ek baar."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await _move(conn, wid, admin_id, ["pending", "approved"], "rejected")
            await ledger.apply(conn, row["user_id"], row["amount"], "withdraw_refund",
                               ref_key=f"w{wid}", note=f"Withdrawal #{wid} refund")
            return row


async def mark_paid(pool, wid, admin_id):
    """Sirf 'approved' request ko Paid kiya ja sakta hai (admin ne manually pay karne ke baad)."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await _move(conn, wid, admin_id, ["approved"], "paid")
            await conn.execute(
                "UPDATE users SET total_withdrawn = total_withdrawn + $2 WHERE tg_id=$1",
                row["user_id"], row["amount"],
            )
            return row


async def get(db, wid):
    return await db.fetchrow("SELECT * FROM withdrawals WHERE id=$1", wid)


async def list_by_status(db, status, limit=20):
    return await db.fetch(
        "SELECT * FROM withdrawals WHERE status=$1 ORDER BY id ASC LIMIT $2", status, limit)


async def user_history(db, uid, limit=10):
    return await db.fetch(
        "SELECT id, amount, status, created_at FROM withdrawals WHERE user_id=$1 "
        "ORDER BY id DESC LIMIT $2", uid, limit)
