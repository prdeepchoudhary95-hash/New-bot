import ledger
import settings


async def reward_if_due(pool, user_id):
    """Referrer ko reward deta hai (sirf EK baar). Return (referrer_id, reward) ya None.

    Safe tareeka: referred user ki row lock hoti hai, referrals.referred_id PRIMARY KEY hai, aur
    ledger mein (referrer, 'referral', referred_id) UNIQUE hai -- triple protection.
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            u = await conn.fetchrow(
                "SELECT tg_id, referrer_id, referral_rewarded FROM users WHERE tg_id=$1 FOR UPDATE",
                user_id,
            )
            if u is None or u["referral_rewarded"]:
                return None
            await conn.execute("UPDATE users SET referral_rewarded=TRUE WHERE tg_id=$1", user_id)
            ref = u["referrer_id"]
            if ref is None or ref == user_id:
                return None
            r = await conn.fetchrow("SELECT is_banned FROM users WHERE tg_id=$1", ref)
            if r is None or r["is_banned"]:
                return None
            reward = await settings.get_int(conn, "referral_reward")
            ins = await conn.fetchval(
                "INSERT INTO referrals(referred_id, referrer_id, reward) VALUES($1,$2,$3) "
                "ON CONFLICT (referred_id) DO NOTHING RETURNING referred_id",
                user_id, ref, reward,
            )
            if ins is None:
                return None
            if reward > 0:
                await ledger.apply(conn, ref, reward, "referral", ref_key=str(user_id),
                                   note="Referral reward")
            return ref, reward
