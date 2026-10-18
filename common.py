from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from utils.ui import main_menu, show
from utils.validators import esc

router = Router(name="common")

WELCOME = (
    "👋 Namaste <b>{name}</b>!\n\n"
    "Yahan aap referral, daily bonus, tasks aur promo codes se kamai kar sakte ho.\n"
    "Neeche menu se option chuno 👇"
)


@router.message(CommandStart())
async def cmd_start(message: Message, user, is_admin, state: FSMContext):
    await state.clear()
    await message.answer(WELCOME.format(name=esc(user["first_name"] or "dost")),
                         reply_markup=main_menu(is_admin))


@router.message(Command("menu"))
async def cmd_menu(message: Message, is_admin, state: FSMContext):
    await state.clear()
    await message.answer("🏠 Main Menu", reply_markup=main_menu(is_admin))


@router.callback_query(F.data == "menu:home")
async def cb_home(cb: CallbackQuery, is_admin, state: FSMContext):
    await state.clear()
    await cb.answer()
    await show(cb, "🏠 Main Menu", main_menu(is_admin))


@router.callback_query(F.data == "chk_join")
async def cb_join_ok(cb: CallbackQuery, user, is_admin, state: FSMContext):
    # Yahan tak pahunche matlab middleware ne membership verify kar li.
    await state.clear()
    await cb.answer("✅ Verified!")
    await show(cb, WELCOME.format(name=esc(user["first_name"] or "dost")), main_menu(is_admin))
