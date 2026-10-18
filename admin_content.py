import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from filters import IsAdmin
import admin as admin_svc
import promos
import tasks
import timeutil
from money import fmt, parse_rupees
from notify import safe_send
from ui import SUB_STATUS, kb, show
from validators import clean_code, clean_text, esc, parse_int

log = logging.getLogger(__name__)
router = Router(name="admin_content")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

BACK = ("⬅️ Admin Panel", "ad:home")


class TaskFSM(StatesGroup):
    title = State()
    description = State()
    instructions = State()
    reward = State()


class PromoNew(StatesGroup):
    code = State()
    reward = State()
    max_uses = State()
    expiry = State()


class PromoEdit(StatesGroup):
    value = State()


# ======================= TASKS =======================
@router.callback_query(F.data == "ad:tasks")
async def tasks_list(cb: CallbackQuery, pool, state: FSMContext):
    await state.clear()
    await cb.answer()
    rows = await tasks.list_all(pool)
    buttons = [[(f"{'🟢' if r['is_active'] else '🔴'} #{r['id']} {r['title'][:25]} • {fmt(r['reward'])}",
                 f"ad:tv:{r['id']}")] for r in rows]
    buttons.append([("➕ Naya Task", "ad:tnew")])
    buttons.append([BACK])
    await show(cb, "📋 <b>Tasks</b>", kb(*buttons))


@router.callback_query(F.data.startswith("ad:tv:") | F.data.startswith("ad:tt:"))
async def task_view(cb: CallbackQuery, pool):
    parts = cb.data.split(":")
    tid = int(parts[2])
    if parts[1] == "tt":
        await tasks.toggle_active(pool, tid)
        await admin_svc.log_action(pool, cb.from_user.id, "task_toggle", f"id={tid}")
    await cb.answer()
    t = await tasks.get(pool, tid)
    if t is None:
        await show(cb, "❌ Task nahi mila.", kb([("⬅️ Tasks", "ad:tasks")]))
        return
    text = (f"📋 <b>#{t['id']} {esc(t['title'])}</b>\nReward: {fmt(t['reward'])}\n"
            f"Status: {'🟢 Active' if t['is_active'] else '🔴 Band'}\n\n{esc(t['description'])}\n\n"
            f"📝 {esc(t['instructions'])}")
    await show(cb, text, kb([("🔁 Active/Band", f"ad:tt:{tid}")], [("⬅️ Tasks", "ad:tasks")]))


