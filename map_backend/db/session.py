# Файл: map_backend/db/session.py

import logging
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from map_backend.core.config import get_env_settings


logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    Класс-менеджер для управления подключением к базе данных.
    Хранит движок (engine) и фабрику сессий.
    """

    def __init__(self, db_url: str, echo: bool = False):
        # Создаем асинхронный "движок" для взаимодействия с БД
        self._engine = create_async_engine(db_url, echo=echo)
        # Создаем "фабрику", которая будет производить сессии по запросу
        self._session_factory = async_sessionmaker(
            self._engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )
        logger.info("DatabaseManager для бэкенда инициализирован.")

    async def dispose(self) -> None:
        """Корректно закрывает пул соединений при остановке приложения."""
        await self._engine.dispose()
        logger.info("Пул соединений бэкенда закрыт.")

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        """Возвращает фабрику сессий."""
        return self._session_factory


# 1. Загружаем настройки, чтобы получить путь к БД из .env
settings = get_env_settings()

# 2. Создаем единственный экземпляр менеджера БД для всего приложения
db_manager = DatabaseManager(settings.DATABASE_URL)


# 3. Создаем асинхронный генератор сессий (ключевая функция для FastAPI)
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI Dependency: предоставляет сессию базы данных для одного запроса.
    Гарантирует, что сессия будет закрыта после выполнения запроса.
    """
    async with db_manager.session_factory() as session:
        try:
            yield session
        finally:
            await session.close()
