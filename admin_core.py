import asyncio
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from handlers.filters import IsAdmin
from services import admin as admin_svc
from services import ledger, settings
from utils import timeutil
from utils.money import fmt, parse_rupees
from utils.notify import safe_send
from utils.ui import KIND_LABEL, kb, show
from utils.validators import clean_text, esc, parse_int

log = logging.getLogger(__name__)
router = Router(name="admin_core")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

BG_TASKS = set()  # broadcast tasks (shutdown par cancel hote hain)

BACK = ("⬅️ Admin Panel", "ad:home")

CONFIRM_TEXT = {
    "ban": "🚫 Is user ko BAN karna hai?",
    "unban": "♻️ Is user ko UNBAN karna hai?",
    "wdr": "❌ Withdrawal REJECT karni hai? (balance wapas refund hoga)",
    "wdp": "💸 Kya aapne user ko manually payment kar di hai? 'Paid' mark karna hai?",
    "sa": "✅ Task submission APPROVE karni hai? (reward credit hoga)",
    "sr": "❌ Task submission REJECT karni hai?",
    "pdel": "🗑 Promo code DELETE karna hai?",
}

SETTING_LABEL = {
    "referral_reward": "Referral reward",
    "daily_bonus": "Daily bonus",
    "min_withdrawal": "Minimum withdrawal",
}
TOGGLE_LABEL = {
    "withdrawals_enabled": "Withdrawals",
    "daily_bonus_enabled": "Daily bonus",
    "leaderboard_enabled": "Leaderboard",
    "force_join": "Force-join channel",
}


class AdminFSM(StatesGroup):
    set_value = State()
    find_user = State()
    bal_amount = State()
    bal_reason = State()
    bal_confirm = State()
    bc_text = State()
    bc_confirm = State()


def home_kb():
    return kb(
        [("📊 Stats", "ad:stats"), ("💸 Withdrawals", "ad:wd:pending")],
        [("👤 User Search", "ad:user"), ("🧾 Recent Txns", "ad:tx")],
        [("⚙️ Settings", "ad:set"), ("📋 Tasks", "ad:tasks")],
        [("📝 Submissions", "ad:subs"), ("🎟 Promo Codes", "ad:promos")],
        [("📣 Broadcast", "ad:bc"), ("📁 CSV Export", "ad:csv")],
        [("🏠 User Menu", "menu:home")])


@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("🛠 <b>Admin Panel</b>", reply_markup=home_kb())


