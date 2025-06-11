import contextlib
import logging
from typing import AsyncGenerator, AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app_bot.database.models import Base

logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    Один экземпляр на процесс:
    • держит AsyncEngine
    • раздаёт короткоживущие AsyncSession
    • умеет создавать/удалять таблицы и корректно закрываться
    """

    def __init__(self, url: str, echo: bool = False) -> None:
        self._engine = create_async_engine(url, echo=echo, pool_pre_ping=True)
        self._session_factory = async_sessionmaker(
            self._engine,
            expire_on_commit=False,
            autoflush=False,
            class_=AsyncSession,
        )
        logger.info("AsyncEngine создан (%s)", url)

    async def create_all(self) -> None:
        """Создать все таблицы (dev-режим)."""
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Таблицы созданы/уже существовали")

    async def drop_all(self) -> None:
        """Удалить все таблицы (осторожно!)."""
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        logger.warning("Таблицы удалены")

    async def dispose(self) -> None:
        """Закрыть пул соединений (graceful-shutdown)."""
        await self._engine.dispose()
        logger.info("Engine.dispose() выполнен")

    @contextlib.asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self._session_factory() as sess:
            try:
                yield sess
                await sess.commit()
            except Exception:
                await sess.rollback()
                raise

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        """Возвращает фабрику сессий."""
        return self._session_factory

    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Генератор для middleware-стиля."""
        async with self.session() as sess:
            yield sess
