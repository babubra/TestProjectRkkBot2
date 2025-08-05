# Файл: map_backend/crud/crud_map_request.py

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# ВАЖНО: Импортируем модель напрямую из кода бота, чтобы избежать дублирования
from app_bot.database.models import MapRequest


logger = logging.getLogger(__name__)


async def get_valid_map_request_by_token(
    token: str, db_session: AsyncSession
) -> MapRequest | None:
    """
    Асинхронно извлекает одну запись MapRequest из базы данных по токену,
    а также проверяет, что срок действия токена не истек.

    Args:
        token: Уникальный токен для поиска.
        db_session: Сессия SQLAlchemy для выполнения запроса.

    Returns:
        Объект MapRequest, если он найден и действителен, иначе None.
    """
    logger.info(f"Поиск в БД действительного токена: {token[:8]}...")

    # 1. Создаем запрос к БД для поиска записи по токену
    stmt = select(MapRequest).where(MapRequest.request_token == token)

    # 2. Выполняем запрос
    result = await db_session.execute(stmt)
    map_request = result.scalar_one_or_none()

    # 3. Проверяем результат
    if not map_request:
        logger.warning(f"Токен {token[:8]}... не найден в базе данных.")
        return None

    # 4. Проверяем, что срок действия токена не истек
    # Сравниваем "наивное" время сейчас (в UTC) с "осведомленным" временем из БД
    if map_request.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        logger.warning(f"Токен {token[:8]}... найден, но его срок действия истек.")
        return None

    logger.info(f"Токен {token[:8]}... найден и действителен. ID записи: {map_request.id}.")
    return map_request
