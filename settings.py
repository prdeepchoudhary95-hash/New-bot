"""Admin-configurable settings. Paise integer mein store hote hain. `db` Pool ya Connection dono ho sakta hai."""

DEFAULTS = {
    "referral_reward": "200",       # Rs 2
    "daily_bonus": "100",           # Rs 1
    "min_withdrawal": "5000",       # Rs 50
    "withdrawals_enabled": "1",
    "daily_bonus_enabled": "1",
    "leaderboard_enabled": "1",
    "force_join": "1",
}


async def ensure_defaults(db):
    for k, v in DEFAULTS.items():
        await db.execute(
            "INSERT INTO settings(key, value) VALUES($1, $2) ON CONFLICT (key) DO NOTHING", k, v
        )


async def get_int(db, key):
    v = await db.fetchval("SELECT value FROM settings WHERE key=$1", key)
    return int(v if v is not None else DEFAULTS[key])


async def get_bool(db, key):
    v = await db.fetchval("SELECT value FROM settings WHERE key=$1", key)
    return (v if v is not None else DEFAULTS[key]) == "1"


async def set_value(db, key, value):
    if key not in DEFAULTS:
        raise KeyError(key)
    await db.execute(
        "INSERT INTO settings(key, value) VALUES($1, $2) "
        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
        key,
        str(value),
    )


async def toggle(db, key):
    new = not await get_bool(db, key)
    await set_value(db, key, "1" if new else "0")
    return new
