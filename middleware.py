"""Har message/callback se pehle: register, ban check, force-join check, referral reward."""
import logging
import time

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, Message

import referrals
import settings
import users
from notify import safe_send
from ui import kb
from money import fmt

log = logging.getLogger(__name__)
_MEMBER_STATUSES = {"creator", "administrator", "member"}


def parse_ref(payload):
    p = (payload or "").strip()
    if p.startswith("ref_"):
        p = p[4:]
    return int(p) if p.isdigit() and len(p) <= 15 else None


class AccessMiddleware(BaseMiddleware):
    def __init__(self, pool, cfg):
        self.pool = pool
        self.cfg = cfg
        self._member_cache = {}  # uid -> expiry (monotonic), sirf "member hai" cache hota hai

    async def _is_member(self, bot, uid):
        """True/False; None agar check hi nahi ho paya (bot channel mein admin nahi, etc.)."""
        if self._member_cache.get(uid, 0) > time.monotonic():
            return True
        try:
            m = await bot.get_chat_member(self.cfg.force_join_channel, uid)
        except TelegramAPIError as e:
            log.error("Force-join check fail hua (bot channel mein admin hai?): %s", e)
            return None
        ok = m.status in _MEMBER_STATUSES or (
            m.status == "restricted" and getattr(m, "is_member", False))
        if ok:
            self._member_cache[uid] = time.monotonic() + 60
        return ok

    async def __call__(self, handler, event, data):
        tg = event.from_user
        if tg is None or tg.is_bot:
            return None
        is_cb = isinstance(event, CallbackQuery)
        chat = event.message.chat if is_cb and event.message else getattr(event, "chat", None)
        if chat is not None and chat.type != "private":
            return None

        ref_id = None
        if isinstance(event, Message) and event.text and event.text.startswith("/start"):
            parts = event.text.split(maxsplit=1)
            if len(parts) == 2:
                ref_id = parse_ref(parts[1])

        if is_cb and event.data and event.data.startswith(("menu:", "lb:", "hist:")):
            st = data.get("state")
            if st is not None:
                await st.clear()  # menu dabane par adhoora flow band

        user, _created = await users.register(self.pool, tg.id, tg.username, tg.first_name, ref_id)
        bot = data["bot"]

        if user["is_banned"]:
            if is_cb:
                await event.answer("🚫 Aapka account ban hai.", show_alert=True)
            else:
                await event.answer("🚫 Aapka account ban hai. Support se baat karo.")
            return None

        is_admin = tg.id in self.cfg.admin_ids
        data["is_admin"] = is_admin
        need_join = (
            bool(self.cfg.force_join_channel)
            and not is_admin
            and await settings.get_bool(self.pool, "force_join")
        )
        if need_join:
            member = await self._is_member(bot, tg.id)
            if member is False:
                if is_cb:
                    if event.data == "chk_join":
                        await event.answer("❌ Abhi channel join nahi kiya!", show_alert=True)
                    else:
                        await event.answer()
                prompt = ("📢 Bot use karne ke liye pehle hamara channel join karo, "
                          "phir '✅ Join Kar Liya' dabao.")
                markup = kb([("📢 Channel Join Karo", None, self.cfg.force_join_link)],
                            [("✅ Join Kar Liya", "chk_join")])
                await bot.send_message(tg.id, prompt, reply_markup=markup)
                return None
            if member is True and not user["joined_verified"]:
                await users.mark_joined(self.pool, tg.id)

        # Access mil gaya: referral reward (sirf ek baar, join verify ke baad)
        if not user["referral_rewarded"]:
            res = await referrals.reward_if_due(self.pool, tg.id)
            if res is not None:
                referrer_id, reward = res
                if reward > 0:
                    await safe_send(
                        bot, referrer_id,
                        f"🎉 Aapke referral se naya user judd gaya! {fmt(reward)} aapke balance mein add ho gaye.")
                else:
                    await safe_send(bot, referrer_id, "🎉 Aapke referral se naya user judd gaya!")

        data["user"] = user
        return await handler(event, data)
