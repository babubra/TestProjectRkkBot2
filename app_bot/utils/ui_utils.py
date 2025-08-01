import asyncio
import json
import logging
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any
from urllib.parse import urljoin

from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app_bot.config.config import get_env_settings
from app_bot.crm_service.crm_client import CRMClient
from app_bot.crm_service.schemas import Deal
from app_bot.database import crud
from app_bot.keyboards.common_keyboards import get_main_menu_kb
from app_bot.keyboards.view_ticket_keyboards import get_deal_action_kb
from app_bot.nspd_service.nspd_client import NspdClient
from app_bot.nspd_service.schemas import CadastralObject
from app_bot.schemas import MapDealData, MapLocation


logger = logging.getLogger(__name__)
settings = get_env_settings()
APP_TIMEZONE = timezone(timedelta(hours=settings.APP_TIMEZONE_OFFSET))


async def get_main_menu_message(
    message: Message, session: AsyncSession, crm_client: CRMClient
) -> None:
    """
    Функция показа главного меню работы с заявками.
    Подгружает информацию о количестве принятых заявок и об общем количестве возможных зяавок
    """
    # Отправляем красивое сообщение о загрузке и сохраняем ссылку на него
    loading_message = await message.answer("⏳ Загружаю меню, пожалуйста подождите...")

    greeting_text = (
        "Здравствуйте!\n\n"
        "Добро пожаловать в систему управления заявками. "
        "Выберите необходимое действие:"
    )

    # Получаем сегодняшнюю и завтрашнюю дату строго в нашем часовом поясе
    now_local = datetime.now(APP_TIMEZONE)
    today = now_local.date()
    tomorrow = today + timedelta(days=1)

    limit_today = 0
    limit_tomorrow = 0
    count_today = 0
    count_tomorrow = 0

    try:
        limit_today = await crud.get_actual_limit_for_date(session, today)
        limit_tomorrow = await crud.get_actual_limit_for_date(session, tomorrow)

        deals_for_period = await crm_client.get_deals_for_date_range_model(
            start_date=today, end_date=tomorrow
        )

        deals_today = []
        deals_tomorrow = []

        if deals_for_period:
            deals_today = [
                deal
                for deal in deals_for_period
                if deal.visit_datetime and deal.visit_datetime.date() == today
            ]
            deals_tomorrow = [
                deal
                for deal in deals_for_period
                if deal.visit_datetime and deal.visit_datetime.date() == tomorrow
            ]

        count_today = len(deals_today)
        count_tomorrow = len(deals_tomorrow)

    except Exception as e:
        logger.error(
            f"Ошибка при получении данных для главного меню (user: {message.from_user.id}): {e}",
            exc_info=True,
        )
        # Редактируем сообщение о загрузке, показывая ошибку
        await loading_message.edit_text(
            "❗️ Произошла ошибка при загрузке данных о заявках. "
            "Некоторые функции могут быть недоступны."
        )
        return

    kb = get_main_menu_kb(
        tickets_today_count=count_today,
        limit_today=limit_today,
        tickets_tomorrow_count=count_tomorrow,
        limit_tomorrow=limit_tomorrow,
    )

    # Редактируем сообщение о загрузке, заменяя его на главное меню
    await loading_message.edit_text(greeting_text, reply_markup=kb)


def strip_html_and_preserve_breaks(text: str) -> str:
    """
    Удаляет HTML-теги, но сохраняет переносы строк от <br> и <p>.
    Это предотвращает "слипание" текста.
    """
    if not text:
        return ""

    # 1. Заменяем теги <br> и </p> на перенос строки
    text = re.sub(r"</p>|<br\s*/?>", "\n", text, flags=re.IGNORECASE)

    # 2. Удаляем все остальные HTML-теги
    text = re.sub(r"<[^>]+?>", "", text)

    # 3. Убираем лишние пустые строки (более двух подряд)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


DEAL_STATUS_ICONS = {
    "166": "📬",  # Воронка заявок
    "152": "🚗",  # Выезд геодезиста
    "160": "🚫",  # Пример: Отменено
}
DEFAULT_STATUS_ICON = "🔵"


def strip_html_tags(text: str) -> str:
    """
    Удаляет HTML-теги из строки для чистого отображения в Telegram.
    """
    if not text:
        return ""
    # Простое регулярное выражение для удаления тегов
    return re.sub("<[^<]+?>", "", text).strip()


def create_2gis_link(lon: float, lat: float) -> str:
    """Создает стандартную веб-ссылку на точку на карте 2ГИС."""
    return f"https://2gis.ru/geo/{lon},{lat}"


