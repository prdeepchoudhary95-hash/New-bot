from aiogram import Router
from aiogram.types import CallbackQuery, Message

from utils.ui import main_menu

router = Router(name="fallback")


@router.message()
async def unknown_message(message: Message, is_admin):
    await message.answer("Samajh nahi aaya 🙂 Menu se option chuno:", reply_markup=main_menu(is_admin))


@router.callback_query()
async def unknown_callback(cb: CallbackQuery):
    await cb.answer("Ye button ab kaam nahi karta ya aapko allowed nahi hai.", show_alert=True)
