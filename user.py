from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from services import bonus, leaderboard, promos, settings, users
from utils import timeutil
from utils.money import fmt
from utils.ui import HOME_BTN, KIND_LABEL, WD_STATUS, kb, show
from utils.validators import clean_code, esc, mask_name

router = Router(name="user")


class PromoFSM(StatesGroup):
    code = State()


@router.callback_query(F.data == "menu:profile")
async def profile(cb: CallbackQuery, user, pool):
    await cb.answer()
    st = await users.stats(pool, user["tg_id"])
    uname = f"@{esc(user['username'])}" if user["username"] else "-"
    text = (
        "👤 <b>Aapka Profile</b>\n\n"
        f"🆔 ID: <code>{user['tg_id']}</code>\n"
        f"📛 Naam: {esc(user['first_name'])}\n"
        f"🔖 Username: {uname}\n"
        f"📅 Join date: {timeutil.fmt_dt(user['registered_at'])}\n\n"
        f"💰 Balance: <b>{fmt(user['balance'])}</b>\n"
        f"📈 Total kamaya: {fmt(user['total_earned'])}\n"
        f"💸 Total withdraw (Paid): {fmt(user['total_withdrawn'])}\n"
        f"👥 Referrals: {st['referrals']}\n"
        f"🎁 Daily bonus liye: {st['bonuses']}"
    )
    await show(cb, text, kb([HOME_BTN]))


@router.callback_query(F.data == "menu:balance")
async def balance(cb: CallbackQuery, user, pool):
    await cb.answer()
    st = await users.stats(pool, user["tg_id"])
    text = (
        "💰 <b>Aapka Balance</b>\n\n"
        f"✅ Available: <b>{fmt(user['balance'])}</b>\n"
        f"📈 Total earned: {fmt(user['total_earned'])}\n"
        f"💸 Total withdrawn: {fmt(user['total_withdrawn'])}\n"
        f"👥 Referrals: {st['referrals']}"
    )
    await show(cb, text, kb(
        [("🧾 Transaction History", "hist:tx"), ("🎁 Bonus History", "hist:bonus")],
        [("💸 Withdraw History", "hist:wd")],
        [HOME_BTN]))


@router.callback_query(F.data == "hist:tx")
async def hist_tx(cb: CallbackQuery, user, pool):
    await cb.answer()
    rows = await users.recent_transactions(pool, user["tg_id"], 10)
    if not rows:
        text = "🧾 Abhi koi transaction nahi hai."
    else:
        lines = []
        for r in rows:
            sign = "+" if r["amount"] > 0 else "-"
            lines.append(f"{sign}{fmt(abs(r['amount']))} • {KIND_LABEL.get(r['kind'], r['kind'])} • "
                         f"{timeutil.fmt_dt(r['created_at'])}")
        text = "🧾 <b>Last 10 Transactions</b>\n\n" + "\n".join(lines)
    await show(cb, text, kb([("⬅️ Back", "menu:balance")], [HOME_BTN]))


@router.callback_query(F.data == "hist:bonus")
async def hist_bonus(cb: CallbackQuery, user, pool):
    await cb.answer()
    rows = await users.recent_bonuses(pool, user["tg_id"], 10)
    if not rows:
        text = "🎁 Abhi tak koi daily bonus nahi liya."
    else:
        lines = [f"{r['bonus_date'].strftime('%d %b %Y')} • +{fmt(r['amount'])}" for r in rows]
        text = "🎁 <b>Daily Bonus History</b>\n\n" + "\n".join(lines)
    await show(cb, text, kb([("⬅️ Back", "menu:balance")], [HOME_BTN]))


@router.callback_query(F.data == "hist:wd")
async def hist_wd(cb: CallbackQuery, user, pool):
    from services import withdrawals

    await cb.answer()
    rows = await withdrawals.user_history(pool, user["tg_id"], 10)
    if not rows:
        text = "💸 Abhi tak koi withdrawal request nahi hai."
    else:
        lines = [f"#{r['id']} • {fmt(r['amount'])} • {WD_STATUS[r['status']]} • "
                 f"{timeutil.fmt_dt(r['created_at'])}" for r in rows]
        text = "💸 <b>Withdrawal History</b>\n\n" + "\n".join(lines)
    await show(cb, text, kb([("⬅️ Back", "menu:balance")], [HOME_BTN]))


