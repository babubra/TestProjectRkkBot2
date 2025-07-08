import logging
from datetime import date, datetime, timedelta

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app_bot.crm_service.crm_client import CRMClient
from app_bot.crm_service.schemas import Deal
from app_bot.database import crud
from app_bot.database.models import Permission
from app_bot.filters.permission_filters import HasPermissionFilter
from app_bot.keyboards.add_ticket_keyboards import (
    AddTicketDateCallback,
    AddTicketTimeCallback,
    get_add_ticket_date_kb,
    get_add_ticket_time_kb,
)
from app_bot.utils.ui_utils import get_main_menu_message


add_ticket_router = Router()
logger = logging.getLogger(__name__)


class AddTicketFSM(StatesGroup):
    """FSM для процесса создания заявки."""

    waiting_for_visit_date = State()
    waiting_for_visit_time = State()
    waiting_for_description = State()
    # waiting_for_files = State()
    # waiting_for_confirmation = State()


@add_ticket_router.callback_query(
    F.data == "add_ticket", HasPermissionFilter(Permission.CREATE_TICKETS)
)
async def start_add_ticket(
    query: CallbackQuery, state: FSMContext, session: AsyncSession, crm_client: CRMClient
):
    """
    Начинает процесс создания заявки.
    Запускает FSM и показывает клавиатуру для выбора даты.
    """
    await query.answer()
    loading_msg = await query.message.answer("⏳ Загружаю меню добавления заявки, подождите...")

    try:
        today = date.today()
        end_date_for_fetch = today + timedelta(days=4)

        deals_for_period = await crm_client.get_deals_for_date_range_model(
            start_date=today, end_date=end_date_for_fetch
        )
        if deals_for_period is None:
            deals_for_period = []

        # --- Сериализуем сделки для сохранения в state ---
        # FSM не может хранить сложные объекты Pydantic, поэтому конвертируем их в словари
        deals_as_dicts = [deal.model_dump(mode="json") for deal in deals_for_period]
        await state.update_data(deals_on_period=deals_as_dicts)

        daily_stats = {}
        for i in range(5):
            current_date = today + timedelta(days=i)
            # Считаем сделки по уже загруженным данным
            count = sum(
                1
                for deal_dict in deals_as_dicts
                # Сравниваем даты напрямую из словарей
                if deal_dict.get("visit_datetime")
                and date.fromisoformat(deal_dict["visit_datetime"][:10]) == current_date
            )
            limit = await crud.get_actual_limit_for_date(session, current_date)
            daily_stats[current_date] = (count, limit)

        kb = get_add_ticket_date_kb(daily_stats)
        instruction_text = "📅 **Создание новой заявки**\n\nВыберите дату выезда:"

        await loading_msg.edit_text(text=instruction_text, reply_markup=kb)
        await state.set_state(AddTicketFSM.waiting_for_visit_date)

    except Exception as e:
        logger.error(f"Ошибка при подготовке меню добавления заявки: {e}", exc_info=True)
        await loading_msg.edit_text(
            "❌ Произошла ошибка при загрузке данных. Попробуйте позже."
        )
        await state.clear()


@add_ticket_router.callback_query(
    AddTicketFSM.waiting_for_visit_date,
    AddTicketDateCallback.filter(F.action == "select_date"),
    HasPermissionFilter(Permission.CREATE_TICKETS),
)
async def process_visit_date(
    query: CallbackQuery,
    callback_data: AddTicketDateCallback,
    state: FSMContext,
    session: AsyncSession,
    crm_client: CRMClient,
):
    """
    Обрабатывает выбор даты, проверяет лимиты и запрашивает время.
    """
    await query.answer()
    loading_msg = await query.message.answer("⏳ Начинаю добавление, подождите...")

    target_date = date.fromisoformat(callback_data.date_iso)

    # --- Повторная проверка общего лимита на день ---
    fsm_data = await state.get_data()
    all_deals_dicts = fsm_data.get("deals_on_period", [])

    deals_on_date_dicts = [
        deal_dict
        for deal_dict in all_deals_dicts
        if deal_dict.get("visit_datetime")
        and date.fromisoformat(deal_dict["visit_datetime"][:10]) == target_date
    ]

    limit = await crud.get_actual_limit_for_date(session, target_date)
    count = len(deals_on_date_dicts)

    if count >= limit:
        await loading_msg.edit_text(
            f"🔴 **Лимит на {target_date.strftime('%d.%m.%Y')} достигнут ({count}/{limit}).**\n"
            "Уточните у менеджера возможность добавления заявки сверх лимита. "
            "Добавляемая заявка может быть перенесена на другой срок."
        )
        # Оставляем пользователя в том же состоянии, чтобы он мог выбрать другую дату

    # --- Лимит в порядке, переходим к следующему шагу ---
    await state.update_data(visit_date=target_date.isoformat())
    brigades_count = await crud.get_actual_brigades_for_date(session, target_date)

    # Извлекаем время из словарей
    occupied_slots = [
        datetime.fromisoformat(deal_dict["visit_datetime"]).strftime("%H:%M")
        for deal_dict in deals_on_date_dicts
        if deal_dict.get("visit_datetime")
    ]

    kb = get_add_ticket_time_kb(occupied_slots=occupied_slots, brigades_count=brigades_count)
    await loading_msg.edit_text(
        f"📅 Дата выезда: <b>{target_date.strftime('%d.%m.%Y')}</b>\n\n"
        "🕒 Теперь выберите время выезда:",
        reply_markup=kb,
    )

    await state.set_state(AddTicketFSM.waiting_for_visit_time)