async def _enrich_deal_with_nspd_data(
    deal: Deal, nspd_client: NspdClient
) -> list[CadastralObject]:
    """
    Проверяет сделку (в названии и описании) на наличие недостающих данных о КН
    и дозапрашивает их.
    Возвращает ПОЛНЫЙ список кадастровых объектов (старые + новые).
    """
    # Используем `or ""` на случай, если одно из полей None
    name_text = deal.name or ""
    description_text = strip_html_and_preserve_breaks(deal.description or "")
    combined_text = f"{name_text}\n{description_text}"

    if not combined_text.strip():
        return deal.service_data or []

    # 1. Находим все кадастровые номера в объединенном тексте
    cadastral_num_pattern = re.compile(r"\b\d{2}:\d{2}:\d{6,7}:\d{1,5}\b")
    # Используем set для автоматического удаления дубликатов
    required_numbers = set(cadastral_num_pattern.findall(combined_text))

    if not required_numbers:
        return deal.service_data or []

    # 2. Находим номера, по которым уже есть информация
    known_objects = deal.service_data or []
    known_numbers = {obj.cadastral_number for obj in known_objects}

    # 3. Определяем, что нужно запросить (остальная логика не меняется)
    numbers_to_fetch = list(required_numbers - known_numbers)

    if not numbers_to_fetch:
        return known_objects

    logger.info(f"Для сделки {deal.id} требуется запросить данные по КН: {numbers_to_fetch}")

    # 4. Асинхронно запрашиваем недостающие данные
    tasks = [nspd_client.get_object_info(num) for num in numbers_to_fetch]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    newly_fetched_objects = []
    for res in results:
        if isinstance(res, CadastralObject):
            newly_fetched_objects.append(res)
        elif isinstance(res, Exception):
            logger.error(f"Ошибка при запросе данных от NSPD: {res}")

    # 5. Объединяем старые и новые данные
    all_objects = known_objects + newly_fetched_objects
    return all_objects


async def prepare_deal_view_data(
    crm_client: CRMClient,
    start_date: date,
    end_date: date,
    nspd_client: NspdClient,
    session: AsyncSession,
    user_telegram_id: int,
) -> dict[str, Any]:
    """
    Готовит все данные для отображения сделок: текстовые сообщения и ссылку на карту.

    1. Получает сделки из CRM.
    2. Обогащает их данными из NSPD.
    3. В одном цикле формирует:
        - Список сообщений для Telegram.
        - Список данных для карты.
    4. Если есть данные для карты, создает запись в БД и генерирует уникальную ссылку.

    Returns:
        Словарь вида:
        {
            "messages_to_send": list[dict],
            "map_url": str | None
        }
    """
    logger.info(f"Подготовка данных для отображения сделок за {start_date} - {end_date}")

    deals = await crm_client.get_deals_for_date_range_model(
        start_date=start_date, end_date=end_date
    )

    if not deals:
        return {
            "messages_to_send": [
                {"text": "✅ На выбранную дату заявок не найдено.", "reply_markup": None}
            ],
            "map_url": None,
        }

    messages_to_send = []
    data_for_map = []

    for deal in deals:
        # Логика обогащения и сохранения данных NSPD остается прежней
        all_cadastral_objects = await _enrich_deal_with_nspd_data(deal, nspd_client)
        if all_cadastral_objects and all_cadastral_objects != deal.service_data:
            json_data_to_save = json.dumps(
                [obj.model_dump(mode="json") for obj in all_cadastral_objects],
                ensure_ascii=False,
            )
            asyncio.create_task(
                crm_client.update_deal(
                    deal.id, {"Category1000076CustomFieldServiceData": json_data_to_save}
                )
            )
            deal.service_data = all_cadastral_objects

        # --- Часть 1: Готовим текстовое сообщение (как и раньше) ---
        coord_map = {}
        if all_cadastral_objects:
            for cad_object in all_cadastral_objects:
                if cad_object.cadastral_number and cad_object.centroid_wgs84:
                    coord_map[cad_object.cadastral_number] = cad_object.centroid_wgs84

        enriched_name = deal.name
        enriched_description = ""

        if coord_map:
            pattern = re.compile("|".join(re.escape(kn) for kn in coord_map.keys()))

            def replacer(match):
                cadastral_number = match.group(0)
                coords = coord_map.get(cadastral_number)
                if coords:
                    link = create_2gis_link(lon=coords[0], lat=coords[1])
                    return f'<a href="{link}">{cadastral_number}</a>'
                return cadastral_number

            enriched_name = pattern.sub(replacer, deal.name)
            if deal.description:
                clean_description = strip_html_and_preserve_breaks(deal.description)
                enriched_description = pattern.sub(replacer, clean_description)
        elif deal.description:
            enriched_description = strip_html_and_preserve_breaks(deal.description)

        message_parts = []
        icon = DEAL_STATUS_ICONS.get(deal.state.id, DEFAULT_STATUS_ICON)
        if deal.visit_result and isinstance(deal.visit_result, str):
            stripped_result = deal.visit_result.strip()
            if stripped_result:
                icon += stripped_result[0]
        deal_url = urljoin(crm_client.base_url, f"/deals/{deal.id}/card/")
        link_text = f"{icon} Сделка {deal.id}."
        header_link = f'<a href="{deal_url}">{link_text}</a>'
        visit_date_str = ""
        if deal.visit_datetime:
            fmt = (
                "%d.%m.%Y"
                if deal.visit_datetime.time() == datetime.min.time()
                else "%d.%m.%Y %H:%M"
            )
            visit_date_str = f"<b>{deal.visit_datetime.strftime(fmt)}</b>"

        message_parts.append(f"{header_link} {visit_date_str}".strip())
        message_parts.append(f"<b>{enriched_name}</b>")
        if enriched_description:
            message_parts.append(enriched_description)
        if deal.executors:
            message_parts.append(
                f"<b>Исполнители:</b> {', '.join([e.name for e in deal.executors])}"
            )

        final_message = "\n\n".join(part for part in message_parts if part)
        keyboard = get_deal_action_kb(deal_id=deal.id)
        messages_to_send.append({"text": final_message, "reply_markup": keyboard})

        # --- Часть 2: Готовим данные для карты ---
        deal_locations = [
            MapLocation(cadastral_number=obj.cadastral_number, coords=obj.centroid_wgs84)
            for obj in (all_cadastral_objects or [])
            if obj.centroid_wgs84
        ]

        if deal_locations:
            if deal.visit_datetime:
                visit_time_str = (
                    deal.visit_datetime.strftime("%H:%M")
                    if deal.visit_datetime.time() != datetime.min.time()
                    else "Весь день"
                )
            else:
                visit_time_str = "Без времени"

            data_for_map.append(
                MapDealData(
                    deal_id=deal.id,
                    deal_url=deal_url,
                    deal_name=deal.name,
                    visit_time=visit_time_str,
                    executors=[e.name for e in deal.executors],
                    locations=deal_locations,
                )
            )

    # --- Часть 3: После цикла создаем запрос на карту ---
    map_url = None
    if data_for_map:
        try:
            deals_json_string = json.dumps(
                [deal.model_dump() for deal in data_for_map], ensure_ascii=False
            )
            token = await crud.create_map_request(
                session=session,
                user_telegram_id=user_telegram_id,
                deals_data_json=deals_json_string,
                expires_in_minutes=5,
            )
            map_url = urljoin(settings.FRONTEND_BASE_URL, f"/map/{token}")
            logger.info(
                f"Сгенерирована ссылка на карту для пользователя {user_telegram_id}: {map_url}"
            )
        except Exception as e:
            logger.error(f"Не удалось создать запрос на карту: {e}", exc_info=True)
            map_url = None  # В случае ошибки просто не будет ссылки

    return {"messages_to_send": messages_to_send, "map_url": map_url}


