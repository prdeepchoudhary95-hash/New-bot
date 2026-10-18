import timeutil


async def top(db, weekly, limit=10):
    since = timeutil.week_start_utc() if weekly else None
    return await db.fetch(
        "SELECT u.first_name, count(*) AS cnt FROM referrals r "
        "JOIN users u ON u.tg_id = r.referrer_id "
        "WHERE NOT u.is_banned AND ($1::timestamptz IS NULL OR r.created_at >= $1) "
        "GROUP BY r.referrer_id, u.first_name ORDER BY cnt DESC, min(r.created_at) ASC LIMIT $2",
        since, limit)