@add_ticket_router.callback_query(
    AddTicketFSM.waiting_for_visit_time,
    AddTicketTimeCallback.filter(F.action == "select_time"),
    HasPermissionFilter(Permission.CREATE_TICKETS),
)
async def process_visit_time(
    query: CallbackQuery,
    callback_data: AddTicketTimeCallback,
    state: FSMContext,
    session: AsyncSession,
):
    """
    Обрабатывает выбор времени и запрашивает описание заявки.
    """
    await query.answer()
    # Получаем "08-00" и просто заменяем "-" на ":"
    time_from_callback = callback_data.time_str
    visit_time_str = time_from_callback.replace("-", ":")

    # Сохраняем в state уже красивое время "08:00"
    await state.update_data(visit_time=visit_time_str)

    # Получаем уже сохраненную дату для красивого отображения
    data = await state.get_data()
    visit_date_iso = data.get("visit_date")
    visit_date_obj = date.fromisoformat(visit_date_iso)

    warning_message = ""
    try:
        all_deals_dicts = data.get("deals_on_period", [])

        deals_on_date_dicts = [
            deal_dict
            for deal_dict in all_deals_dicts
            if deal_dict.get("visit_datetime")
            and date.fromisoformat(deal_dict["visit_datetime"][:10]) == visit_date_obj
        ]

        occupied_slots = [
            datetime.fromisoformat(deal_dict["visit_datetime"]).strftime("%H:%M")
            for deal_dict in deals_on_date_dicts
            if deal_dict.get("visit_datetime")
        ]

        brigades_count = await crud.get_actual_brigades_for_date(session, visit_date_obj)
        occupation_count = occupied_slots.count(visit_time_str)

        if occupation_count >= brigades_count:
            warning_message = (
                f"\n\n🔴 <b>Внимание!</b> На <b>{visit_time_str}</b> уже записано "
                f"<b>{occupation_count}</b> из <b>{brigades_count}</b> возможных заявок. "
                "Ваша заявка будет создана, но менеджер может изменить время выезда."
            )
    except Exception as e:
        logger.error(f"Ошибка при проверке занятости слота: {e}", exc_info=True)

    # Переходим к следующему шагу - вводу описания
    # Мы добавляем `warning_message` в итоговый текст.
    # Если он пустой, ничего не добавится. Если не пустой - он отобразится.
    await query.message.edit_text(
        f"📅 Дата: <b>{visit_date_obj.strftime('%d.%m.%Y')}</b>\n"
        f"🕒 Время: <b>{visit_time_str}</b>"
        f"{warning_message}\n\n"
        "✍️ Теперь введите описание заявки. \n"
        "Постарайтесь указать вид работ, кадастровый номер, адрес и контакты."
    )

    await state.set_state(AddTicketFSM.waiting_for_description)


@add_ticket_router.callback_query(
    F.data == "add_ticket_no_visit",
    AddTicketFSM.waiting_for_visit_date,
    HasPermissionFilter(Permission.CREATE_TICKETS),
)
async def process_no_visit(query: CallbackQuery, state: FSMContext):
    """
    Обрабатывает случай, когда выезд не требуется.
    Пропускает шаги выбора даты и времени.
    """
    await query.answer()

    # Сохраняем информацию, что дата/время не требуется
    await state.update_data(visit_date=None, visit_time=None)

    # ЗАГЛУШКА: переходим сразу к описанию
    await query.message.edit_text(
        "🖥️ **Заявка без выезда.**\n\n"
        "✍️ Введите описание заявки. \n"
        "Постарайтесь указать кадастровый номер, адрес и контакты."
    )

    await state.set_state(
        AddTicketFSM.waiting_for_description
    )  # <-- Устанавливаем новое состояние


@add_ticket_router.callback_query(F.data == "add_ticket_cancel")
async def cancel_add_ticket_date_step(
    query: CallbackQuery, state: FSMContext, session: AsyncSession, crm_client: CRMClient
):
    """Отменяет процесс создания заявки и возвращает в главное меню."""
    await state.clear()
    await query.answer("Действие отменено")
    await get_main_menu_message(query.message, session, crm_client)
