import asyncpg

import ledger


class TaskUnavailable(Exception):
    pass


class AlreadySubmitted(Exception):
    pass


class InvalidState(Exception):
    pass


async def create(db, title, description, instructions, reward):
    return await db.fetchval(
        "INSERT INTO tasks(title, description, instructions, reward) VALUES($1,$2,$3,$4) RETURNING id",
        title, description, instructions, reward)


async def get(db, tid):
    return await db.fetchrow("SELECT * FROM tasks WHERE id=$1", tid)


async def list_all(db, limit=30):
    return await db.fetch("SELECT * FROM tasks ORDER BY id DESC LIMIT $1", limit)


async def list_available(db, uid):
    return await db.fetch(
        "SELECT t.* FROM tasks t WHERE t.is_active AND NOT EXISTS ("
        " SELECT 1 FROM task_submissions s WHERE s.task_id=t.id AND s.user_id=$1 "
        " AND s.status IN ('pending','approved')) ORDER BY t.id DESC LIMIT 30", uid)


async def toggle_active(db, tid):
    return await db.fetchval(
        "UPDATE tasks SET is_active = NOT is_active WHERE id=$1 RETURNING is_active", tid)


async def submit(pool, tid, uid, text, file_id):
    async with pool.acquire() as conn:
        async with conn.transaction():
            task = await conn.fetchrow("SELECT * FROM tasks WHERE id=$1 AND is_active", tid)
            if task is None:
                raise TaskUnavailable()
            try:
                return await conn.fetchval(
                    "INSERT INTO task_submissions(task_id, user_id, reward, proof_text, proof_file) "
                    "VALUES($1,$2,$3,$4,$5) RETURNING id",
                    tid, uid, task["reward"], text, file_id)
            except asyncpg.UniqueViolationError:
                raise AlreadySubmitted()


async def review(pool, sub_id, admin_id, approve):
    """Approve par reward EK hi baar milta hai (status guard + ledger unique key)."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "UPDATE task_submissions SET status=$2, reviewed_at=now(), reviewed_by=$3 "
                "WHERE id=$1 AND status='pending' RETURNING *",
                sub_id, "approved" if approve else "rejected", admin_id)
            if row is None:
                raise InvalidState()
            if approve:
                await ledger.apply(conn, row["user_id"], row["reward"], "task_reward",
                                   ref_key=f"sub{sub_id}", note=f"Task #{row['task_id']} reward")
            return row


async def get_submission(db, sub_id):
    return await db.fetchrow(
        "SELECT s.*, t.title FROM task_submissions s JOIN tasks t ON t.id=s.task_id WHERE s.id=$1",
        sub_id)


async def pending_submissions(db, limit=20):
    return await db.fetch(
        "SELECT s.id, s.user_id, s.reward, t.title FROM task_submissions s "
        "JOIN tasks t ON t.id=s.task_id WHERE s.status='pending' ORDER BY s.id ASC LIMIT $1", limit)


async def user_history(db, uid, limit=10):
    return await db.fetch(
        "SELECT s.id, s.status, s.reward, s.created_at, t.title FROM task_submissions s "
        "JOIN tasks t ON t.id=s.task_id WHERE s.user_id=$1 ORDER BY s.id DESC LIMIT $2", uid, limit)