@router.callback_query(F.data == "ad:tnew")
async def task_new(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.set_state(TaskFSM.title)
    await show(cb, "➕ Task ka <b>title</b> bhejo (max 60):", kb([("❌ Cancel", "ad:tasks")]))


@router.message(TaskFSM.title, F.text)
async def task_title(message: Message, state: FSMContext):
    v = clean_text(message.text, 60)
    if v is None:
        await message.answer("❌ Title 1-60 characters ka ho.")
        return
    await state.update_data(title=v)
    await state.set_state(TaskFSM.description)
    await message.answer("📄 Task ki <b>description</b> bhejo (max 500):")


@router.message(TaskFSM.description, F.text)
async def task_desc(message: Message, state: FSMContext):
    v = clean_text(message.text, 500)
    if v is None:
        await message.answer("❌ Description 1-500 characters ki ho.")
        return
    await state.update_data(description=v)
    await state.set_state(TaskFSM.instructions)
    await message.answer("📝 <b>Instructions</b> bhejo (proof kya dena hai, max 800):")


@router.message(TaskFSM.instructions, F.text)
async def task_instr(message: Message, state: FSMContext):
    v = clean_text(message.text, 800)
    if v is None:
        await message.answer("❌ Instructions 1-800 characters ke ho.")
        return
    await state.update_data(instructions=v)
    await state.set_state(TaskFSM.reward)
    await message.answer("💰 <b>Reward</b> (₹) bhejo:")


@router.message(TaskFSM.reward, F.text)
async def task_reward(message: Message, pool, state: FSMContext):
    paise = parse_rupees(message.text)
    if paise is None:
        await message.answer("❌ Galat amount. Number bhejo.")
        return
    d = await state.get_data()
    tid = await tasks.create(pool, d["title"], d["description"], d["instructions"], paise)
    await admin_svc.log_action(pool, message.from_user.id, "task_create", f"id={tid}")
    await state.clear()
    await message.answer(f"✅ Task #{tid} ban gaya aur users ko dikhega.",
                         reply_markup=kb([("⬅️ Tasks", "ad:tasks")], [BACK]))


# ======================= SUBMISSIONS =======================
@router.callback_query(F.data == "ad:subs")
async def subs_list(cb: CallbackQuery, pool):
    await cb.answer()
    rows = await tasks.pending_submissions(pool)
    buttons = [[(f"#{r['id']} • {r['title'][:20]} • {fmt(r['reward'])} • {r['user_id']}", f"ad:sv:{r['id']}")]
               for r in rows]
    buttons.append([BACK])
    await show(cb, "📝 <b>Pending submissions</b> (pehli 20)" + ("" if rows else "\n\nKoi nahi."), kb(*buttons))


@router.callback_query(F.data.startswith("ad:sv:"))
async def sub_view(cb: CallbackQuery, pool):
    await cb.answer()
    sid = int(cb.data.split(":")[2])
    s = await tasks.get_submission(pool, sid)
    if s is None:
        await show(cb, "❌ Submission nahi mili.", kb([BACK]))
        return
    text = (f"📝 <b>Submission #{s['id']}</b>\nTask: {esc(s['title'])}\nUser: <code>{s['user_id']}</code>\n"
            f"Reward: {fmt(s['reward'])}\nStatus: {SUB_STATUS[s['status']]}\n"
            f"Time: {timeutil.fmt_dt(s['created_at'])}\n\nProof text: {esc(s['proof_text'] or '(sirf photo)')}")
    rows = []
    if s["status"] == "pending":
        rows.append([("✅ Approve", f"ad:c:sa:{sid}"), ("❌ Reject", f"ad:c:sr:{sid}")])
    rows.append([("⬅️ List", "ad:subs"), BACK])
    markup = kb(*rows)
    if s["proof_file"]:
        await cb.bot.send_photo(cb.from_user.id, s["proof_file"], caption=text[:1000], reply_markup=markup)
    else:
        await show(cb, text, markup)


async def _review(cb, pool, approve):
    sid = int(cb.data.split(":")[3])
    try:
        s = await tasks.review(pool, sid, cb.from_user.id, approve)
    except tasks.InvalidState:
        await cb.answer("Ye submission pehle hi review ho chuki hai.", show_alert=True)
        return
    await admin_svc.log_action(pool, cb.from_user.id, "sub_approve" if approve else "sub_reject", f"id={sid}")
    await cb.answer("Ho gaya")
    if approve:
        msg = f"✅ Aapki task submission #{sid} <b>approve</b> ho gayi! {fmt(s['reward'])} balance mein add hue."
    else:
        msg = f"❌ Aapki task submission #{sid} <b>reject</b> ho gayi. Instructions dekhkar dobara try kar sakte ho."
    await safe_send(cb.bot, s["user_id"], msg)
    await show(cb, f"{'✅ Approved' if approve else '❌ Rejected'}: submission #{sid}",
               kb([("📝 Aur Submissions", "ad:subs")], [BACK]))


@router.callback_query(F.data.startswith("ad:y:sa:"))
async def sub_approve(cb: CallbackQuery, pool):
    await _review(cb, pool, True)


@router.callback_query(F.data.startswith("ad:y:sr:"))
async def sub_reject(cb: CallbackQuery, pool):
    await _review(cb, pool, False)


# ======================= PROMOS =======================
def _promo_text(p):
    limit = "Unlimited" if p["max_uses"] is None else f"{p['used_count']}/{p['max_uses']}"
    if p["max_uses"] is None:
        limit += f" (use hue: {p['used_count']})"
    return (f"🎟 <b>{esc(p['code'])}</b>\nReward: {fmt(p['reward'])}\nUses: {limit}\n"
            f"Expiry: {timeutil.fmt_dt(p['expires_at']) if p['expires_at'] else 'Kabhi nahi'}\n"
            f"Status: {'🟢 Active' if p['is_active'] else '🔴 Band'}")


@router.callback_query(F.data == "ad:promos")
async def promos_list(cb: CallbackQuery, pool, state: FSMContext):
    await state.clear()
    await cb.answer()
    rows = await promos.list_all(pool)
    buttons = [[(f"{'🟢' if r['is_active'] else '🔴'} {r['code']} • {fmt(r['reward'])}", f"ad:pv:{r['code']}")]
               for r in rows]
    buttons.append([("➕ Naya Promo", "ad:pnew")])
    buttons.append([BACK])
    await show(cb, "🎟 <b>Promo Codes</b>", kb(*buttons))


async def _promo_view(cb, pool, code):
    p = await promos.get(pool, code)
    if p is None:
        await show(cb, "❌ Promo nahi mila.", kb([("⬅️ Promos", "ad:promos")]))
        return
    await show(cb, _promo_text(p), kb(
        [("🔁 Active/Band", f"ad:pt:{code}")],
        [("✏️ Reward", f"ad:pe:r:{code}"), ("✏️ Limit", f"ad:pe:m:{code}")],
        [("✏️ Expiry", f"ad:pe:x:{code}"), ("🗑 Delete", f"ad:c:pdel:{code}")],
        [("⬅️ Promos", "ad:promos")]))


@router.callback_query(F.data.startswith("ad:pv:"))
async def promo_view(cb: CallbackQuery, pool):
    await cb.answer()
    await _promo_view(cb, pool, cb.data.split(":", 2)[2])


@router.callback_query(F.data.startswith("ad:pt:"))
async def promo_toggle(cb: CallbackQuery, pool):
    code = cb.data.split(":", 2)[2]
    p = await promos.get(pool, code)
    if p is None:
        await cb.answer("Promo nahi mila", show_alert=True)
        return
    await promos.set_active(pool, code, not p["is_active"])
    await admin_svc.log_action(pool, cb.from_user.id, "promo_toggle", code)
    await cb.answer("Ho gaya")
    await _promo_view(cb, pool, code)


@router.callback_query(F.data.startswith("ad:y:pdel:"))
async def promo_delete(cb: CallbackQuery, pool):
    code = cb.data.split(":", 3)[3]
    ok = await promos.delete(pool, code)
    await admin_svc.log_action(pool, cb.from_user.id, "promo_delete", code)
    await cb.answer("Delete ho gaya" if ok else "Promo nahi mila", show_alert=not ok)
    await show(cb, "🗑 Promo delete ho gaya." if ok else "❌ Promo nahi mila.",
               kb([("⬅️ Promos", "ad:promos")], [BACK]))


@router.callback_query(F.data == "ad:pnew")
async def promo_new(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.set_state(PromoNew.code)
    await show(cb, "➕ Promo <b>code</b> bhejo (3-32, letters/numbers/-/_):", kb([("❌ Cancel", "ad:promos")]))


@router.message(PromoNew.code, F.text)
async def pn_code(message: Message, state: FSMContext):
    code = clean_code(message.text)
    if code is None:
        await message.answer("❌ Code 3-32 characters (A-Z, 0-9, -, _) ka ho.")
        return
    await state.update_data(code=code)
    await state.set_state(PromoNew.reward)
    await message.answer("💰 Reward (₹) bhejo:")


@router.message(PromoNew.reward, F.text)
async def pn_reward(message: Message, state: FSMContext):
    paise = parse_rupees(message.text)
    if paise is None:
        await message.answer("❌ Galat amount.")
        return
    await state.update_data(reward=paise)
    await state.set_state(PromoNew.max_uses)
    await message.answer("🔢 Total kitni baar use ho sakta hai? (0 = unlimited)")


@router.message(PromoNew.max_uses, F.text)
async def pn_max(message: Message, state: FSMContext):
    n = parse_int(message.text, 0, 10_000_000)
    if n is None:
        await message.answer("❌ Sirf number bhejo (0 = unlimited).")
        return
    await state.update_data(max_uses=n or None)
    await state.set_state(PromoNew.expiry)
    await message.answer("📅 Expiry date bhejo (YYYY-MM-DD, IST) ya 0 (kabhi expire nahi):")


@router.message(PromoNew.expiry, F.text)
async def pn_expiry(message: Message, pool, state: FSMContext):
    try:
        exp = timeutil.parse_expiry(message.text)
    except ValueError as e:
        await message.answer(f"❌ {e}")
        return
    d = await state.get_data()
    try:
        await promos.create(pool, d["code"], d["reward"], d["max_uses"], exp)
    except promos.CodeExists:
        await state.clear()
        await message.answer("❌ Ye code pehle se maujood hai.", reply_markup=kb([("⬅️ Promos", "ad:promos")]))
        return
    await admin_svc.log_action(pool, message.from_user.id, "promo_create", d["code"])
    await state.clear()
    await message.answer(f"✅ Promo <b>{esc(d['code'])}</b> ban gaya.",
                         reply_markup=kb([("🎟 Promos", "ad:promos")], [BACK]))


@router.callback_query(F.data.startswith("ad:pe:"))
async def promo_edit_start(cb: CallbackQuery, state: FSMContext):
    _, _, field, code = cb.data.split(":", 3)
    prompts = {"r": ("reward", "💰 Naya reward (₹) bhejo:"),
               "m": ("max_uses", "🔢 Naya total use limit bhejo (0 = unlimited):"),
               "x": ("expires_at", "📅 Nayi expiry (YYYY-MM-DD, IST) ya 0:")}
    if field not in prompts:
        await cb.answer("Unknown", show_alert=True)
        return
    await cb.answer()
    await state.set_state(PromoEdit.value)
    await state.update_data(code=code, field=prompts[field][0])
    await show(cb, prompts[field][1], kb([("❌ Cancel", f"ad:pv:{code}")]))


@router.message(PromoEdit.value, F.text)
async def promo_edit_save(message: Message, pool, state: FSMContext):
    d = await state.get_data()
    field, code = d.get("field"), d.get("code")
    if field == "reward":
        value = parse_rupees(message.text)
    elif field == "max_uses":
        n = parse_int(message.text, 0, 10_000_000)
        value = None if n is None else (n or None)
        if n is None:
            value = False
    else:
        try:
            value = timeutil.parse_expiry(message.text)
        except ValueError as e:
            await message.answer(f"❌ {e}")
            return
    if value is False or (field == "reward" and value is None):
        await message.answer("❌ Galat value. Dobara bhejo.")
        return
    ok = await promos.update_field(pool, code, field, value)
    await admin_svc.log_action(pool, message.from_user.id, "promo_edit", f"{code} {field}")
    await state.clear()
    await message.answer("✅ Update ho gaya." if ok else "❌ Promo nahi mila.",
                         reply_markup=kb([("⬅️ Promo", f"ad:pv:{code}")], [BACK]))