@router.callback_query(F.data == "menu:refer")
async def refer(cb: CallbackQuery, user, pool, config):
    await cb.answer()
    reward = await settings.get_int(pool, "referral_reward")
    st = await users.stats(pool, user["tg_id"])
    link = f"https://t.me/{config.bot_username}?start=ref_{user['tg_id']}"
    text = (
        "👥 <b>Refer &amp; Earn</b>\n\n"
        f"Har successful referral par aapko <b>{fmt(reward)}</b> milenge.\n"
        "Reward tab milta hai jab dost bot start karke channel join verify kar leta hai.\n\n"
        f"🔗 Aapka link:\n<code>{link}</code>\n\n"
        f"✅ Successful referrals: <b>{st['referrals']}</b>"
    )
    await show(cb, text, kb([HOME_BTN]))


@router.callback_query(F.data == "menu:bonus")
async def daily_bonus(cb: CallbackQuery, user, pool):
    try:
        amount = await bonus.claim(pool, user["tg_id"])
    except bonus.BonusDisabled:
        await cb.answer("Daily bonus abhi band hai.", show_alert=True)
        return
    except bonus.AlreadyClaimed:
        await cb.answer("Aaj ka bonus le chuke ho! Kal 12:00 AM (IST) ke baad aana.", show_alert=True)
        return
    await cb.answer()
    await show(cb, f"🎁 Daily bonus mil gaya: <b>+{fmt(amount)}</b>\nKal phir aana!", kb([HOME_BTN]))


@router.callback_query(F.data == "menu:lb")
async def lb_menu(cb: CallbackQuery, pool):
    if not await settings.get_bool(pool, "leaderboard_enabled"):
        await cb.answer("Leaderboard abhi band hai.", show_alert=True)
        return
    await cb.answer()
    await show(cb, "🏆 <b>Referral Leaderboard</b>\nKaunsa dekhna hai?",
               kb([("📅 Is Hafte Ka", "lb:w"), ("🌟 All-Time", "lb:a")], [HOME_BTN]))


@router.callback_query(F.data.in_({"lb:w", "lb:a"}))
async def lb_show(cb: CallbackQuery, pool):
    if not await settings.get_bool(pool, "leaderboard_enabled"):
        await cb.answer("Leaderboard abhi band hai.", show_alert=True)
        return
    await cb.answer()
    weekly = cb.data == "lb:w"
    rows = await leaderboard.top(pool, weekly, 10)
    title = "📅 Is Hafte Ka Top 10 (Mon se, IST)" if weekly else "🌟 All-Time Top 10"
    if not rows:
        body = "Abhi koi entry nahi hai. Referral karke pehle number par aao!"
    else:
        medals = ["🥇", "🥈", "🥉"]
        body = "\n".join(
            f"{medals[i] if i < 3 else str(i + 1) + '.'} {mask_name(r['first_name'])} — {r['cnt']} referrals"
            for i, r in enumerate(rows))
    await show(cb, f"🏆 <b>{title}</b>\n\n{body}",
               kb([("⬅️ Back", "menu:lb")], [HOME_BTN]))


@router.callback_query(F.data == "menu:promo")
async def promo_start(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.set_state(PromoFSM.code)
    await show(cb, "🎟 Apna promo code bhejo (sirf letters, numbers, - aur _):", kb([HOME_BTN]))


@router.message(PromoFSM.code, F.text)
async def promo_redeem(message: Message, user, pool, state: FSMContext):
    code = clean_code(message.text)
    if code is None:
        await message.answer("❌ Code galat format mein hai. Dobara bhejo ya Main Menu dabao.",
                             reply_markup=kb([HOME_BTN]))
        return
    try:
        reward = await promos.redeem(pool, user["tg_id"], code)
    except promos.PromoNotFound:
        msg = "❌ Ye promo code maujood nahi hai."
    except promos.PromoInactive:
        msg = "❌ Ye promo code abhi band hai."
    except promos.PromoExpired:
        msg = "⌛ Ye promo code expire ho chuka hai."
    except promos.PromoLimitReached:
        msg = "😕 Is promo code ki limit poori ho chuki hai."
    except promos.PromoAlreadyUsed:
        msg = "⚠️ Aap ye code pehle hi use kar chuke ho."
    else:
        msg = f"✅ Promo code lag gaya! <b>+{fmt(reward)}</b> balance mein add hue."
    await state.clear()
    await message.answer(msg, reply_markup=kb([HOME_BTN]))
