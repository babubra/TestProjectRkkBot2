# Файл: app_bot/database/crud.py

import logging
from collections.abc import Sequence
from datetime import date, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import AppSettings, DailyLimitOverride, Permission, User


logger = logging.getLogger(__name__)


async def get_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> User | None:
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


async def delete_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> bool:
    """
    Асинхронно удаляет одного пользователя из базы данных по его telegram_id.

    Args:
        session: Экземпляр AsyncSession для взаимодействия с БД.
        telegram_id: Telegram ID пользователя, которого нужно удалить.

    Returns:
        True, если пользователь был найден и успешно удален, иначе False.
    """
    logger.info(f"Попытка удаления пользователя по telegram_id: {telegram_id}")

    user_to_delete = await get_user_by_telegram_id(session, telegram_id)

    if user_to_delete:
        await session.delete(user_to_delete)
        # Применяем изменения в базе данных в рамках текущей сессии/транзакции.
        await session.flush()
        logger.info(f"Пользователь с telegram_id {telegram_id} успешно удален.")
        return True
    else:
        logger.warning(
            f"Пользователь с telegram_id {telegram_id} не найден. Удаление не требуется."
        )
        return False


async def create_user(
    session: AsyncSession,
    telegram_id: int,
    username: str | None = None,
    megaplan_user_id: int | None = None,
    initial_permissions: list[Permission] | None = None,
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


async def get_users(session: AsyncSession, skip: int = 0, limit: int = 100) -> Sequence[User]:
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

    logger.info(f"Найдено {len(users)} пользователей (пропущено: {skip}, лимит: {limit}).")
    return users


async def get_app_settings(session: AsyncSession) -> AppSettings:
    """
    Получает настройки приложения. Если настроек нет, создает их с дефолтными значениями.
    """
    logger.info("Запрос настроек приложения.")
    stmt = select(AppSettings).order_by(AppSettings.id).limit(1)
    result = await session.execute(stmt)
    settings = result.scalar_one_or_none()

    if not settings:
        logger.warning("Настройки приложения не найдены. Создание настроек по умолчанию.")
        settings = AppSettings()  # Используем default=10 из модели
        session.add(settings)
        await session.flush()
        await session.refresh(settings)
        logger.info(
            f"Созданы настройки по умолчанию: ID={settings.id}, Limit={settings.default_daily_limit}"
        )
    else:
        logger.info(
            f"Настройки приложения найдены: ID={settings.id}, Limit={settings.default_daily_limit}"
        )

    return settings


async def update_default_limit(session: AsyncSession, new_limit: int) -> AppSettings:
    """
    Обновляет лимит по умолчанию в настройках приложения.
    """
    logger.info(f"Попытка обновления лимита по умолчанию на {new_limit}.")

    # Проверка типа данных
    if not isinstance(new_limit, int):
        raise TypeError(
            f"Лимит должен быть целым числом, получен тип: {type(new_limit).__name__}"
        )

    # Проверка на отрицательное значение
    if new_limit < 0:
        raise ValueError("Лимит не может быть отрицательным.")

    settings = await get_app_settings(session)  # Получаем (или создаем) настройки
    settings.default_daily_limit = new_limit
    await session.flush()
    await session.refresh(settings)
    logger.info(f"Лимит по умолчанию успешно обновлен на {settings.default_daily_limit}.")
    return settings


async def update_default_brigades_count(session: AsyncSession, new_count: int) -> AppSettings:
    """
    Обновляет количество бригад по умолчанию в настройках приложения.
    """
    logger.info(f"Попытка обновления количества бригад по умолчанию на {new_count}.")
    if not isinstance(new_count, int) or new_count <= 0:
        raise ValueError("Количество бригад должно быть положительным целым числом.")

    settings = await get_app_settings(session)
    settings.default_brigades_count = new_count
    await session.flush()
    await session.refresh(settings)
    logger.info(
        f"Количество бригад по умолчанию успешно обновлено на {settings.default_brigades_count}."
    )
    return settings


async def get_override_for_date(
    session: AsyncSession, target_date: date
) -> DailyLimitOverride | None:
    """
    Получает переопределение лимита для конкретной даты.
    """
    logger.info(f"Запрос переопределения лимита для даты: {target_date}")
    stmt = select(DailyLimitOverride).where(DailyLimitOverride.limit_date == target_date)
    result = await session.execute(stmt)
    override = result.scalar_one_or_none()
    if override:
        logger.info(f"Найдено переопределение для {target_date}: Лимит={override.daily_limit}")
    else:
        logger.info(f"Переопределение для {target_date} не найдено.")
    return override


async def set_daily_limit_override(
    session: AsyncSession, target_date: date, limit: int, brigades_count: int | None = None
) -> DailyLimitOverride:
    """
    Устанавливает или обновляет переопределение лимита и количества бригад для конкретной даты.
    """
    logger.info(
        f"Установка/обновление лимита для {target_date} на {limit}, бригад: {brigades_count}."
    )
    if limit < 0:
        raise ValueError("Лимит не может быть отрицательным.")
    if brigades_count is not None and brigades_count <= 0:
        raise ValueError("Количество бригад должно быть положительным числом.")

    override = await get_override_for_date(session, target_date)

    if override:
        override.daily_limit = limit
        override.brigades_count = brigades_count
        logger.info(f"Настройки для {target_date} обновлены.")
    else:
        override = DailyLimitOverride(
            limit_date=target_date, daily_limit=limit, brigades_count=brigades_count
        )
        session.add(override)
        logger.info(f"Установлены новые настройки для {target_date}.")

    await session.flush()
    await session.refresh(override)
    return override


async def delete_daily_limit_override(session: AsyncSession, target_date: date) -> bool:
    """
    Удаляет переопределение лимита для конкретной даты.
    Возвращает True, если удаление произошло, иначе False.
    """
    logger.info(f"Попытка удаления переопределения лимита для {target_date}.")
    override = await get_override_for_date(session, target_date)

    if override:
        await session.delete(override)
        await session.flush()
        logger.info(f"Переопределение для {target_date} успешно удалено.")
        return True
    else:
        logger.warning(f"Переопределение для {target_date} не найдено, удаление не требуется.")
        return False


async def delete_daily_limit_override_range(
    session: AsyncSession, start_date: date, end_date: date
) -> int:
    """
    Удаляет переопределения лимитов для указанного диапазона дат (включительно).
    Возвращает количество удаленных записей.
    """
    logger.info(
        f"Попытка удаления переопределений лимитов для диапазона {start_date} - {end_date}."
    )
    if start_date > end_date:
        logger.error("Начальная дата не может быть позже конечной.")
        raise ValueError("Начальная дата не может быть позже конечной.")

    # Создаем SQL-запрос DELETE с условием WHERE для диапазона дат
    stmt = (
        delete(DailyLimitOverride)
        .where(DailyLimitOverride.limit_date >= start_date)
        .where(DailyLimitOverride.limit_date <= end_date)
    )

    # Выполняем запрос
    result = await session.execute(stmt)

    # Получаем количество удаленных строк
    deleted_count = result.rowcount

    # Применяем изменения (хотя execute(delete) обычно автокоммитится в рамках сессии,
    # flush гарантирует синхронизацию перед дальнейшими действиями)
    await session.flush()

    logger.info(
        f"Удалено {deleted_count} переопределений для диапазона {start_date} - {end_date}."
    )
    return deleted_count


async def set_daily_limit_override_range(
    session: AsyncSession,
    start_date: date,
    end_date: date,
    limit: int,
    brigades_count: int | None = None,
) -> list[DailyLimitOverride]:
    """
    Устанавливает или обновляет переопределение лимита для диапазона дат.
    """
    logger.info(
        f"Установка/обновление лимита для диапазона {start_date} - {end_date} на {limit}, бригад: {brigades_count}."
    )
    if limit < 0:
        raise ValueError("Лимит не может быть отрицательным.")
    if start_date > end_date:
        raise ValueError("Начальная дата не может быть позже конечной.")

    overrides_list = []
    current_date = start_date
    while current_date <= end_date:
        override = await set_daily_limit_override(session, current_date, limit, brigades_count)
        overrides_list.append(override)
        current_date += timedelta(days=1)

    logger.info(f"Установлены настройки для {len(overrides_list)} дней в диапазоне.")
    return overrides_list


async def get_actual_limit_for_date(session: AsyncSession, target_date: date) -> int:
    """
    Получает фактический лимит заявок для указанной даты,
    учитывая переопределения и настройки по умолчанию.
    """
    logger.info(f"Запрос фактического лимита для даты: {target_date}")
    override = await get_override_for_date(session, target_date)
    if override is not None:
        logger.info(
            f"Используется переопределенный лимит для {target_date}: {override.daily_limit}"
        )
        return override.daily_limit
    else:
        settings = await get_app_settings(session)
        logger.info(
            f"Используется лимит по умолчанию для {target_date}: {settings.default_daily_limit}"
        )
        return settings.default_daily_limit


async def get_actual_brigades_for_date(session: AsyncSession, target_date: date) -> int:
    """
    Получает фактическое количество бригад для указанной даты,
    учитывая переопределения и настройки по умолчанию.
    """
    logger.info(f"Запрос фактического количества бригад для даты: {target_date}")
    override = await get_override_for_date(session, target_date)

    # Если есть переопределение и в нем указано кол-во бригад
    if override and override.brigades_count is not None:
        logger.info(
            f"Используется переопределенное кол-во бригад для {target_date}: {override.brigades_count}"
        )
        return override.brigades_count
    else:
        settings = await get_app_settings(session)
        logger.info(
            f"Используется кол-во бригад по умолчанию для {target_date}: {settings.default_brigades_count}"
        )
        return settings.default_brigades_count
