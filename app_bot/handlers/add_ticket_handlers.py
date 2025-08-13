import asyncio
import logging
from datetime import date, datetime, timedelta
from io import BytesIO

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app_bot.ai_service.perplexity_client import format_ticket_with_perplexity
from app_bot.crm_service.crm_client import CRMClient
from app_bot.database import crud
from app_bot.database.models import Permission
from app_bot.filters.permission_filters import HasPermissionFilter
from app_bot.keyboards.add_ticket_keyboards import (
    AddTicketDateCallback,
    AddTicketTimeCallback,
    get_add_ticket_cancel_kb,
    get_add_ticket_confirmation_kb,
    get_add_ticket_date_kb,
    get_add_ticket_files_kb,
    get_add_ticket_time_kb,
)
from app_bot.nspd_service.nspd_client import NspdClient
from app_bot.utils.ui_utils import get_cadastral_data_as_json, get_main_menu_message


SERVICE_DATA_CRM_FIELD = "Category1000076CustomFieldServiceData"

add_ticket_router = Router()
logger = logging.getLogger(__name__)


class AddTicketFSM(StatesGroup):
    """FSM для процесса создания заявки."""

    waiting_for_visit_date = State()
    waiting_for_custom_date_input = State()  # Новое состояние для ввода произвольной даты
    waiting_for_visit_time = State()
    waiting_for_description = State()
    waiting_for_files = State()
    waiting_for_confirmation = State()


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
        instruction_text = "📅 <b>Создание новой заявки</b>\n\nВыберите дату выезда:"

        await loading_msg.edit_text(text=instruction_text, reply_markup=kb, parse_mode="HTML")
        await state.set_state(AddTicketFSM.waiting_for_visit_date)

    except Exception as e:
        logger.error(f"Ошибка при подготовке меню добавления заявки: {e}", exc_info=True)
        await loading_msg.edit_text(
            "❌ Произошла ошибка при загрузке данных. Попробуйте позже."
        )
        await state.clear()


