from aiogram import Bot
from aiogram import Dispatcher
from aiogram.types import Update
from contextlib import asynccontextmanager
from dishka import AsyncContainer
from dishka import FromDishka
from dishka.integrations.fastapi import DishkaRoute
from fastapi import APIRouter
from fastapi import FastAPI
from fastapi import Request

from source.config import settings
from source.database import create_tables
from source.database import drop_tables
from source.utils import set_default_commands


@asynccontextmanager
async def lifespan(app: FastAPI, bot: Bot, dp: Dispatcher):
    await drop_tables()
    await create_tables()

    await set_default_commands(bot)

    if settings.tg.webhook_use:
        webhook_url = f"{settings.webhook.url.rstrip('/')}{settings.tg.webhook_path}"
        await bot.set_webhook(
            url=webhook_url,
            secret_token=settings.webhook.secret.get_secret_value(),
            allowed_updates=dp.resolve_used_update_types(),
            drop_pending_updates=True,
        )
    yield
    if settings.tg.webhook_use:
        await bot.delete_webhook()


def create_app(bot: Bot, dp: Dispatcher) -> FastAPI:
    async def app_lifespan(app: FastAPI):
        async with lifespan(app, bot, dp):
            yield

    app = FastAPI(lifespan=app_lifespan)
    webhook_router = APIRouter(route_class=DishkaRoute)

    @webhook_router.post(settings.tg.webhook_path)
    async def telegram_webhook(request: Request, container: FromDishka[AsyncContainer]):
        if (
            request.headers.get("X-Telegram-Bot-Api-Secret-Token")
            != settings.webhook.secret.get_secret_value()
        ):
            return {"ok": False, "error": "Wrong secret token"}

        update = Update.model_validate(await request.json(), context={"bot": bot})
        await dp.feed_update(bot=bot, update=update, dishka_container=container)
        return {"ok": True}

    app.include_router(webhook_router)

    return app
