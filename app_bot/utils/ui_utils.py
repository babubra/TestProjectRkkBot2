import logging
import re
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urljoin

from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app_bot.config.config import get_env_settings
from app_bot.crm_service.crm_client import CRMClient
from app_bot.database import crud
from app_bot.keyboards.common_keyboards import get_main_menu_kb
from app_bot.keyboards.view_ticket_keyboards import get_deal_action_kb


logger = logging.getLogger(__name__)
settings = get_env_settings()
APP_TIMEZONE = timezone(timedelta(hours=settings.APP_TIMEZONE_OFFSET))


async def get_main_menu_message(message: Message, session: AsyncSession, crm_client: CRMClient):
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
DEFAULT_STATUS_ICON = "🟢"  # Иконка по умолчанию - выезд завершен успешно


def strip_html_tags(text: str) -> str:
    """
    Удаляет HTML-теги из строки для чистого отображения в Telegram.
    """
    if not text:
        return ""
    # Простое регулярное выражение для удаления тегов
    return re.sub("<[^<]+?>", "", text).strip()


async def get_and_format_deals_from_crm(
    crm_client: CRMClient, start_date: date, end_date: date
) -> list[dict]:
    """
    Универсальная функция для получения и форматирования списка сделок за период.
    Возвращает список словарей, где каждый словарь содержит 'text' и 'reply_markup'.
    """
    logger.info(f"Запрос и форматирование сделок для диапазона: {start_date} - {end_date}")

    deals = await crm_client.get_deals_for_date_range_model(
        start_date=start_date, end_date=end_date
    )

    if not deals:
        # Возвращаем словарь, чтобы соответствовать новому формату
        return [{"text": "✅ На выбранную дату заявок не найдено.", "reply_markup": None}]

    formatted_messages = []
    for deal in deals:
        message_parts = []
        # ... (весь ваш код по формированию message_parts остается без изменений) ...
        # --- 1. Формируем заголовок со ссылкой и датой ---
        icon = DEAL_STATUS_ICONS.get(deal.state.id, DEFAULT_STATUS_ICON)
        if deal.visit_result and isinstance(deal.visit_result, str):
            stripped_result = deal.visit_result.strip()
            if stripped_result:
                secondary_icon = stripped_result[0]
                icon += secondary_icon

        deal_url = urljoin(crm_client.base_url, f"/deals/{deal.id}/card/")
        link_text = f"{icon} Сделка {deal.id}."
        header_link = f'<a href="{deal_url}">{link_text}</a>'

        visit_date_str = ""
        if deal.visit_datetime:
            if deal.visit_datetime.time() == datetime.min.time():
                format_string = "%d.%m.%Y"
            else:
                format_string = "%d.%m.%Y %H:%M"
            visit_date_str = f"<b>{deal.visit_datetime.strftime(format_string)}</b>"

        full_header = f"{header_link} {visit_date_str}".strip()
        message_parts.append(full_header)

        # --- 2. Название сделки ---
        message_parts.append(f"<b>{deal.name}</b>")

        # --- 3. Описание сделки ---
        if deal.description:
            clean_description = strip_html_and_preserve_breaks(deal.description)
            if clean_description:
                message_parts.append(clean_description)

        # --- 4. Исполнители ---
        if deal.executors:
            executor_names = ", ".join([e.name for e in deal.executors])
            message_parts.append(f"<b>Исполнители:</b> {executor_names}")

        # --- 5. Файлы со ссылками ---
        if deal.files_for_visit:
            file_links = []
            for file in deal.files_for_visit:
                file_url = urljoin(crm_client.base_url, f"{file.path}")
                file_links.append(f'<a href="{file_url}">{file.name}</a>')

            files_str = "\n".join(file_links)
            message_parts.append(f"<b>Файлы:</b>\n{files_str}")

        final_message = "\n".join(message_parts)

        # --- Собираем клавиатуру и добавляем всё в итоговый список ---
        keyboard = get_deal_action_kb(deal_id=deal.id)
        formatted_messages.append({"text": final_message, "reply_markup": keyboard})

    return formatted_messages
