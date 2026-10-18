"""Keyboard helpers aur message show/edit helper."""
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup


def kb(*rows):
    """rows: har row list of ('text', 'callback_data') ya ('text', None, 'url')."""
    out = []
    for row in rows:
        line = []
        for b in row:
            if len(b) == 3:
                line.append(InlineKeyboardButton(text=b[0], url=b[2]))
            else:
                line.append(InlineKeyboardButton(text=b[0], callback_data=b[1]))
        out.append(line)
    return InlineKeyboardMarkup(inline_keyboard=out)


HOME_BTN = ("🏠 Main Menu", "menu:home")


async def show(event, text, markup=None):
    """Callback ho to message edit karo, warna naya message bhejo."""
    if isinstance(event, CallbackQuery):
        try:
            await event.message.edit_text(text, reply_markup=markup)
            return
        except TelegramBadRequest as e:
            if "message is not modified" in str(e):
                return
        except AttributeError:
            pass
        await event.bot.send_message(event.from_user.id, text, reply_markup=markup)
    else:
        await event.answer(text, reply_markup=markup)


def main_menu(is_admin):
    rows = [
        [("👤 Profile", "menu:profile"), ("💰 Balance", "menu:balance")],
        [("🎁 Daily Bonus", "menu:bonus"), ("👥 Refer & Earn", "menu:refer")],
        [("📋 Tasks", "menu:tasks"), ("🎟 Promo Code", "menu:promo")],
        [("💸 Withdraw", "menu:withdraw"), ("🏆 Leaderboard", "menu:lb")],
    ]
    if is_admin:
        rows.append([("🛠 Admin Panel", "ad:home")])
    return kb(*rows)


KIND_LABEL = {
    "referral": "Referral reward",
    "daily_bonus": "Daily bonus",
    "task_reward": "Task reward",
    "promo": "Promo code",
    "withdraw_hold": "Withdrawal request",
    "withdraw_refund": "Withdrawal refund",
    "admin_credit": "Admin credit",
    "admin_debit": "Admin debit",
}

WD_STATUS = {
    "pending": "⏳ Pending",
    "approved": "✅ Approved (payment baaki hai)",
    "rejected": "❌ Rejected",
    "paid": "💸 Paid",
}

SUB_STATUS = {"pending": "⏳ Pending", "approved": "✅ Approved", "rejected": "❌ Rejected"}
