"""Balance badalne ka EKLAUTA raasta. Har credit/debit transactions table mein likhta hai."""

EARNING_KINDS = {"referral", "daily_bonus", "task_reward", "promo", "admin_credit"}


class InsufficientFunds(Exception):
    pass


async def apply(conn, user_id, amount, kind, ref_key=None, note=None):
    """Transaction ke ANDAR call karo (async with conn.transaction()).

    Return: naya balance, ya None agar (user_id, kind, ref_key) pehle se maujood hai (duplicate).
    Raise: InsufficientFunds agar balance negative ho jata; LookupError agar user nahi mila.
    """
    if not isinstance(amount, int) or amount == 0:
        raise ValueError("amount non-zero integer paise hona chahiye")
    row = await conn.fetchrow("SELECT balance FROM users WHERE tg_id=$1 FOR UPDATE", user_id)
    if row is None:
        raise LookupError(f"user {user_id} nahi mila")
    new_balance = row["balance"] + amount
    if new_balance < 0:
        raise InsufficientFunds()
    inserted = await conn.fetchval(
        "INSERT INTO transactions(user_id, amount, kind, ref_key, note, balance_after) "
        "VALUES($1,$2,$3,$4,$5,$6) ON CONFLICT (user_id, kind, ref_key) DO NOTHING RETURNING id",
        user_id, amount, kind, ref_key, note, new_balance,
    )
    if inserted is None:
        return None
    earned = amount if (kind in EARNING_KINDS and amount > 0) else 0
    await conn.execute(
        "UPDATE users SET balance=$2, total_earned=total_earned+$3 WHERE tg_id=$1",
        user_id, new_balance, earned,
    )
    return new_balance
