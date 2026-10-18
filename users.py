async def get(db, uid):
    return await db.fetchrow("SELECT * FROM users WHERE tg_id=$1", uid)


async def register(pool, uid, username, first_name, ref_id=None):
    """Return (user_row, created). Referrer sirf naye user par set hota hai, baad mein kabhi nahi badalta."""
    username = (username or "")[:64] or None
    first_name = (first_name or "")[:64]
    async with pool.acquire() as conn:
        valid_ref = None
        if ref_id and ref_id != uid:
            valid_ref = await conn.fetchval("SELECT tg_id FROM users WHERE tg_id=$1", ref_id)
        created = await conn.fetchval(
            "INSERT INTO users(tg_id, username, first_name, referrer_id) VALUES($1,$2,$3,$4) "
            "ON CONFLICT (tg_id) DO NOTHING RETURNING tg_id",
            uid, username, first_name, valid_ref,
        )
        if created is None:
            await conn.execute(
                "UPDATE users SET username=$2, first_name=$3, last_active_at=now() WHERE tg_id=$1",
                uid, username, first_name,
            )
        row = await conn.fetchrow("SELECT * FROM users WHERE tg_id=$1", uid)
    return row, created is not None


async def mark_joined(db, uid):
    await db.execute("UPDATE users SET joined_verified=TRUE WHERE tg_id=$1", uid)


async def stats(db, uid):
    return await db.fetchrow(
        "SELECT (SELECT count(*) FROM referrals WHERE referrer_id=$1) AS referrals, "
        "(SELECT count(*) FROM daily_bonuses WHERE user_id=$1) AS bonuses",
        uid,
    )


async def recent_transactions(db, uid, limit=10):
    return await db.fetch(
        "SELECT amount, kind, note, created_at FROM transactions WHERE user_id=$1 "
        "ORDER BY id DESC LIMIT $2", uid, limit)


async def recent_bonuses(db, uid, limit=10):
    return await db.fetch(
        "SELECT bonus_date, amount, created_at FROM daily_bonuses WHERE user_id=$1 "
        "ORDER BY bonus_date DESC LIMIT $2", uid, limit)
