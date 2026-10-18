import csv
import io

from services import ledger
from utils.money import fmt


async def log_action(db, admin_id, action, detail=""):
    await db.execute(
        "INSERT INTO admin_log(admin_id, action, detail) VALUES($1,$2,$3)",
        admin_id, action, detail[:500])


async def dashboard(db):
    return await db.fetchrow(
        "SELECT "
        "(SELECT count(*) FROM users) AS total_users, "
        "(SELECT count(*) FROM users WHERE last_active_at >= now() - interval '7 days') AS active_users, "
        "(SELECT count(*) FROM referrals) AS total_referrals, "
        "(SELECT COALESCE(sum(amount),0) FROM transactions "
        "   WHERE kind IN ('referral','daily_bonus','task_reward','promo')) AS rewards, "
        "(SELECT count(*) FROM withdrawals WHERE status='pending') AS pending_n, "
        "(SELECT COALESCE(sum(amount),0) FROM withdrawals WHERE status='pending') AS pending_amt, "
        "(SELECT count(*) FROM withdrawals WHERE status='approved') AS approved_n, "
        "(SELECT COALESCE(sum(amount),0) FROM withdrawals WHERE status='approved') AS approved_amt, "
        "(SELECT COALESCE(sum(amount),0) FROM withdrawals WHERE status='paid') AS paid_amt, "
        "(SELECT count(*) FROM task_submissions WHERE status='pending') AS pending_subs")


async def user_card(db, uid):
    return await db.fetchrow(
        "SELECT u.*, "
        "(SELECT count(*) FROM referrals WHERE referrer_id=u.tg_id) AS referral_count, "
        "(SELECT count(*) FROM withdrawals WHERE user_id=u.tg_id AND status IN ('pending','approved')) "
        "  AS active_withdrawals "
        "FROM users u WHERE u.tg_id=$1", uid)


async def adjust_balance(pool, admin_id, uid, amount, reason):
    """amount signed paise: + credit, - debit. InsufficientFunds / LookupError raise ho sakte hain."""
    kind = "admin_credit" if amount > 0 else "admin_debit"
    async with pool.acquire() as conn:
        async with conn.transaction():
            new_bal = await ledger.apply(conn, uid, amount, kind,
                                         note=f"Admin {admin_id}: {reason}"[:200])
            await log_action(conn, admin_id, kind, f"user={uid} amount={amount} reason={reason}")
            return new_bal


async def set_ban(db, admin_id, uid, banned):
    res = await db.execute("UPDATE users SET is_banned=$2 WHERE tg_id=$1", uid, banned)
    ok = res.endswith("1")
    if ok:
        await log_action(db, admin_id, "ban" if banned else "unban", f"user={uid}")
    return ok


async def recent_transactions(db, limit=20, uid=None):
    if uid is None:
        return await db.fetch(
            "SELECT id, user_id, amount, kind, created_at FROM transactions ORDER BY id DESC LIMIT $1",
            limit)
    return await db.fetch(
        "SELECT id, user_id, amount, kind, created_at FROM transactions WHERE user_id=$1 "
        "ORDER BY id DESC LIMIT $2", uid, limit)


async def broadcast_targets(db):
    rows = await db.fetch("SELECT tg_id FROM users WHERE NOT is_banned ORDER BY tg_id")
    return [r["tg_id"] for r in rows]


def _safe(v):
    """CSV injection se bachav: =,+,-,@ se shuru hone wale text ke aage ' laga do."""
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def _to_csv(header, rows):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    for r in rows:
        w.writerow([_safe(x) for x in r])
    return buf.getvalue().encode("utf-8-sig")


async def export_users_csv(db):
    rows = await db.fetch(
        "SELECT tg_id, username, first_name, registered_at, referrer_id, balance, total_earned, "
        "total_withdrawn, is_banned FROM users ORDER BY tg_id")
    return _to_csv(
        ["tg_id", "username", "first_name", "registered_at_utc", "referrer_id", "balance_rs",
         "total_earned_rs", "total_withdrawn_rs", "is_banned"],
        [(r["tg_id"], r["username"], r["first_name"], r["registered_at"].isoformat(),
          r["referrer_id"], fmt(r["balance"]), fmt(r["total_earned"]), fmt(r["total_withdrawn"]),
          r["is_banned"]) for r in rows])


async def export_transactions_csv(db):
    rows = await db.fetch(
        "SELECT id, user_id, amount, kind, ref_key, note, balance_after, created_at "
        "FROM transactions ORDER BY id")
    return _to_csv(
        ["id", "user_id", "amount_rs", "kind", "ref_key", "note", "balance_after_rs", "created_at_utc"],
        [(r["id"], r["user_id"], fmt(r["amount"]), r["kind"], r["ref_key"], r["note"],
          fmt(r["balance_after"]), r["created_at"].isoformat()) for r in rows])


async def export_withdrawals_csv(db):
    rows = await db.fetch(
        "SELECT id, user_id, amount, upi_id, status, created_at, updated_at FROM withdrawals ORDER BY id")
    return _to_csv(
        ["id", "user_id", "amount_rs", "upi_id", "status", "created_at_utc", "updated_at_utc"],
        [(r["id"], r["user_id"], fmt(r["amount"]), r["upi_id"], r["status"],
          r["created_at"].isoformat(), r["updated_at"].isoformat()) for r in rows])