async def get_cadastral_data_as_json(description: str, nspd_client: NspdClient) -> str | None:
    """
    Извлекает кадастровые номера из текста, запрашивает по ним данные
    через NspdClient и возвращает результат в виде JSON-строки.

    Args:
        description: Текст для поиска кадастровых номеров.
        nspd_client: Экземпляр клиента для работы с НСПД.

    Returns:
        JSON-строка со списком найденных объектов или None, если ничего не найдено.
    """
    try:
        if not description:
            return None

        # Регулярное выражение для кадастровых номеров (учитывая 1-5 цифр в конце)
        cadastral_num_pattern = re.compile(r"\b\d{2}:\d{2}:\d{6,7}:\d{1,5}\b")

        found_numbers = cadastral_num_pattern.findall(description)

        all_unique_numbers = list(set(found_numbers))

        if not all_unique_numbers:
            logger.info("Кадастровые номера в описании не найдены.")
            return None

        logger.info(f"Найдены КН для обработки: {all_unique_numbers}")

        # Асинхронно запрашиваем информацию по всем найденным номерам
        tasks = [nspd_client.get_object_info(num) for num in all_unique_numbers]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        successful_results: list[CadastralObject] = []
        for i, res in enumerate(results):
            if isinstance(res, CadastralObject):
                successful_results.append(res)
            elif isinstance(res, Exception):
                logger.error(f"Ошибка при запросе КН {all_unique_numbers[i]}: {res}")
            # Если res is None, объект просто не найден, это не считается ошибкой.

        if not successful_results:
            logger.warning("Не удалось получить данные ни по одному из КН.")
            return None

        # Сериализуем успешные результаты в JSON
        data_to_serialize = [obj.model_dump(mode="json") for obj in successful_results]
        json_string = json.dumps(data_to_serialize, ensure_ascii=False)

        logger.info(
            f"Успешно подготовлены данные по {len(successful_results)} кадастровым объектам."
        )
        return json_string

    except Exception as e:
        logger.error(f"Критическая ошибка в задаче обработки КН: {e}", exc_info=True)
        return None
