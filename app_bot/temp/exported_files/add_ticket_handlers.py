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
from app_bot.crm_service.schemas import Deal
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
from app_bot.utils.ui_utils import get_main_menu_message


add_ticket_router = Router()
logger = logging.getLogger(__name__)


class AddTicketFSM(StatesGroup):
    """FSM для процесса создания заявки."""

    waiting_for_visit_date = State()
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
    await loading_msg.edit_text(
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

    description_text = message.text

    # --- ЗАГЛУШКА для AI-логики ---
    # В будущем здесь будет вызов AI, который вернет name и description
    # А пока просто берем первую строку как название, а все остальное как описание
    lines = description_text.split("\n")
    deal_name = lines[0].strip()
    if len(deal_name) > 150:  # Ограничим длину названия
        deal_name = deal_name[:150] + "..."

    deal_description = description_text
    # --- КОНЕЦ ЗАГЛУШКИ ---

    await state.update_data(
        deal_name=deal_name,
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

    # ЗАГЛУШКА для финального шага
    # Здесь мы будем формировать и показывать итоговое сообщение со всеми данными

    data = await state.get_data()

    # Собираем информацию для итогового сообщения
    deal_name = data.get("deal_name", "Без названия")
    deal_description = data.get("deal_description", "Без описания")
    visit_date_iso = data.get("visit_date")
    visit_time = data.get("visit_time")
    attached_files = data.get("attached_files", [])

    # Формируем текст
    summary_parts = [f"🔔 <b>Проверьте данные перед созданием заявки:</b>\n"]

    if visit_date_iso and visit_time:
        visit_date = date.fromisoformat(visit_date_iso)
        display_time = "Любое" if visit_time == "00:00" else visit_time
        summary_parts.append(
            f"<b>Дата и время:</b> {visit_date.strftime('%d.%m.%Y')}, {display_time}"
        )
    else:
        summary_parts.append("<b>Дата и время:</b> Без выезда")

    summary_parts.append(f"<b>Название:</b> {deal_name}")
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


# Файл: app_bot/handlers/add_ticket_handlers.py

# ... (все импорты и хендлеры до этого) ...

# Этап 5: Финальное ПОДТВЕРЖДЕНИЕ и СОЗДАНИЕ СДЕЛКИ
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
):
    """
    Обрабатывает подтверждение, создает сделку с сырыми данными,
    а затем в фоне пытается обновить ее с помощью AI.
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
    try:
        # --- Шаг 1: Создание сделки с СЫРЫМИ данными ---
        visit_datetime_obj = None
        visit_date_iso = data.get("visit_date")
        visit_time_str = data.get("visit_time")
        if visit_date_iso and visit_time_str:
            visit_date = date.fromisoformat(visit_date_iso)
            hour, minute = map(int, visit_time_str.split(':'))
            visit_datetime_obj = datetime.combine(visit_date, datetime.min.time()).replace(hour=hour, minute=minute)

        created_deal = await crm_client.create_deal(
            name=data.get("deal_name"),
            description=data.get("deal_description"),
            ticket_visit_datetime=visit_datetime_obj,
            megaplan_user_id=user.megaplan_user_id,
        )

        if not created_deal or "id" not in created_deal:
            raise Exception("CRM не вернуло данные о созданной сделке.")

        deal_id = created_deal["id"]
        
        # --- Шаг 2: Прикрепление файлов (если есть) ---
        # ... (эта часть остается без изменений)
        attached_files = data.get("attached_files", [])
        if attached_files:
            # ... (логика загрузки и прикрепления файлов)

        # --- Шаг 3: Попытка "улучшения" сделки с помощью AI ---
        await query.message.edit_text(f"✅ Заявка #{deal_id} создана.\n⏳ Форматирую описание с помощью AI...")
        
        update_succeeded = False
        # По умолчанию используем сырые данные для финального сообщения
        final_deal_name = data.get("deal_name", "")
        final_deal_description = data.get("deal_description", "")

        try:
            raw_description_for_ai = data.get("deal_description", "")
            formatted_response = await format_ticket_with_perplexity(raw_description_for_ai)

            if formatted_response:
                parts = formatted_response.split('\n', 1)
                new_name = parts[0].strip()
                new_description = parts[1].strip() if len(parts) > 1 else new_name
                
                update_payload = {"name": new_name, "description": new_description}
                
                # Обновляем сделку в CRM
                updated_deal = await crm_client.update_deal(deal_id, update_payload)
                if updated_deal:
                    update_succeeded = True
                    final_deal_name = new_name
                    final_deal_description = new_description
                    logger.info(f"Сделка {deal_id} успешно обновлена с помощью AI.")

        except Exception as e_format:
            # Эта ошибка не критична, основная сделка уже создана
            logger.error(f"Ошибка на этапе форматирования сделки {deal_id}: {e_format}", exc_info=True)
            # update_succeeded остается False

        # --- Шаг 4: Финальный отчет пользователю ---
        deal_url = f"{crm_client.base_url}/deals/{deal_id}/card/"
        final_message_parts = []

        if update_succeeded:
            final_message_parts.append("✅ **Заявка создана и успешно отформатирована!**")
        else:
            final_message_parts.append("⚠️ **Заявка создана, но отформатировать не удалось.**")

        # Формируем итоговое сообщение (код из предыдущего ответа)
        if visit_date_iso:
            visit_date = date.fromisoformat(visit_date_iso)
            display_time = "Любое" if visit_time_str == "00:00" else visit_time_str
            final_message_parts.append(f"🚗 Выезд {visit_date.strftime('%d.%m.%Y')}, {display_time}")
        else:
            final_message_parts.append("🖥️ Заявка без выезда")

        final_message_parts.append(f"{final_deal_name}")
        
        lines = final_deal_description.split('\n')
        if len(lines) > 1:
            clean_description = "\n".join(lines[1:]).strip()
            if clean_description:
                final_message_parts.append(f"{clean_description}")
        
        final_message_parts.append(f"\n<a href='{deal_url}'>Перейти к сделке #{deal_id}</a>")
        
        await query.message.edit_text(
            text="\n".join(final_message_parts),
            disable_web_page_preview=True,
        )

    except Exception as e_main:
        logger.error(f"Критическая ошибка при создании сделки: {e_main}", exc_info=True)
        deal_id_str = f" (ID сделки: {deal_id})" if deal_id else ""
        await query.message.answer(
            f"❌ Произошла ошибка при создании заявки{deal_id_str}. Свяжитесь с администратором."
        )
    finally:
        # --- Шаг 5: Очистка и возврат в меню ---
        await state.clear()
        await get_main_menu_message(query.message, session, crm_client)

@add_ticket_router.callback_query(F.data == "add_ticket_cancel")
async def cancel_add_ticket_date_step(
    query: CallbackQuery, state: FSMContext, session: AsyncSession, crm_client: CRMClient
):
    """Отменяет процесс создания заявки и возвращает в главное меню."""
    await state.clear()
    await query.answer("Действие отменено")
    await get_main_menu_message(query.message, session, crm_client)