@add_ticket_router.callback_query(
    AddTicketFSM.waiting_for_visit_date,
    AddTicketDateCallback.filter(F.action == "custom_date"),
    HasPermissionFilter(Permission.CREATE_TICKETS),
)
async def process_custom_date_request(
    query: CallbackQuery,
    state: FSMContext,
):
    """
    Обрабатывает нажатие кнопки "Ввести свою дату".
    Переводит пользователя в состояние ожидания ввода произвольной даты.
    """
    await query.answer()
    
    await query.message.edit_text(
        "📅 <b>Ввод произвольной даты</b>\n\n"
        "Введите дату выезда в од��ом из форматов:\n"
        "• <code>ДД.ММ.ГГГГ</code> (например: 25.12.2024)\n"
        "• <code>ДД.ММ</code> (например: 25.12 - текущий год)\n"
        "• <code>ДД</code> (например: 25 - текущий месяц и год)\n\n"
        "⚠️ Дата не может быть в прошлом.",
        reply_markup=get_add_ticket_cancel_kb(),
        parse_mode="HTML",
    )
    
    await state.set_state(AddTicketFSM.waiting_for_custom_date_input)


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
            f"🔴 <b>Лимит на {target_date.strftime('%d.%m.%Y')} достигнут ({count}/{limit}).</b>\n"
            "Уточните у менеджера возможность добавления заявки сверх лимита. "
            "Добавляемая заявка может быть перенесена на другой срок.",
            parse_mode="HTML",
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
    await loading_msg.answer(
        f"📅 Дата выезда: <b>{target_date.strftime('%d.%m.%Y')}</b>\n\n"
        "🕒 Теперь выберите время выезда:",
        reply_markup=kb,
        parse_mode="HTML",
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
    Обрабатывает выбор времени, предупреждает о занятости и запрашивает описание.
    """
    await query.answer()

    time_from_callback = callback_data.time_str

    warning_message = ""

    if time_from_callback == "any-time":
        visit_time_str = "00:00"
    else:
        # Это код для обработки конкретного времени, он остается
        visit_time_str = time_from_callback.replace("-", ":")

        # Проверку на занятость делаем только для конкретного времени
        try:
            data = await state.get_data()
            visit_date_iso = data.get("visit_date")
            visit_date_obj = date.fromisoformat(visit_date_iso)
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

    await state.update_data(visit_time=visit_time_str)

    data = await state.get_data()
    visit_date_iso = data.get("visit_date")
    visit_date_obj = date.fromisoformat(visit_date_iso)

    # Отображаем "Любое" если было выбрано 00:00, для понятности
    display_time = "Любое" if visit_time_str == "00:00" else visit_time_str

    await query.message.edit_text(
        f"📅 Дата: <b>{visit_date_obj.strftime('%d.%m.%Y')}</b>\n"
        f"🕒 Время: <b>{display_time}</b>"
        f"{warning_message}\n\n"
        "✍️ Теперь введите описание заявки. \n"
        "Постарайтесь указать вид работ, кадастровый номер, адрес и контакты.",
        reply_markup=get_add_ticket_cancel_kb(),
        parse_mode="HTML",
    )

    await state.set_state(AddTicketFSM.waiting_for_description)


@add_ticket_router.message(
    AddTicketFSM.waiting_for_custom_date_input,
    F.text,
    HasPermissionFilter(Permission.CREATE_TICKETS),
)
async def process_custom_date_input(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    crm_client: CRMClient,
):
    """
    Обрабатывает ввод произвольной даты пользователем.
    Парсит дату в различных форматах, проверяет корректность,
    запрашивает данные из CRM и проверяет лимиты.
    """
    user_input = message.text.strip()
    
    # Функция для парсинга даты в различных форматах
    def parse_custom_date(date_str: str) -> date | None:
        """
        Парсит дату в форматах: ДД.ММ.ГГГГ, ДД.ММ, ДД
        Возвращает объект date или None при ошибке.
        """
        today = date.today()
        
        try:
            # Убираем лишние пробелы и разделяем по точке
            parts = [part.strip() for part in date_str.split('.')]
            
            if len(parts) == 3:  # ДД.ММ.ГГГГ
                day, month, year = map(int, parts)
                return date(year, month, day)
            elif len(parts) == 2:  # ДД.ММ (текущий год)
                day, month = map(int, parts)
                return date(today.year, month, day)
            elif len(parts) == 1:  # ДД (текущий месяц и год)
                day = int(parts[0])
                return date(today.year, today.month, day)
            else:
                return None
        except (ValueError, TypeError):
            return None
    
    # Парсим введенную дату
    parsed_date = parse_custom_date(user_input)
    
    if parsed_date is None:
        # Дата некорректна - просим ввести ��щё раз
        await message.answer(
            "❌ <b>Некорректная дата!</b>\n\n"
            "Пожалуйста, введите дату в одном из форматов:\n"
            "• <code>ДД.ММ.ГГГГ</code> (например: 25.12.2024)\n"
            "• <code>ДД.ММ</code> (например: 25.12)\n"
            "• <code>ДД</code> (например: 25)\n\n"
            "Попробуйте ещё раз:",
            reply_markup=get_add_ticket_cancel_kb(),
            parse_mode="HTML",
        )
        return
    
    # Проверяем, что дата не в прошлом
    today = date.today()
    if parsed_date < today:
        await message.answer(
            f"❌ <b>Дата не может быть в прошлом!</b>\n\n"
            f"Вы ввели: <b>{parsed_date.strftime('%d.%m.%Y')}</b>\n"
            f"Сегодня: <b>{today.strftime('%d.%m.%Y')}</b>\n\n"
            "Введите дату не раньше сегодняшнего дня:",
            reply_markup=get_add_ticket_cancel_kb(),
            parse_mode="HTML",
        )
        return
    
    # Дата корректна - показываем загрузку и запрашиваем данные из CRM
    loading_msg = await message.answer("⏳ Проверяю загруженность на выбранную дату...")
    
    try:
        # Запрашиваем данные из CRM для введенной даты
        # Запрашиваем только один день, так как нам нужна информация именно по этой дате
        deals_for_date = await crm_client.get_deals_for_date_range_model(
            start_date=parsed_date, end_date=parsed_date
        )
        if deals_for_date is None:
            deals_for_date = []
        
        # Получаем лимит для этой даты
        limit = await crud.get_actual_limit_for_date(session, parsed_date)
        count = len(deals_for_date)
        
        # Проверяем лимит и выводим предупреждение если нужно
        warning_message = ""
        if count >= limit:
            warning_message = (
                f"\n\n🔴 <b>Внимание!</b> Лимит на {parsed_date.strftime('%d.%m.%Y')} "
                f"уже достигнут: <b>{count}/{limit}</b> заявок.\n"
                "Ваша заявка будет создана, но потребуется согласование с менеджером. "
                "Введенная дата может быть перенесена менеджером."
            )
        
        # Сохраняем дату в state и переходим к выбору времени
        await state.update_data(visit_date=parsed_date.isoformat())
        
        # Получаем количество бригад для расчета занятости времени
        brigades_count = await crud.get_actual_brigades_for_date(session, parsed_date)
        
        # Извлекаем занятые временные слоты
        occupied_slots = []
        if deals_for_date:
            # Сериализуем сделки для сохранения в state (как в оригинальном коде)
            deals_as_dicts = [deal.model_dump(mode="json") for deal in deals_for_date]
            await state.update_data(deals_on_period=deals_as_dicts)
            
            occupied_slots = [
                datetime.fromisoformat(deal_dict["visit_datetime"]).strftime("%H:%M")
                for deal_dict in deals_as_dicts
                if deal_dict.get("visit_datetime")
            ]
        else:
            # Если нет сделок, сохраняем пустой список
            await state.update_data(deals_on_period=[])
        
        # Создаем клавиатуру для выбора времени
        kb = get_add_ticket_time_kb(occupied_slots=occupied_slots, brigades_count=brigades_count)
        
        await loading_msg.edit_text(
            f"📅 Дата выезда: <b>{parsed_date.strftime('%d.%m.%Y')}</b> "
            f"({count}/{limit} заявок){warning_message}\n\n"
            "🕒 Теперь выберите время выезда:",
            reply_markup=kb,
            parse_mode="HTML",
        )
        
        await state.set_state(AddTicketFSM.waiting_for_visit_time)
        
    except Exception as e:
        logger.error(f"Ошибка при обработке произвольной даты {parsed_date}: {e}", exc_info=True)
        await loading_msg.edit_text(
            "❌ Произошла ошибка при проверке даты. Попробуйте ещё раз или выберите другую дату:",
            reply_markup=get_add_ticket_cancel_kb(),
        )


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

    await query.message.answer(
        "🖥️ <b>Заявка без выезда.</b>\n\n"
        "✍️ Введите описание заявки. \n"
        "Постарайтесь указать кадастровый номер, адрес и контакты.",
        reply_markup=get_add_ticket_cancel_kb(),
        parse_mode="HTML",
    )

    await state.set_state(AddTicketFSM.waiting_for_description)


@add_ticket_router.message(
    AddTicketFSM.waiting_for_description,
    F.text,
    HasPermissionFilter(Permission.CREATE_TICKETS),
)
async def process_description(message: Message, state: FSMContext):
    """
    Ловит описание заявки, сохраняет его и предлагает прикрепить файлы.
    """

    deal_description = message.text

    await state.update_data(
        deal_description=deal_description,
        attached_files=[],  # Инициализируем пустой список для файлов
    )

    kb = get_add_ticket_files_kb()
    await message.answer(
        "📝 <b>Описание принято.</b>\n\n"
        "Теперь вы можете прикрепить к заявке файлы (фото, документы).\n"
        "Отправьте их в чат по одному или альбомом.\n\n"
        "Когда закончите, нажмите <b>«Завершить»</b>. "
        "Если файлы не нужны, нажмите <b>«Пропустить»</b>.",
        reply_markup=kb,
        parse_mode="HTML",
    )

    await state.set_state(AddTicketFSM.waiting_for_files)


MAX_FILE_SIZE = 25 * 1024 * 1024


@add_ticket_router.message(
    AddTicketFSM.waiting_for_files,
    F.content_type.in_({"photo", "document", "video"}),
    HasPermissionFilter(Permission.CREATE_TICKETS),
)
async def process_file_attachment(message: Message, state: FSMContext):
    """
    Ловит отправленный пользователем файл, проверяет его размер
    и сохраняет его file_id в FSM.
    """
    file_id = None
    file_name = "Неизвестный файл"
    file_size = 0

    if message.photo:
        file_id = message.photo[-1].file_id
        file_name = f"Фото_{file_id[:6]}.jpg"
        file_size = message.photo[-1].file_size
    elif message.document:
        file_id = message.document.file_id
        file_name = message.document.file_name or "Документ"
        file_size = message.document.file_size
    elif message.video:
        file_id = message.video.file_id
        file_name = message.video.file_name or f"Видео_{file_id[:6]}.mp4"
        file_size = message.video.file_size

    if not file_id:
        await message.answer("Не удалось обработать файл. Попробуйте другой.")
        return

    if file_size and file_size > MAX_FILE_SIZE:
        error_msg = (
            f"❌ <b>Файл «{file_name}» слишком большой</b> ({file_size / 1024 / 1024:.2f} МБ).\n"
            "Он не будет прикреплен к заявке. Лимит Telegram Bot API — 25 МБ.\n\n"
            "Пожалуйста, после создания заявки загрузите его вручную через веб-интерфейс CRM."
        )
        await message.answer(
            error_msg, reply_markup=get_add_ticket_files_kb(), parse_mode="HTML"
        )
        return  # Важно прервать выполнение, чтобы не сохранять file_id

    data = await state.get_data()
    current_files = data.get("attached_files", [])

    current_files.append({"file_id": file_id, "file_name": file_name})

    await state.update_data(attached_files=current_files)

    await message.answer(
        f"✅ Файл «{file_name}» принят.\nМожете отправить следующий или нажать на кнопку ниже.",
        reply_markup=get_add_ticket_files_kb(),
    )


@add_ticket_router.callback_query(
    AddTicketFSM.waiting_for_files,
    F.data.in_({"add_ticket_files_done", "add_ticket_skip_files"}),
    HasPermissionFilter(Permission.CREATE_TICKETS),
)
async def process_files_done_or_skip(query: CallbackQuery, state: FSMContext):
    """
    Переводит на финальный шаг подтверждения после добавления файлов или их пропуска.
    """
    await query.answer()

    data = await state.get_data()

    # Собираем информацию для итогового сообщения
    deal_description = data.get("deal_description", "Без описания")
    visit_date_iso = data.get("visit_date")
    visit_time = data.get("visit_time")
    attached_files = data.get("attached_files", [])

    # Формируем текст
    summary_parts = ["🔔 <b>Проверьте данные перед созданием заявки:</b>\n"]

    if visit_date_iso and visit_time:
        visit_date = date.fromisoformat(visit_date_iso)
        display_time = "Любое" if visit_time == "00:00" else visit_time
        summary_parts.append(
            f"<b>Дата и время:</b> {visit_date.strftime('%d.%m.%Y')}, {display_time}"
        )
    else:
        summary_parts.append("<b>Дата и время:</b> Без выезда")

    summary_parts.append(f"<b>Описание:</b>\n{deal_description}")

    if attached_files:
        files_list = "\n".join([f" - 📎 {f['file_name']}" for f in attached_files])
        summary_parts.append(
            f"\n<b>Прикрепленные файлы ({len(attached_files)}):</b>\n{files_list}"
        )
    else:
        summary_parts.append("\n<b>Прикрепленные файлы:</b> нет")

    summary_text = "\n".join(summary_parts)

    kb = get_add_ticket_confirmation_kb()
    await query.message.edit_text(
        summary_text, reply_markup=kb, disable_web_page_preview=True, parse_mode="HTML"
    )

    await state.set_state(AddTicketFSM.waiting_for_confirmation)


@add_ticket_router.callback_query(
    AddTicketFSM.waiting_for_confirmation,
    F.data == "add_ticket_confirm_create",
    HasPermissionFilter(Permission.CREATE_TICKETS),
)
async def process_confirmation(
    query: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    crm_client: CRMClient,
    bot: Bot,
    nspd_client: NspdClient,  # Добавляем nspd_client из middleware
):
    """
    Обрабатывает финальное подтверждение создания заявки.
    1. Создает сделку с "сырыми" данными и прикрепляет файлы.
    2. Сразу показывает пользователю созданную сделку.
    3. В фоне запускает улучшение с помощью AI и поиск кадастровых номеров.
    4. Собирает результаты фоновых задач и ОДНИМ запросом обновляет сделку.
    """
    await query.message.edit_text("⏳ Начинаю создание заявки...")
    await query.answer()

    data = await state.get_data()
    user = await crud.get_user_by_telegram_id(session, query.from_user.id)
    if not user or not user.megaplan_user_id:
        await query.message.answer("❌ Ошибка: ваш профиль не привязан к сотруднику CRM.")
        await state.clear()
        return

    deal_id = None
    status_msg = None  # Инициализируем переменную для статусного сообщения

    try:
        # --- Шаг 1: Создание сделки с СЫРЫМИ данными ---
        visit_datetime_obj = None
        visit_date_iso = data.get("visit_date")
        visit_time_str = data.get("visit_time")
        if visit_date_iso and visit_time_str:
            visit_date = date.fromisoformat(visit_date_iso)
            hour, minute = map(int, visit_time_str.split(":"))
            visit_datetime_obj = datetime.combine(visit_date, datetime.min.time()).replace(
                hour=hour, minute=minute
            )

        raw_full_description = data.get("deal_description", "")
        lines = raw_full_description.split("\n", 1)
        deal_name_for_crm = lines[0].strip()
        deal_description_for_crm = raw_full_description

        created_deal = await crm_client.create_deal(
            name=deal_name_for_crm,
            description=deal_description_for_crm,
            ticket_visit_datetime=visit_datetime_obj,
            megaplan_user_id=user.megaplan_user_id,
        )

        if not created_deal or "id" not in created_deal:
            raise Exception("CRM не вернуло данные о созданной сделке.")

        deal_id = created_deal["id"]

        # --- Шаг 2: Прикрепление файлов (если есть) ---
        attached_files = data.get("attached_files", [])
        if attached_files:
            await query.message.edit_text(
                f"✅ Заявка #{deal_id} создана.\n⏳ Загружаю {len(attached_files)} файлов..."
            )
            crm_file_ids = []
            for file_info in attached_files:
                try:
                    file_io = BytesIO()
                    await bot.download(file_info["file_id"], destination=file_io)
                    file_bytes = file_io.getvalue()

                    uploaded_file = await crm_client.upload_file_from_bytes(
                        file_content=file_bytes, file_name=file_info["file_name"]
                    )
                    if uploaded_file and "id" in uploaded_file:
                        crm_file_ids.append(uploaded_file["id"])
                except Exception as e:
                    logger.error(
                        f"Не удалось обработать файл {file_info['file_name']} для сделки {deal_id}: {e}"
                    )

            if crm_file_ids:
                await crm_client.attach_files_to_deal_main_attachments(deal_id, crm_file_ids)

        # --- Шаг 3: Показ "сырой" заявки пользователю ---
        deal_url = f"{crm_client.base_url}deals/{deal_id}/card/"
        raw_deal_message_parts = ["✅ <b>Заявка успешно создана!</b>"]

        if visit_date_iso and visit_time_str:
            visit_date = date.fromisoformat(visit_date_iso)
            display_time = "Любое" if visit_time_str == "00:00" else visit_time_str
            raw_deal_message_parts.append(
                f"🚗 <b>Выезд:</b> {visit_date.strftime('%d.%m.%Y')}, {display_time}"
            )
        else:
            raw_deal_message_parts.append("🖥️ <b>Заявка без выезда</b>")

        raw_deal_message_parts.append(data.get("deal_description", "Нет описания."))
        raw_deal_message_parts.append(f"\n<a href='{deal_url}'>Перейти к сделке #{deal_id}</a>")

        await query.message.edit_text(
            text="\n".join(raw_deal_message_parts),
            disable_web_page_preview=True,
            parse_mode="HTML",
        )

        # --- Шаг 4: Запуск фоновых задач и единое обновление ---
        status_msg = await query.message.answer(
            "⏳ Улучшаю заявку с помощью AI и ищу кадастровые номера..."
        )

        raw_description_for_background = data.get("deal_description", "")

        if raw_description_for_background:
            # Создаем обе фоновые задачи
            task_ai = format_ticket_with_perplexity(raw_description_for_background)
            task_cadastral = get_cadastral_data_as_json(
                raw_description_for_background, nspd_client
            )

            # Запускаем их параллельно и ждем результатов
            ai_result, cadastral_json_string = await asyncio.gather(
                task_ai, task_cadastral, return_exceptions=True
            )

            # Готовим единый payload для обновления
            update_payload = {}

            # Обрабатываем результат от AI
            if isinstance(ai_result, dict):
                new_name = ai_result.get("name")
                new_description = ai_result.get("description")
                if new_name and new_description:
                    update_payload["name"] = new_name
                    update_payload["description"] = new_description
            elif isinstance(ai_result, Exception):
                logger.error(
                    f"Ошибка на этапе форматирования AI для сделки {deal_id}: {ai_result}"
                )

            # Обрабатываем результат от НСПД
            if isinstance(cadastral_json_string, str):
                update_payload[SERVICE_DATA_CRM_FIELD] = cadastral_json_string
            elif isinstance(cadastral_json_string, Exception):
                logger.error(
                    f"Ошибка на этапе получения кадастровых данных для сделки {deal_id}: {cadastral_json_string}"
                )

            # Если есть что обновлять, делаем один запрос в CRM
            if update_payload:
                await crm_client.update_deal(deal_id, update_payload)
                logger.info(f"Сделка {deal_id} успешно обновлена фоновыми данными.")
            else:
                logger.info(f"Для сделки {deal_id} не было данных для фонового обновления.")

    except Exception as e_main:
        logger.error(f"Критическая ошибка при создании сделки: {e_main}", exc_info=True)
        deal_id_str = f" (ID сделки: {deal_id})" if deal_id else ""
        error_text = f"❌ Произошла ошибка при создании заявки{deal_id_str}. Свяжитесь с администратором."
        # Проверяем, было ли уже отредактировано сообщение, чтобы избежать ошибки
        try:
            await query.message.edit_text(error_text)
        except Exception:
            await query.message.answer(error_text)

    finally:
        # --- Шаг 5: Очистка и возврат в меню ---
        if status_msg:
            await status_msg.delete()  # Удаляем сообщение "Улучшаю заявку..."

        await state.clear()
        # Вызываем меню как новое сообщение, чтобы не редактировать сообщение со сделкой
        await get_main_menu_message(query.message, session, crm_client)


@add_ticket_router.callback_query(F.data == "add_ticket_cancel")
async def cancel_add_ticket_date_step(
    query: CallbackQuery, state: FSMContext, session: AsyncSession, crm_client: CRMClient
):
    """Отменяет процесс создания заявки и возвращает в главное меню."""
    await state.clear()
    await query.answer("Действие отменено")
    # Редактируем сообщение, чтобы убрать клавиатуру и показать, что мы в меню
    await get_main_menu_message(query.message, session, crm_client)
