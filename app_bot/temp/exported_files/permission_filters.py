import logging
from typing import Any

from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app_bot.config.config import get_env_settings
from app_bot.database import crud
from app_bot.database.models import Permission


logger = logging.getLogger(__name__)


class HasPermissionFilter(BaseFilter):
    """
    Фильтр для проверки прав пользователя.
    Поддерживает проверку одного права или списка прав (любое из списка).
    Суперадмин (ADMIN_ID) проходит все проверки автоматически.
    """

    def __init__(self, permissions: Permission | list[Permission]):
        # Приводим к списку для единообразной обработки
        if isinstance(permissions, Permission):
            self.permissions = [permissions]
        else:
            self.permissions = permissions

    async def __call__(
        self, event: Message | CallbackQuery, session: AsyncSession, **kwargs: Any
    ) -> bool:
        """
        Проверяет права пользователя.

        Args:
            event: Событие (Message или CallbackQuery)
            session: Сессия БД (приходит из DbSessionMiddleware)

        Returns:
            True если пользователь имеет права, False иначе
        """
        # Получаем telegram_id из события
        telegram_id = None

        if isinstance(event, Message):
            telegram_id = event.from_user.id if event.from_user else None
        elif isinstance(event, CallbackQuery):
            telegram_id = event.from_user.id if event.from_user else None

        if not telegram_id:
            logger.warning("HasPermissionFilter: Не удалось получить telegram_id из события")
            return False

        # Получаем ADMIN_ID из настроек
        env_settings = get_env_settings()

        # Суперадмин проходит все проверки
        if telegram_id == env_settings.ADMIN_ID:
            logger.debug(
                f"HasPermissionFilter: Пользователь {telegram_id} - суперадмин, доступ разрешен"
            )
            return True

        # Загружаем пользователя из БД
        user = await crud.get_user_by_telegram_id(session, telegram_id)

        if not user:
            logger.warning(f"HasPermissionFilter: Пользователь {telegram_id} не найден в БД")
            return False

        # Проверяем права - достаточно любого из требуемых прав
        for permission in self.permissions:
            if user.has_permission(permission):
                logger.debug(
                    f"HasPermissionFilter: Пользователь {telegram_id} имеет право {permission.value}"
                )
                return True

        logger.debug(
            f"HasPermissionFilter: Пользователь {telegram_id} не имеет прав {[p.value for p in self.permissions]}"
        )
        return False
