from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app_bot.config.config import get_env_settings
from app_bot.crm_service.crm_client import CRMClient
from app_bot.nspd_service.nspd_client import NspdClient
from app_bot.utils.ui_utils import get_and_format_deals_from_crm, get_main_menu_message
from app_bot.utils.ui_utils import get_main_menu_message, prepare_deal_view_data


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
    query: CallbackQuery,
    crm_client: CRMClient,
    session: AsyncSession,
    nspd_client: NspdClient,
):
    await query.message.answer("Загружаю заявки на сегодня...")
    await query.answer()

    today = datetime.now().date()
    # 1. Вызываем новую универсальную функцию
    result = await prepare_deal_view_data(
        crm_client=crm_client,
        start_date=today,
        end_date=today,
        nspd_client=nspd_client,
        session=session,
        user_telegram_id=query.from_user.id,
    )

    # 2. Отправляем сообщения со сделками
    for item in result["messages_to_send"]:
        await query.message.answer(
            text=item["text"],
            reply_markup=item["reply_markup"],
            disable_web_page_preview=True,
        )

    # 3. Отправляем ссылку на карту, если она есть
    map_url = result.get("map_url")
    if map_url:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="📍 Открыть карту выездов", url=map_url)]]
        )
        await query.message.answer(
            "🗺️ <b>Карта выездов готова!</b>\n\n"
            "Нажмите на кнопку ниже, чтобы открыть интерактивную карту.\n"
            "<i>Ссылка действительна 5 минут.</i>",
            reply_markup=kb,
        )

    # 4. Возвращаем в главное меню
    await get_main_menu_message(query.message, session, crm_client)


@view_tickets_router.callback_query(F.data == "view_tickets_tomorrow")
async def view_tomorrow_deals_handler(
    query: CallbackQuery,
    crm_client: CRMClient,
    session: AsyncSession,
    # Добавляем nspd_client в параметры
    nspd_client: NspdClient,
):
    await query.message.answer("Загружаю заявки на завтра...")
    await query.answer()

    tomorrow = datetime.now(APP_TIMEZONE).date() + timedelta(days=1)

    # Вызываем универсальную функцию, передавая nspd_client
    messages_to_send = await get_and_format_deals_from_crm(
        crm_client=crm_client, start_date=tomorrow, end_date=tomorrow, nspd_client=nspd_client
    )

    # Отправляем все, что она вернула
    for item in messages_to_send:
        await query.message.answer(
            text=item["text"],
            reply_markup=item["reply_markup"],
            disable_web_page_preview=True,
        )

    # Возвращаем в главное меню
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
    message: Message,
    state: FSMContext,
    crm_client: CRMClient,
    session: AsyncSession,
    # Добавляем nspd_client в параметры
    nspd_client: NspdClient,
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

    # Вызываем универсальную функцию, передавая nspd_client
    messages_to_send = await get_and_format_deals_from_crm(
        crm_client=crm_client,
        start_date=target_date,
        end_date=target_date,
        nspd_client=nspd_client,
    )

    # Отправляем сообщения пользователю
    for item in messages_to_send:
        await message.answer(
            text=item["text"],
            reply_markup=item["reply_markup"],
            disable_web_page_preview=True,
        )

    # Возвращаемся в главное меню, чтобы пользователь мог продолжить работу
    await get_main_menu_message(message, session, crm_client)
