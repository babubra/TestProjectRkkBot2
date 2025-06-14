# Файл: app_bot/middlewares/auth_middleware.py

import logging
from collections.abc import Awaitable
from typing import Any, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import async_sessionmaker

from app_bot.config.config import EnvSettings
from app_bot.database import crud


logger = logging.getLogger(__name__)


class AuthMiddleware(BaseMiddleware):
    def __init__(self, session_pool: async_sessionmaker, env_settings: EnvSettings):
        self.session_pool = session_pool
        self.env_settings = env_settings

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        # event_from_user содержит объект aiogram.User, из которого мы берем ID
        event_user = data.get("event_from_user")
        if not event_user:
            # Если пользователя в событии нет (например, пост в канале), просто продолжаем
            return await handler(event, data)

        # Создаем короткоживущую сессию для одного запроса
        async with self.session_pool() as session:
            # Получаем нашего пользователя из БД (модель User)
            db_user = await crud.get_user_by_telegram_id(session, event_user.id)

            # "Пробрасываем" пользователя и настройки в следующие Middleware, фильтры и хендлеры
            data["user"] = db_user
            data["env_settings"] = self.env_settings

        return await handler(event, data)
