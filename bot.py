"""Entry point: Render Web Service par health-check server + Telegram polling ek saath chalte hain."""
import asyncio
import logging
import sys

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config import ConfigError, load_config
from db.pool import create_pool, init_schema
from handlers import admin_content, admin_core, admin_withdrawals, common, fallback, tasks, user, withdraw
from utils.middleware import AccessMiddleware

log = logging.getLogger("bot")


def build_health_app(pool):
    async def root(_request):
        return web.Response(text="ok")

    async def health(_request):
        try:
            await pool.fetchval("SELECT 1")
        except Exception:
            log.exception("Health check: database error")
            return web.Response(status=503, text="db error")
        return web.Response(text="ok")

    app = web.Application()
    app.add_routes([web.get("/", root), web.get("/health", health)])
    return app


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("aiogram").setLevel(logging.INFO)
    try:
        cfg = load_config()
    except ConfigError as e:
        log.error("Config error: %s", e)
        sys.exit(1)

    pool = await create_pool(cfg.database_url)
    runner = None
    bot = Bot(cfg.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    try:
        await init_schema(pool)
        me = await bot.get_me()
        cfg.bot_username = me.username or "sxearningbot"
        log.info("Bot start ho raha hai: @%s", cfg.bot_username)

        dp = Dispatcher(storage=MemoryStorage(), pool=pool, config=cfg)
        mw = AccessMiddleware(pool, cfg)
        dp.message.outer_middleware(mw)
        dp.callback_query.outer_middleware(mw)
        for r in (common.router, admin_core.router, admin_withdrawals.router, admin_content.router,
                  user.router, withdraw.router, tasks.router, fallback.router):
            dp.include_router(r)

        @dp.errors()
        async def on_error(event):
            log.exception("Unhandled error: %s", event.exception)
            return True

        runner = web.AppRunner(build_health_app(pool))
        await runner.setup()
        await web.TCPSite(runner, "0.0.0.0", cfg.port).start()
        log.info("Health server port %s par chal raha hai", cfg.port)

        await bot.delete_webhook(drop_pending_updates=False)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        for t in list(admin_core.BG_TASKS):
            t.cancel()
        if runner is not None:
            await runner.cleanup()
        await bot.session.close()
        await pool.close()
        log.info("Shutdown poora hua")


if __name__ == "__main__":
    asyncio.run(main())
