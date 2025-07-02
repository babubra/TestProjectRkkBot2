from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app_bot.config.config import get_env_settings
from app_bot.crm_service.crm_client import CRMClient
from app_bot.utils.ui_utils import get_and_format_deals_from_crm, get_main_menu_message


view_tickets_router = Router()

settings = get_env_settings()
APP_TIMEZONE = timezone(timedelta(hours=settings.APP_TIMEZONE_OFFSET))


@view_tickets_router.callback_query(F.data == "view_tickets_today")
async def view_today_deals_handler(
    query: CallbackQuery, crm_client: CRMClient, session: AsyncSession
):
    await query.message.answer("Загружаю заявки на сегодня...")
    await query.answer()

    today = datetime.now().date()

    # 1. Вызываем функцию загрузки, которая вернет список словарей
    messages_to_send = await get_and_format_deals_from_crm(
        crm_client=crm_client, start_date=today, end_date=today
    )

    # 2. Отправляем все, что она вернула, используя распаковку словаря
    for item in messages_to_send:
        await query.message.answer(
            text=item["text"],
            reply_markup=item["reply_markup"],
            disable_web_page_preview=True,
        )

    # 3. Возвращаем в главное меню
    await get_main_menu_message(query.message, session, crm_client)


@view_tickets_router.callback_query(F.data == "view_tickets_tomorrow")
async def view_tomorrow_deals_handler(
    query: CallbackQuery, crm_client: CRMClient, session: AsyncSession
):
    await query.message.answer("Загружаю заявки на завтра...")
    await query.answer()

    tomorrow = datetime.now(APP_TIMEZONE).date() + timedelta(days=1)

    # 1. Вызываем ту же универсальную функцию
    messages_to_send = await get_and_format_deals_from_crm(
        crm_client=crm_client, start_date=tomorrow, end_date=tomorrow
    )

    # 2. Отправляем все, что она вернула
    for item in messages_to_send:
        await query.message.answer(
            text=item["text"],
            reply_markup=item["reply_markup"],
            disable_web_page_preview=True,
        )

    # 3. Возвращаем в главное меню
    await get_main_menu_message(query.message, session, crm_client)