@router.callback_query(F.data == "ad:home")
async def cb_home(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.answer()
    await show(cb, "🛠 <b>Admin Panel</b>", home_kb())


# ---------- generic confirmation screen ----------
@router.callback_query(F.data.startswith("ad:c:"))
async def ask_confirm(cb: CallbackQuery):
    _, _, action, arg = cb.data.split(":", 3)
    if action not in CONFIRM_TEXT:
        await cb.answer("Unknown action", show_alert=True)
        return
    await cb.answer()
    await show(cb, f"⚠️ <b>Confirm</b>\n\n{CONFIRM_TEXT[action]}\nTarget: <code>{esc(arg)}</code>",
               kb([("✅ Haan, Karo", f"ad:y:{action}:{arg}"), ("❌ Nahi", "ad:home")]))


# ---------- stats ----------
@router.callback_query(F.data == "ad:stats")
async def stats(cb: CallbackQuery, pool):
    await cb.answer()
    d = await admin_svc.dashboard(pool)
    text = (
        "📊 <b>Bot Stats</b>\n\n"
        f"👥 Total users: <b>{d['total_users']}</b>\n"
        f"🟢 Active users (7 din): <b>{d['active_users']}</b>\n"
        f"🤝 Total referrals: <b>{d['total_referrals']}</b>\n"
        f"🎁 Total rewards distributed: <b>{fmt(d['rewards'])}</b>\n"
        "   (referral + daily + task + promo; admin credit shamil nahi)\n\n"
        f"⏳ Pending withdrawals: <b>{d['pending_n']}</b> ({fmt(d['pending_amt'])})\n"
        f"✅ Approved, payment baaki: <b>{d['approved_n']}</b> ({fmt(d['approved_amt'])})\n"
        f"💸 Total paid out: <b>{fmt(d['paid_amt'])}</b>\n"
        f"📝 Pending task submissions: <b>{d['pending_subs']}</b>"
    )
    await show(cb, text, kb([BACK]))


# ---------- settings ----------
async def settings_view(cb, pool):
    s = {k: await settings.get_int(pool, k) for k in SETTING_LABEL}
    t = {k: await settings.get_bool(pool, k) for k in TOGGLE_LABEL}
    text = (
        "⚙️ <b>Settings</b>\n\n"
        f"👥 Referral reward: <b>{fmt(s['referral_reward'])}</b>\n"
        f"🎁 Daily bonus: <b>{fmt(s['daily_bonus'])}</b>\n"
        f"💸 Min withdrawal: <b>{fmt(s['min_withdrawal'])}</b>"
    )
    rows = [[(f"✏️ {SETTING_LABEL[k]}", f"ad:st:{k}")] for k in SETTING_LABEL]
    for k, label in TOGGLE_LABEL.items():
        rows.append([(f"{'🟢 ON' if t[k] else '🔴 OFF'} • {label}", f"ad:tg:{k}")])
    rows.append([BACK])
    await show(cb, text, kb(*rows))


@router.callback_query(F.data == "ad:set")
async def set_menu(cb: CallbackQuery, pool, state: FSMContext):
    await state.clear()
    await cb.answer()
    await settings_view(cb, pool)


@router.callback_query(F.data.startswith("ad:tg:"))
async def do_toggle(cb: CallbackQuery, pool):
    key = cb.data.split(":", 2)[2]
    if key not in TOGGLE_LABEL:
        await cb.answer("Unknown", show_alert=True)
        return
    new = await settings.toggle(pool, key)
    await admin_svc.log_action(pool, cb.from_user.id, "toggle", f"{key}={new}")
    await cb.answer(f"{TOGGLE_LABEL[key]}: {'ON' if new else 'OFF'}")
    await settings_view(cb, pool)


@router.callback_query(F.data.startswith("ad:st:"))
async def ask_setting(cb: CallbackQuery, state: FSMContext):
    key = cb.data.split(":", 2)[2]
    if key not in SETTING_LABEL:
        await cb.answer("Unknown", show_alert=True)
        return
    await cb.answer()
    await state.set_state(AdminFSM.set_value)
    await state.update_data(key=key)
    extra = " (0 bhi allowed hai)" if key == "referral_reward" else ""
    await show(cb, f"✏️ <b>{SETTING_LABEL[key]}</b> ka naya amount ₹ mein bhejo{extra}:",
               kb([("❌ Cancel", "ad:set")]))


@router.message(AdminFSM.set_value, F.text)
async def save_setting(message: Message, pool, state: FSMContext):
    data = await state.get_data()
    key = data.get("key")
    paise = parse_rupees(message.text, allow_zero=(key == "referral_reward"))
    if key not in SETTING_LABEL or paise is None:
        await message.answer("❌ Galat amount. Number bhejo (jaise 2 ya 2.50).", reply_markup=kb([("❌ Cancel", "ad:set")]))
        return
    await settings.set_value(pool, key, paise)
    await admin_svc.log_action(pool, message.from_user.id, "setting", f"{key}={paise}")
    await state.clear()
    await message.answer(f"✅ {SETTING_LABEL[key]} ab {fmt(paise)} hai.", reply_markup=kb([("⚙️ Settings", "ad:set")], [BACK]))


# ---------- user search / balance / ban ----------
async def user_view(target, pool, uid):
    u = await admin_svc.user_card(pool, uid)
    if u is None:
        await show(target, "❌ Is ID ka user nahi mila.", kb([BACK]))
        return
    uname = f"@{esc(u['username'])}" if u["username"] else "-"
    text = (
        f"👤 <b>User</b> <code>{u['tg_id']}</code>\n"
        f"Naam: {esc(u['first_name'])} | {uname}\n"
        f"Joined: {timeutil.fmt_dt(u['registered_at'])}\n"
        f"Referrer: {u['referrer_id'] or '-'} | Referrals: {u['referral_count']}\n"
        f"Status: {'🚫 BANNED' if u['is_banned'] else '🟢 Active'}\n\n"
        f"💰 Balance: <b>{fmt(u['balance'])}</b>\n"
        f"📈 Earned: {fmt(u['total_earned'])}\n"
        f"💸 Withdrawn (Paid): {fmt(u['total_withdrawn'])}\n"
        f"⏳ Active withdrawals: {u['active_withdrawals']}"
    )
    ban_btn = ("♻️ Unban", f"ad:c:unban:{uid}") if u["is_banned"] else ("🚫 Ban", f"ad:c:ban:{uid}")
    await show(target, text, kb(
        [("➕ Balance Add", f"ad:bal:+:{uid}"), ("➖ Balance Deduct", f"ad:bal:-:{uid}")],
        [ban_btn, ("🧾 Txns", f"ad:utx:{uid}")],
        [BACK]))


@router.callback_query(F.data == "ad:user")
async def ask_user(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.set_state(AdminFSM.find_user)
    await show(cb, "👤 User ki numeric Telegram ID bhejo:", kb([BACK]))


@router.message(AdminFSM.find_user, F.text)
async def got_user(message: Message, pool, state: FSMContext):
    uid = parse_int(message.text, 1)
    if uid is None:
        await message.answer("❌ Sirf numeric ID bhejo.", reply_markup=kb([BACK]))
        return
    await state.clear()
    await user_view(message, pool, uid)


@router.callback_query(F.data.startswith("ad:uv:"))
async def view_user_cb(cb: CallbackQuery, pool):
    await cb.answer()
    await user_view(cb, pool, int(cb.data.split(":")[2]))


@router.callback_query(F.data.startswith("ad:utx:"))
async def user_txns(cb: CallbackQuery, pool):
    await cb.answer()
    uid = int(cb.data.split(":")[2])
    rows = await admin_svc.recent_transactions(pool, 15, uid)
    lines = [f"#{r['id']} {'+' if r['amount'] > 0 else '-'}{fmt(abs(r['amount']))} "
             f"{KIND_LABEL.get(r['kind'], r['kind'])} {timeutil.fmt_dt(r['created_at'])}" for r in rows]
    await show(cb, f"🧾 <b>User {uid} ke last transactions</b>\n\n" + ("\n".join(lines) or "Koi nahi."),
               kb([("⬅️ User", f"ad:uv:{uid}")], [BACK]))


@router.callback_query(F.data.startswith("ad:y:ban:") | F.data.startswith("ad:y:unban:"))
async def do_ban(cb: CallbackQuery, pool, config):
    _, _, action, uid_s = cb.data.split(":")
    uid = int(uid_s)
    if uid in config.admin_ids:
        await cb.answer("Admin ko ban nahi kiya ja sakta.", show_alert=True)
        return
    banned = action == "ban"
    ok = await admin_svc.set_ban(pool, cb.from_user.id, uid, banned)
    await cb.answer("Ho gaya" if ok else "User nahi mila", show_alert=not ok)
    if ok:
        await user_view(cb, pool, uid)


@router.callback_query(F.data.startswith("ad:bal:"))
async def ask_balance(cb: CallbackQuery, state: FSMContext):
    _, _, sign, uid_s = cb.data.split(":")
    if sign not in ("+", "-"):
        await cb.answer("Unknown", show_alert=True)
        return
    await cb.answer()
    await state.set_state(AdminFSM.bal_amount)
    await state.update_data(uid=int(uid_s), sign=sign)
    word = "ADD" if sign == "+" else "DEDUCT"
    await show(cb, f"💰 User <code>{uid_s}</code> ka balance {word} karna hai.\nAmount (₹) bhejo:",
               kb([BACK]))


@router.message(AdminFSM.bal_amount, F.text)
async def bal_amount(message: Message, state: FSMContext):
    paise = parse_rupees(message.text)
    if paise is None:
        await message.answer("❌ Galat amount.", reply_markup=kb([BACK]))
        return
    await state.update_data(paise=paise)
    await state.set_state(AdminFSM.bal_reason)
    await message.answer("📝 Reason likho (short, max 100 characters):", reply_markup=kb([BACK]))


@router.message(AdminFSM.bal_reason, F.text)
async def bal_reason(message: Message, state: FSMContext):
    reason = clean_text(message.text, 100)
    if reason is None:
        await message.answer("❌ Reason 1-100 characters ka hona chahiye.", reply_markup=kb([BACK]))
        return
    d = await state.get_data()
    await state.update_data(reason=reason)
    await state.set_state(AdminFSM.bal_confirm)
    word = "ADD" if d["sign"] == "+" else "DEDUCT"
    await message.answer(
        f"⚠️ <b>Confirm</b>\nUser: <code>{d['uid']}</code>\n{word}: <b>{fmt(d['paise'])}</b>\nReason: {esc(reason)}",
        reply_markup=kb([("✅ Confirm", "ad:bal_ok"), ("❌ Cancel", "ad:home")]))


@router.callback_query(AdminFSM.bal_confirm, F.data == "ad:bal_ok")
async def bal_ok(cb: CallbackQuery, pool, state: FSMContext):
    d = await state.get_data()
    await state.clear()
    try:
        amount = d["paise"] if d["sign"] == "+" else -d["paise"]
        new_bal = await admin_svc.adjust_balance(pool, cb.from_user.id, d["uid"], amount, d["reason"])
    except ledger.InsufficientFunds:
        await cb.answer("❌ User ka balance kam hai, deduct nahi ho sakta.", show_alert=True)
        return
    except LookupError:
        await cb.answer("❌ User nahi mila.", show_alert=True)
        return
    except KeyError:
        await cb.answer("Session expire ho gaya.", show_alert=True)
        return
    await cb.answer("Ho gaya")
    await safe_send(cb.bot, d["uid"],
                    f"ℹ️ Admin ne aapke balance mein {'+' if amount > 0 else '-'}{fmt(abs(amount))} "
                    f"adjust kiya.\nNaya balance: {fmt(new_bal)}")
    await show(cb, f"✅ Done. Naya balance: <b>{fmt(new_bal)}</b>", kb([("⬅️ User", f"ad:uv:{d['uid']}")], [BACK]))


# ---------- recent transactions ----------
@router.callback_query(F.data == "ad:tx")
async def recent_tx(cb: CallbackQuery, pool):
    await cb.answer()
    rows = await admin_svc.recent_transactions(pool, 20)
    lines = [f"#{r['id']} <code>{r['user_id']}</code> {'+' if r['amount'] > 0 else '-'}{fmt(abs(r['amount']))} "
             f"{KIND_LABEL.get(r['kind'], r['kind'])}" for r in rows]
    await show(cb, "🧾 <b>Recent 20 Transactions</b>\n\n" + ("\n".join(lines) or "Koi nahi."), kb([BACK]))


# ---------- CSV export ----------
@router.callback_query(F.data == "ad:csv")
async def csv_menu(cb: CallbackQuery):
    await cb.answer()
    await show(cb, "📁 Kaunsi report chahiye?", kb(
        [("👥 Users", "ad:csv:u"), ("🧾 Transactions", "ad:csv:t")],
        [("💸 Withdrawals", "ad:csv:w")], [BACK]))


@router.callback_query(F.data.startswith("ad:csv:"))
async def csv_send(cb: CallbackQuery, pool):
    kind = cb.data.split(":")[2]
    makers = {"u": ("users.csv", admin_svc.export_users_csv),
              "t": ("transactions.csv", admin_svc.export_transactions_csv),
              "w": ("withdrawals.csv", admin_svc.export_withdrawals_csv)}
    if kind not in makers:
        await cb.answer("Unknown", show_alert=True)
        return
    await cb.answer("Report ban rahi hai...")
    name, fn = makers[kind]
    data = await fn(pool)
    await admin_svc.log_action(pool, cb.from_user.id, "export", name)
    await cb.bot.send_document(cb.from_user.id, BufferedInputFile(data, filename=name))


# ---------- broadcast ----------
@router.callback_query(F.data == "ad:bc")
async def bc_start(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.set_state(AdminFSM.bc_text)
    await show(cb, "📣 Broadcast ka message bhejo (plain text, max 1000 characters):", kb([BACK]))


@router.message(AdminFSM.bc_text, F.text)
async def bc_text(message: Message, state: FSMContext):
    text = clean_text(message.text, 1000)
    if text is None:
        await message.answer("❌ Message 1-1000 characters ka hona chahiye.", reply_markup=kb([BACK]))
        return
    await state.update_data(text=text)
    await state.set_state(AdminFSM.bc_confirm)
    await message.answer("⚠️ <b>Ye message SAB users ko jayega:</b>\n\n" + esc(text),
                         reply_markup=kb([("✅ Bhejo", "ad:bc_ok"), ("❌ Cancel", "ad:home")]))


async def run_broadcast(bot, pool, admin_id, text):
    ids = await admin_svc.broadcast_targets(pool)
    sent = failed = 0
    for uid in ids:
        if await safe_send(bot, uid, text, parse_mode=None):
            sent += 1
        else:
            failed += 1
        await asyncio.sleep(0.05)  # Telegram limit (~30 msg/sec) se neeche
    await safe_send(bot, admin_id, f"📣 Broadcast khatam.\n✅ Gaye: {sent}\n⚠️ Nahi gaye (blocked etc.): {failed}")


@router.callback_query(AdminFSM.bc_confirm, F.data == "ad:bc_ok")
async def bc_ok(cb: CallbackQuery, pool, state: FSMContext):
    d = await state.get_data()
    await state.clear()
    text = d.get("text")
    if not text:
        await cb.answer("Session expire ho gaya.", show_alert=True)
        return
    await cb.answer("Broadcast shuru")
    await admin_svc.log_action(pool, cb.from_user.id, "broadcast", text[:200])
    task = asyncio.create_task(run_broadcast(cb.bot, pool, cb.from_user.id, text))
    BG_TASKS.add(task)
    task.add_done_callback(BG_TASKS.discard)
    await show(cb, "📣 Broadcast background mein shuru ho gaya. Khatam hone par aapko report milegi.", kb([BACK]))
