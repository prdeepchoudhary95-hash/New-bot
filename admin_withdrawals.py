import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery

from filters import IsAdmin
import admin as admin_svc
import withdrawals
import timeutil
from money import fmt
from notify import safe_send
from ui import WD_STATUS, kb, show
from validators import esc

log = logging.getLogger(__name__)
router = Router(name="admin_withdrawals")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

BACK = ("⬅️ Admin Panel", "ad:home")


@router.callback_query(F.data.in_({"ad:wd:pending", "ad:wd:approved"}))
async def wd_list(cb: CallbackQuery, pool):
    await cb.answer()
    status = cb.data.split(":")[2]
    rows = await withdrawals.list_by_status(pool, status, 20)
    buttons = [[(f"#{r['id']} • {fmt(r['amount'])} • {r['user_id']}", f"ad:wdv:{r['id']}")] for r in rows]
    other = "approved" if status == "pending" else "pending"
    buttons.append([(f"➡️ {WD_STATUS[other]} dekho", f"ad:wd:{other}")])
    buttons.append([BACK])
    title = f"💸 <b>{WD_STATUS[status]} withdrawals</b> (pehli 20)"
    await show(cb, title if rows else title + "\n\nKoi nahi.", kb(*buttons))


def wd_text(w):
    return (
        f"💸 <b>Withdrawal #{w['id']}</b>\n"
        f"👤 User: <code>{w['user_id']}</code>\n"
        f"💰 Amount: <b>{fmt(w['amount'])}</b>\n"
        f"🏦 UPI: <code>{esc(w['upi_id'])}</code>\n"
        f"📌 Status: {WD_STATUS[w['status']]}\n"
        f"🕒 Request: {timeutil.fmt_dt(w['created_at'])}"
    )


def wd_buttons(w):
    wid = w["id"]
    rows = []
    if w["status"] == "pending":
        rows.append([("✅ Approve", f"ad:wda:{wid}"), ("❌ Reject", f"ad:c:wdr:{wid}")])
    elif w["status"] == "approved":
        rows.append([("💸 Paid Mark Karo", f"ad:c:wdp:{wid}"), ("❌ Reject", f"ad:c:wdr:{wid}")])
    rows.append([("👤 User", f"ad:uv:{w['user_id']}")])
    rows.append([("⬅️ List", "ad:wd:pending"), BACK])
    return kb(*rows)


async def _show_wd(cb, pool, wid):
    w = await withdrawals.get(pool, wid)
    if w is None:
        await show(cb, "❌ Request nahi mili.", kb([BACK]))
        return
    await show(cb, wd_text(w), wd_buttons(w))


@router.callback_query(F.data.startswith("ad:wdv:"))
async def wd_view(cb: CallbackQuery, pool):
    await cb.answer()
    await _show_wd(cb, pool, int(cb.data.split(":")[2]))


@router.callback_query(F.data.startswith("ad:wda:"))
async def wd_approve(cb: CallbackQuery, pool):
    wid = int(cb.data.split(":")[2])
    try:
        w = await withdrawals.approve(pool, wid, cb.from_user.id)
    except withdrawals.InvalidState:
        await cb.answer("Ye request ab pending nahi hai.", show_alert=True)
        await _show_wd(cb, pool, wid)
        return
    await admin_svc.log_action(pool, cb.from_user.id, "wd_approve", f"id={wid}")
    await cb.answer("Approved")
    await safe_send(cb.bot, w["user_id"],
                    f"✅ Aapki withdrawal request #{wid} ({fmt(w['amount'])}) <b>approve</b> ho gayi hai.\n"
                    "Admin jaldi aapke UPI par payment karega. Payment hone ke baad status 'Paid' ho jayega.")
    await _show_wd(cb, pool, wid)


@router.callback_query(F.data.startswith("ad:y:wdr:"))
async def wd_reject(cb: CallbackQuery, pool):
    wid = int(cb.data.split(":")[3])
    try:
        w = await withdrawals.reject(pool, wid, cb.from_user.id)
    except withdrawals.InvalidState:
        await cb.answer("Ye request ab reject nahi ho sakti (pehle hi reject/paid).", show_alert=True)
        await _show_wd(cb, pool, wid)
        return
    await admin_svc.log_action(pool, cb.from_user.id, "wd_reject", f"id={wid}")
    await cb.answer("Rejected + refund")
    await safe_send(cb.bot, w["user_id"],
                    f"❌ Aapki withdrawal request #{wid} <b>reject</b> ho gayi.\n"
                    f"{fmt(w['amount'])} aapke balance mein wapas add kar diye gaye hain.")
    await _show_wd(cb, pool, wid)


@router.callback_query(F.data.startswith("ad:y:wdp:"))
async def wd_paid(cb: CallbackQuery, pool):
    wid = int(cb.data.split(":")[3])
    try:
        w = await withdrawals.mark_paid(pool, wid, cb.from_user.id)
    except withdrawals.InvalidState:
        await cb.answer("Sirf 'Approved' request ko Paid mark kar sakte ho.", show_alert=True)
        await _show_wd(cb, pool, wid)
        return
    await admin_svc.log_action(pool, cb.from_user.id, "wd_paid", f"id={wid}")
    await cb.answer("Paid mark ho gaya")
    await safe_send(cb.bot, w["user_id"],
                    f"💸 Admin ne aapki withdrawal #{wid} ({fmt(w['amount'])}) ko <b>Paid</b> mark kiya hai.\n"
                    "Agar payment na mile to support se sampark karo.")
    await _show_wd(cb, pool, wid)
