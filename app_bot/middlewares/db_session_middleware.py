from typing import Callable, Dict, Any, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession


class DbSessionMiddleware(BaseMiddleware):
    """
    Middleware для передачи сессии SQLAlchemy в хендлеры.
    """

    def __init__(self, session_pool: async_sessionmaker[AsyncSession]):
        self.session_pool = session_pool

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        # Используем контекстный менеджер session_pool для создания сессии
        async with self.session_pool.begin() as session:
            # "Прокидываем" сессию в словарь data, который доступен в хендлерах
            data["session"] = session
            # Вызываем следующий обработчик в цепочке, передавая обновленные данные
            return await handler(event, data)
