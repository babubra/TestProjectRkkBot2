from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app_bot.config.config import get_env_settings
from app_bot.crm_service.crm_client import CRMClient
from app_bot.utils.ui_utils import get_and_format_deals_from_crm, get_main_menu_message


view_tickets_router = Router()

settings = get_env_settings()
APP_TIMEZONE = timezone(timedelta(hours=settings.APP_TIMEZONE_OFFSET))


class ViewTicketsByDateFSM(StatesGroup):
    """
    Машина состояний для процесса просмотра заявок на определенную дату.
    """

    waiting_for_date = State()


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


@view_tickets_router.callback_query(F.data == "view_tickets_other_date")
async def view_other_date_deals_start(query: CallbackQuery, state: FSMContext):
    """
    Запускает процесс просмотра заявок на другую дату.
    Запрашивает у пользователя дату.
    """
    await query.answer()
    await query.message.answer("Введите дату в формате <b>ДД.ММ.ГГГГ</b> для просмотра заявок.")
    await state.set_state(ViewTicketsByDateFSM.waiting_for_date)


@view_tickets_router.message(ViewTicketsByDateFSM.waiting_for_date, F.text)
async def process_date_for_view(
    message: Message, state: FSMContext, crm_client: CRMClient, session: AsyncSession
):
    """
    Обрабатывает введенную пользователем дату, загружает и отображает заявки.
    """
    await state.clear()
    try:
        # Преобразуем введенный текст в объект даты
        target_date = datetime.strptime(message.text.strip(), "%d.%m.%Y").date()
    except ValueError:
        await message.answer(
            "❌ <b>Ошибка:</b> Неверный формат даты. Пожалуйста, используйте <b>ДД.ММ.ГГГГ</b>."
        )
        # Так как FSM уже очищен, просто возвращаемся в главное меню
        await get_main_menu_message(message, session, crm_client)
        return

    await message.answer(f"⏳ Загружаю заявки на <b>{target_date.strftime('%d.%m.%Y')}</b>...")

    # Вызываем универсальную функцию для получения и форматирования сделок
    messages_to_send = await get_and_format_deals_from_crm(
        crm_client=crm_client, start_date=target_date, end_date=target_date
    )

    # Отправляем сообщения пользователю
    if messages_to_send:
        for item in messages_to_send:
            await message.answer(
                text=item["text"],
                reply_markup=item["reply_markup"],
                disable_web_page_preview=True,
            )

    # Возвращаемся в главное меню, чтобы пользователь мог продолжить работу
    await get_main_menu_message(message, session, crm_client)
