from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import tasks
import timeutil
from money import fmt
from notify import notify_admins
from ui import HOME_BTN, SUB_STATUS, kb, show
from validators import clean_text, esc

router = Router(name="tasks")


class ProofFSM(StatesGroup):
    proof = State()


@router.callback_query(F.data == "menu:tasks")
async def list_tasks(cb: CallbackQuery, user, pool, state: FSMContext):
    await state.clear()
    await cb.answer()
    rows = await tasks.list_available(pool, user["tg_id"])
    buttons = [[(f"{r['title'][:30]} • {fmt(r['reward'])}", f"tk:v:{r['id']}")] for r in rows]
    buttons.append([("📜 Meri Submissions", "tk:my")])
    buttons.append([HOME_BTN])
    text = "📋 <b>Available Tasks</b>\nKoi task chuno:" if rows else \
        "📋 Abhi koi naya task available nahi hai. Baad mein check karo."
    await show(cb, text, kb(*buttons))


@router.callback_query(F.data.startswith("tk:v:"))
async def view_task(cb: CallbackQuery, pool):
    await cb.answer()
    tid = int(cb.data.split(":")[2])
    t = await tasks.get(pool, tid)
    if t is None or not t["is_active"]:
        await show(cb, "Ye task ab available nahi hai.", kb([("⬅️ Tasks", "menu:tasks")]))
        return
    text = (f"📋 <b>{esc(t['title'])}</b>\n💰 Reward: <b>{fmt(t['reward'])}</b>\n\n"
            f"{esc(t['description'])}\n\n📝 <b>Instructions:</b>\n{esc(t['instructions'])}")
    await show(cb, text, kb([("📤 Proof Submit Karo", f"tk:s:{tid}")], [("⬅️ Tasks", "menu:tasks")]))


@router.callback_query(F.data.startswith("tk:s:"))
async def ask_proof(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    tid = int(cb.data.split(":")[2])
    await state.set_state(ProofFSM.proof)
    await state.update_data(task_id=tid)
    await show(cb, "📤 Apna proof bhejo: <b>ek screenshot (photo)</b> ya <b>text</b> (max 500 characters).\n"
                   "Admin check karke approve karega, tabhi reward milega.",
               kb([("❌ Cancel", "menu:tasks")]))


@router.message(ProofFSM.proof, F.photo | F.text)
async def got_proof(message: Message, user, pool, state: FSMContext, config):
    data = await state.get_data()
    tid = data.get("task_id")
    file_id, text = None, None
    if message.photo:
        file_id = message.photo[-1].file_id
        text = clean_text(message.caption, 500) if message.caption else None
    else:
        text = clean_text(message.text, 500)
        if text is None:
            await message.answer("❌ Proof 1 se 500 characters ke beech hona chahiye. Dobara bhejo.",
                                 reply_markup=kb([("❌ Cancel", "menu:tasks")]))
            return
    if tid is None:
        await state.clear()
        await message.answer("Session expire ho gaya.", reply_markup=kb([("⬅️ Tasks", "menu:tasks")]))
        return
    try:
        sub_id = await tasks.submit(pool, tid, user["tg_id"], text, file_id)
    except tasks.TaskUnavailable:
        await state.clear()
        await message.answer("❌ Ye task ab available nahi hai.", reply_markup=kb([("⬅️ Tasks", "menu:tasks")]))
        return
    except tasks.AlreadySubmitted:
        await state.clear()
        await message.answer("⚠️ Is task ki submission pehle se pending/approved hai.",
                             reply_markup=kb([("⬅️ Tasks", "menu:tasks")]))
        return
    await state.clear()
    await message.answer(f"✅ Proof submit ho gaya (#{sub_id}). Admin review ke baad aapko message aayega.",
                         reply_markup=kb([("⬅️ Tasks", "menu:tasks")], [HOME_BTN]))
    await notify_admins(message.bot, config, f"📝 Nayi task submission #{sub_id} aayi hai.",
                        kb([("👁 Review Karo", f"ad:sv:{sub_id}")]))


@router.callback_query(F.data == "tk:my")
async def my_subs(cb: CallbackQuery, user, pool):
    await cb.answer()
    rows = await tasks.user_history(pool, user["tg_id"], 10)
    if not rows:
        text = "📜 Abhi tak koi submission nahi hai."
    else:
        lines = [f"#{r['id']} • {esc(r['title'][:30])} • {fmt(r['reward'])} • {SUB_STATUS[r['status']]} • "
                 f"{timeutil.fmt_dt(r['created_at'])}" for r in rows]
        text = "📜 <b>Meri Task Submissions</b>\n\n" + "\n".join(lines)
    await show(cb, text, kb([("⬅️ Tasks", "menu:tasks")], [HOME_BTN]))
