# Файл: app_bot/database/crud.py

import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List, Sequence  # Sequence импортирован

from .models import User, Permission

logger = logging.getLogger(__name__)


async def get_user_by_telegram_id(
    session: AsyncSession, telegram_id: int
) -> Optional[User]:
    """
    Асинхронно получает одного пользователя из базы данных по его telegram_id.
    """
    logger.info(f"Запрос пользователя по telegram_id: {telegram_id}")
    stmt = select(User).where(User.telegram_id == telegram_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if user:
        logger.info(
            f"Пользователь с telegram_id {telegram_id} найден: ID={user.id}, Username={user.username}"
        )
    else:
        logger.info(f"Пользователь с telegram_id {telegram_id} не найден.")
    return user


async def create_user(
    session: AsyncSession,
    telegram_id: int,
    username: Optional[str] = None,
    megaplan_user_id: Optional[int] = None,
    initial_permissions: Optional[List[Permission]] = None,
) -> User:
    """
    Асинхронно создает нового пользователя и сохраняет его в базе данных.
    """
    logger.info(
        f"Попытка создания пользователя с telegram_id: {telegram_id}, username: {username}"
    )

    permissions_values_for_db = []
    if initial_permissions:
        permissions_values_for_db = [p.value for p in initial_permissions]

    new_user = User(
        telegram_id=telegram_id,
        username=username,
        megaplan_user_id=megaplan_user_id,
        permissions=permissions_values_for_db,
    )

    session.add(new_user)
    await session.flush()
    await session.refresh(new_user)

    logger.info(
        f"Пользователь успешно создан и сохранен в БД: ID={new_user.id}, telegram_id={new_user.telegram_id}, username='{new_user.username}'"
    )

    return new_user


async def get_users(
    session: AsyncSession, skip: int = 0, limit: int = 100
) -> Sequence[User]:
    """
    Асинхронно получает список пользователей из базы данных с пагинацией.

    Args:
        session: Экземпляр AsyncSession для взаимодействия с БД.
        skip: Количество записей, которые нужно пропустить (для пагинации).
        limit: Максимальное количество записей для возврата (для пагинации).

    Returns:
        Последовательность (Sequence) объектов User.
    """
    logger.info(f"Запрос списка пользователей: пропустить={skip}, лимит={limit}")

    stmt = select(User).offset(skip).limit(limit)
    result = await session.execute(stmt)

    users = result.scalars().all()

    logger.info(
        f"Найдено {len(users)} пользователей (пропущено: {skip}, лимит: {limit})."
    )
    return users
