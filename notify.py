import asyncio
import logging

from aiogram.exceptions import (TelegramAPIError, TelegramBadRequest, TelegramForbiddenError,
                                TelegramRetryAfter)

log = logging.getLogger(__name__)


async def safe_send(bot, chat_id, text, **kwargs):
    """Message bhejta hai. Blocked user / Telegram error par crash nahi hota; True/False return karta hai."""
    for _ in range(2):
        try:
            await bot.send_message(chat_id, text, **kwargs)
            return True
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 0.5)
        except TelegramForbiddenError:
            log.info("User %s ne bot block kiya hai ya chat band hai", chat_id)
            return False
        except TelegramBadRequest as e:
            log.warning("Message %s ko nahi gaya: %s", chat_id, e)
            return False
        except TelegramAPIError as e:
            log.warning("Telegram error (%s): %s", chat_id, e)
            return False
    return False


async def notify_admins(bot, cfg, text, markup=None):
    for admin_id in cfg.admin_ids:
        await safe_send(bot, admin_id, text, reply_markup=markup)
