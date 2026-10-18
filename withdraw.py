import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import settings
import withdrawals
from money import fmt, parse_rupees
from notify import notify_admins
from ui import HOME_BTN, kb, show
from validators import clean_upi, esc

log = logging.getLogger(__name__)
router = Router(name="withdraw")
CANCEL = kb([("❌ Cancel", "menu:home")])


class WD(StatesGroup):
    amount = State()
    upi = State()
    confirm = State()


@router.callback_query(F.data == "menu:withdraw")
async def start(cb: CallbackQuery, user, pool, state: FSMContext):
    await state.clear()
    if not await settings.get_bool(pool, "withdrawals_enabled"):
        await cb.answer("Withdrawals abhi band hain.", show_alert=True)
        return
    minimum = await settings.get_int(pool, "min_withdrawal")
    active = await pool.fetchval(
        "SELECT id FROM withdrawals WHERE user_id=$1 AND status IN ('pending','approved')",
        user["tg_id"])
    if active:
        await cb.answer(f"Aapki request #{active} abhi process mein hai. Pehle wo khatam hone do.",
                        show_alert=True)
        return
    if user["balance"] < minimum:
        await cb.answer(f"Minimum withdrawal {fmt(minimum)} hai. Aapka balance {fmt(user['balance'])} hai.",
                        show_alert=True)
        return
    await cb.answer()
    await state.set_state(WD.amount)
    await show(cb, f"💸 <b>Withdrawal</b>\n\nBalance: {fmt(user['balance'])}\nMinimum: {fmt(minimum)}\n\n"
                   "Kitna withdraw karna hai? Amount (₹) bhejo:", CANCEL)


@router.message(WD.amount, F.text)
async def got_amount(message: Message, user, pool, state: FSMContext):
    amount = parse_rupees(message.text)
    if amount is None:
        await message.answer("❌ Amount galat hai. Sirf number bhejo (jaise 50 ya 75.50).", reply_markup=CANCEL)
        return
    minimum = await settings.get_int(pool, "min_withdrawal")
    fresh = await pool.fetchval("SELECT balance FROM users WHERE tg_id=$1", user["tg_id"])
    if amount < minimum:
        await message.answer(f"❌ Minimum {fmt(minimum)} hai.", reply_markup=CANCEL)
        return
    if amount > fresh:
        await message.answer(f"❌ Aapka balance sirf {fmt(fresh)} hai.", reply_markup=CANCEL)
        return
    await state.update_data(amount=amount)
    await state.set_state(WD.upi)
    await message.answer("Ab apna <b>UPI ID</b> bhejo (jaise name@upi):", reply_markup=CANCEL)


@router.message(WD.upi, F.text)
async def got_upi(message: Message, state: FSMContext):
    upi = clean_upi(message.text)
    if upi is None:
        await message.answer("❌ UPI ID galat lag raha hai. Dobara bhejo (jaise name@upi).", reply_markup=CANCEL)
        return
    data = await state.get_data()
    await state.update_data(upi=upi)
    await state.set_state(WD.confirm)
    await message.answer(
        f"Confirm karo:\n\n💸 Amount: <b>{fmt(data['amount'])}</b>\n🏦 UPI: <code>{esc(upi)}</code>\n\n"
        "Amount abhi aapke balance se hold ho jayega. Reject hone par wapas mil jayega.",
        reply_markup=kb([("✅ Confirm", "wd:ok")], [("❌ Cancel", "menu:home")]))


@router.callback_query(WD.confirm, F.data == "wd:ok")
async def confirm(cb: CallbackQuery, user, pool, state: FSMContext, config):
    data = await state.get_data()
    amount, upi = data.get("amount"), data.get("upi")
    await state.clear()
    if not amount or not upi:
        await cb.answer("Session expire ho gaya. Dobara try karo.", show_alert=True)
        return
    try:
        wid = await withdrawals.create(pool, user["tg_id"], amount, upi)
    except withdrawals.WithdrawalsDisabled:
        await cb.answer("Withdrawals abhi band hain.", show_alert=True)
        return
    except withdrawals.BelowMinimum as e:
        await cb.answer(f"Minimum {fmt(e.minimum)} hai.", show_alert=True)
        return
    except withdrawals.ActiveExists:
        await cb.answer("Aapki ek request pehle se process mein hai.", show_alert=True)
        return
    except withdrawals.InsufficientFunds:
        await cb.answer("Balance kam hai.", show_alert=True)
        return
    await cb.answer()
    await show(cb, f"✅ Request #{wid} bhej di gayi ({fmt(amount)}).\nStatus: ⏳ Pending\n"
                   "Admin review karega, har status change par aapko message aayega.",
               kb([HOME_BTN]))
    await notify_admins(
        cb.bot, config,
        f"🔔 <b>Nayi withdrawal request #{wid}</b>\n👤 User: <code>{user['tg_id']}</code>\n"
        f"💸 Amount: {fmt(amount)}\n🏦 UPI: <code>{esc(upi)}</code>",
        kb([("✅ Approve", f"ad:wda:{wid}"), ("❌ Reject", f"ad:c:wdr:{wid}")],
           [("👁 Dekho", f"ad:wdv:{wid}")]))
