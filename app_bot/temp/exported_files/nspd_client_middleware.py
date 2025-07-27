from collections.abc import Awaitable
from typing import Any, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app_bot.nspd_service.nspd_client import NspdClient


class NspdClientMiddleware(BaseMiddleware):
    """
    Middleware для передачи экземпляра NspdClient в хендлеры.
    """

    def __init__(self, nspd_client: NspdClient):
        self.nspd_client = nspd_client

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        # "Прокидываем" nspd_client в словарь data, который доступен в хендлерах
        data["nspd_client"] = self.nspd_client
        # Вызываем следующий обработчик в цепочке, передавая обновленные данные
        return await handler(event, data)
