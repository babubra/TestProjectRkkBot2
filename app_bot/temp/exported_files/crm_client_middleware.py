from collections.abc import Awaitable
from typing import Any, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app_bot.crm_service.crm_client import CRMClient


class CrmClientMiddleware(BaseMiddleware):
    """
    Middleware для передачи экземпляра CRMClient в хендлеры.
    """

    def __init__(self, crm_client: CRMClient):
        self.crm_client = crm_client

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        # "Прокидываем" crm_client в словарь data, который доступен в хендлерах
        data["crm_client"] = self.crm_client
        # Вызываем следующий обработчик в цепочке, передавая обновленные данные
        return await handler(event, data)
