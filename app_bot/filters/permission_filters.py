# Файл: app_bot/filters/permission_filters.py
from aiogram.filters import BaseFilter
from aiogram.types import TelegramObject

from app_bot.config.config import EnvSettings
from app_bot.database.models import Permission, User


class HasPermissionFilter(BaseFilter):
    """
    Фильтр для проверки прав доступа пользователя.
    """

    def __init__(self, permissions: Permission | list[Permission]):
        # Приводим к списку для унифицированной обработки
        if isinstance(permissions, list):
            self.permissions = permissions
        else:
            self.permissions = [permissions]

    async def __call__(
        self,
        event: TelegramObject,  # Используем общий тип TelegramObject
        user: User | None,
        env_settings: EnvSettings,
        data: dict[str, any],  # Получаем доступ к data от middleware
    ) -> bool:
        # Получаем объект пользователя aiogram из данных,
        # которые предоставляет middleware. Это самый надежный способ.
        event_from_user = data.get("event_from_user")

        # Если событие не от пользователя (например, пост в канале), доступ запрещен.
        if not event_from_user:
            return False

        # --- НОВАЯ, ПРАВИЛЬНАЯ ЛОГИКА ---

        # 1. Проверка на супер-администратора. Этот пользователь имеет доступ ко всему,
        # даже если его нет в базе данных. Проверка происходит до обращения к БД.
        if event_from_user.id == env_settings.ADMIN_ID:
            return True

        # 2. Если это не супер-администратор, то теперь мы проверяем его наличие в БД.
        # Если `user` это None, значит, у обычного пользователя нет доступа.
        if user is None:
            return False

        # 3. Для обычного пользователя из БД проверяем, есть ли у него ВСЕ необходимые права.
        for perm in self.permissions:
            if not user.has_permission(perm):
                return False

        # 4. Если все проверки для обычного пользователя пройдены.
        return True
