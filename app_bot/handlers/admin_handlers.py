import logging
from datetime import date, datetime, timedelta

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

# Импортируем роли и функции для работы с БД
from app_bot.config.user_roles_config import (
    ADMIN_ROLE_PERMISSIONS,
    GEODESIST_ROLE_PERMISSIONS,
    MANAGER_ROLE_PERMISSIONS,
    USER_ROLE_PERMISSIONS,
)
from app_bot.database import crud
from app_bot.database.models import Permission
from app_bot.filters.permission_filters import HasPermissionFilter
from app_bot.keyboards.admin_keyboards import (
    DateLimitCallback,
    UserCallback,
    get_cancel_kb,
    get_limits_management_kb,
    get_user_management_kb,
    get_view_limits_for_date_kb,
)
from app_bot.utils.admin_utils import fetch_holidays_from_url


admin_router = Router()
logger = logging.getLogger(__name__)


class CreateUserFSM(StatesGroup):
    """
    Машина состояний для процесса создания нового пользователя.
    """

    waiting_for_user_data = State()


class SetDefaultLimitFSM(StatesGroup):
    """
    Машина состояний для процесса установки нового лимита по умолчанию.
    """

    waiting_for_new_limit = State()


class SetDefaultBrigadesFSM(StatesGroup):
    """
    Машина состояний для процесса установки нового кол-ва бригад по умолчанию.
    """

    waiting_for_new_brigades_count = State()


class SetDateLimitFSM(StatesGroup):
    """
    Машина состояний для процесса установки лимитов на выбранные даты.
    """

    waiting_for_date_range = State()
    waiting_for_limit_value = State()
    waiting_for_brigades_count = State()


class ViewDateLimitFSM(StatesGroup):
    """
    Машина состояний для просмотра установленных лимитов на выбранные даты.
    """

    waiting_for_date_range_to_view = State()


class SetNonWorkingDaysFSM(StatesGroup):
    """
    Машина состояний для процесса установки нерабочих дней
    по производственному календарю.
    """

    waiting_for_calendar_url = State()


ROLES_MAP = {
    "USER_ROLE_PERMISSIONS": USER_ROLE_PERMISSIONS,
    "MANAGER_ROLE_PERMISSIONS": MANAGER_ROLE_PERMISSIONS,
    "ADMIN_ROLE_PERMISSIONS": ADMIN_ROLE_PERMISSIONS,
    "GEODESIST_ROLE_PERMISSIONS": GEODESIST_ROLE_PERMISSIONS,
}


async def get_admin_menu_message(event: Message | CallbackQuery) -> None:
    """
    Отправляет главное админ-меню.
    Принимает либо Message, либо CallbackQuery.

    • Для Message — просто отвечаем сообщением.
    • Для CallbackQuery — сначала закрываем «крутилку» методом
    `CallbackQuery.answer()` (0-200 симв.[8]), затем
    отправляем новое сообщение в чат при помощи `event.message.answer(...)`.
    """
    instruction_text = (
        "🔧 РЕЖИМ АДМИНИСТРАТОРА 🔧\n\n"
        "Добро пожаловать в панель управления!\n"
        "Выберите необходимое действие:\n\n"
        "👤 /create_user – Создание нового пользователя\n"
        "📋 /users_list – Просмотр всех пользователей\n\n"
        "📊 /ticket_limits – Управление лимитами заявок\n\n"
        "🏠 /start – Главное меню\n\n"
        "---------------------------------\n\n"
        "📊 /fill_not_working_days_for_limit – Установить выходные и праздничные дни из производственного календаря.\n\n"
    )

    if isinstance(event, Message):
        await event.answer(text=instruction_text, disable_web_page_preview=True)
    elif isinstance(event, CallbackQuery):
        # Закрываем progress-bar; текст ≤200 симв.[8]
        await event.answer()
        await event.message.answer(text=instruction_text)
    else:
        raise TypeError("Аргумент должен быть Message или CallbackQuery")


async def get_ticket_limit_menu_message(
    event: Message | CallbackQuery, session: AsyncSession
) -> None:
    """
    Отправляет информативное меню управления лимитами заявок.
    Показывает лимит по умолчанию и прогноз лимитов на 7 дней вперед,
    выделяя дни с особыми настройками.
    """
    # 1. Получаем настройки по умолчанию
    app_settings = await crud.get_app_settings(session)
    default_limit = app_settings.default_daily_limit
    default_brigades = app_settings.default_brigades_count

    # 2. Готовим прогноз на 7 дней
    today = date.today()
    day_names_ru = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")
    weekly_limits_info = []

    for i in range(7):
        current_date = today + timedelta(days=i)
        actual_limit = await crud.get_actual_limit_for_date(session, current_date)
        actual_brigades = await crud.get_actual_brigades_for_date(session, current_date)

        day_name = day_names_ru[current_date.weekday()]
        date_str = current_date.strftime("%d.%m")

        # Проверяем, является ли лимит или кол-во бригад особым
        override_marker = ""
        if actual_limit != default_limit or actual_brigades != default_brigades:
            override_marker = " ✨"

        limit_info_str = f"{day_name}, {date_str}: <b>{actual_limit}</b> заявок, <b>{actual_brigades}</b> бригад{override_marker}"
        weekly_limits_info.append(limit_info_str)

    # 3. Собираем итоговое сообщение
    weekly_limits_formatted = "\n".join(weekly_limits_info)

    instruction_text = (
        "📋 <b>Управление лимитами заявок</b> 📋\n\n"
        f"Лимит по умолчанию: <b>{default_limit}</b>\n"
        f"Бригад по умолчанию: <b>{default_brigades}</b>\n\n"  # <-- Добавляем инфо
        "<u>Прогноз на ближайшие 7 дней:</u>\n"
        f"{weekly_limits_formatted}\n\n"
        "<i>✨ - на дату установлен особый лимит или кол-во бригад.</i>"
    )

    kb = get_limits_management_kb(
        default_limit=default_limit, default_brigades=default_brigades
    )

    # 4. Отправляем сообщение
    if isinstance(event, Message):
        await event.answer(text=instruction_text, reply_markup=kb)
    elif isinstance(event, CallbackQuery):
        await event.answer()
        try:
            await event.message.answer(text=instruction_text, reply_markup=kb)
        except Exception:
            # Если редактирование не удалось (например, текст не изменился), просто отправляем новое
            await event.message.answer(text=instruction_text, reply_markup=kb)
    else:
        raise TypeError("Аргумент должен быть Message или CallbackQuery")


@admin_router.callback_query(
    F.data == "admin_cancel",
    HasPermissionFilter([Permission.MANAGE_USERS, Permission.SET_TRIP_LIMITS]),
)
async def cancel_cmd(query: CallbackQuery, state: FSMContext):
    await state.clear()
    await get_admin_menu_message(query)


@admin_router.message(
    Command("admin"), HasPermissionFilter([Permission.MANAGE_USERS, Permission.SET_TRIP_LIMITS])
)
async def admin_cmd(message: Message, state: FSMContext):
    await state.clear()
    await get_admin_menu_message(message)


@admin_router.message(Command("create_user"), HasPermissionFilter(Permission.MANAGE_USERS))
async def start_user_creation_cmd(message: Message, state: FSMContext):
    """
    Этот хендлер запускает процесс создания нового пользователя.
    Он отправляет администратору инструкцию по вводу данных.
    """

    # Формируем и отправляем сообщение-инструкцию
    instruction_text = """
        📝 **СОЗДАНИЕ НОВОГО ПОЛЬЗОВАТЕЛЯ** 📝

        Введите данные для нового пользователя.
        Каждый параметр указывайте с новой строки:

        🆔 <b>Telegram ID</b>
        └─ Уникальный идентификатор пользователя в Telegram

        🏢 <b>Megaplan ID</b>
        └─ ID в системе Megaplan

        👤 <b>Имя пользователя</b>
        └─ Отображаемое имя пользователя

        🔐 <b>Группа прав</b>
        └─ Выберите одну из ролей:
            • USER_ROLE_PERMISSIONS (создание и просмотр заявок)
            • GEODESIST_ROLE_PERMISSIONS (создание и просмотр заявок + добавлением файлов к сделкам)
            • MANAGER_ROLE_PERMISSIONS (создание и просмотр заявок + управление лимитами заявок)
            • ADMIN_ROLE_PERMISSIONS (все права)
            

        Пример ввода:
        123456789
        133546456
        Иван Иванов
        USER_ROLE_PERMISSIONS
        """
    await message.answer(text=instruction_text, reply_markup=get_cancel_kb())

    # Устанавливаем состояние ожидания данных от администратора
    await state.set_state(CreateUserFSM.waiting_for_user_data)


@admin_router.message(
    CreateUserFSM.waiting_for_user_data, F.text, HasPermissionFilter(Permission.MANAGE_USERS)
)
async def process_and_save_user_data_cmd(
    message: Message, state: FSMContext, session: AsyncSession
):
    """
    Этот хендлер ловит сообщение с данными, проверяет их
    и сразу сохраняет в БД. Каждая проверка обернута в свой блок try-except.
    """
    # --- 1. Проверка структуры ввода ---
    try:
        lines = message.text.strip().split("\n")
        if len(lines) != 4:
            raise ValueError("Неверное количество строк. Ожидалось 4.")
        tg_id_str, mp_id_str, username, role_str = [line.strip() for line in lines]
    except (ValueError, IndexError):
        await message.answer(
            "❌ <b>Ошибка формата ввода!</b>\n\n"
            "Убедитесь, что вы ввели ровно 4 строки, как в примере. "
            "Попробуйте снова или нажмите /cancel для отмены."
        )
        return

    # --- 2. Проверка Telegram ID ---
    try:
        telegram_id = int(tg_id_str)
    except ValueError:
        await message.answer(
            f"❌ <b>Ошибка: неверный Telegram ID!</b>\n\n"
            f"Значение '<code>{tg_id_str}</code>' не является числом. "
            f"Пожалуйста, введите корректный числовой ID."
        )
        return

    # --- 3. Проверка Megaplan ID ---
    try:
        megaplan_user_id = int(mp_id_str)
    except ValueError:
        await message.answer(
            f"❌ <b>Ошибка: неверный Megaplan ID!</b>\n\n"
            f"Значение '<code>{mp_id_str}</code>' не является числом. "
            f"Пожалуйста, введите корректный числовой ID."
        )
        return

    # --- 4. Проверка имени пользователя ---
    if not username:
        await message.answer(
            "❌ <b>Ошибка: пустое имя пользователя!</b>\n\n"
            "Поле имени пользователя не может быть пустым. Пожалуйста, введите имя."
        )
        return

    # --- 5. Проверка роли ---
    try:
        permissions = ROLES_MAP[role_str]
    except KeyError:
        valid_roles_html = "\n".join([f"• <code>{role}</code>" for role in ROLES_MAP.keys()])
        await message.answer(
            f"❌ <b>Ошибка: неверная роль!</b>\n\n"
            f"Указана несуществующая роль '<code>{role_str}</code>'.\n"
            f"Пожалуйста, выберите одну из доступных ролей:\n{valid_roles_html}"
        )
        return

    # --- 6. Попытка создания пользователя в БД ---
    try:
        new_user = await crud.create_user(
            session=session,
            telegram_id=telegram_id,
            username=username,
            megaplan_user_id=megaplan_user_id,
            initial_permissions=permissions,
        )

        success_text = f"""
            ✅ <b>ПОЛЬЗОВАТЕЛЬ УСПЕШНО СОЗДАН</b> ✅

            Ниже приведены данные нового пользователя:

            🆔 <b>Telegram ID:</b> <code>{new_user.telegram_id}</code>
            🏢 <b>Megaplan ID:</b> <code>{new_user.megaplan_user_id}</code>
            👤 <b>Имя:</b> {new_user.username}
            🔐 <b>Роль:</b> <code>{role_str}</code>
        """

        await message.answer(success_text)
        await get_admin_menu_message(message)

    except IntegrityError:
        await message.answer(
            "❌ <b>Ошибка: пользователь уже существует!</b>\n\n"
            "Пользователь с таким <b>Telegram ID</b> "
            "уже зарегистрирован в системе."
        )
    except Exception as e:
        logger.error(f"Непредвиденная ошибка при создании пользователя: {e}", exc_info=True)
        await message.answer(
            "❌ <b>Произошла непредвиденная ошибка.</b>\n\n"
            "Информация об ошибке записана в лог. Свяжитесь с разработчиком."
        )
    finally:
        # В любом случае (успех или ошибка на этапе БД) завершаем состояние
        await state.clear()


@admin_router.message(Command("users_list"), HasPermissionFilter(Permission.MANAGE_USERS))
async def show_users_list_cmd(message: Message, session: AsyncSession):
    users = await crud.get_users(session, limit=100)  # Получаем всех пользователей

    if not users:
        await message.answer("👥 В системе пока нет зарегистрированных пользователей.")
        return

    await message.answer(f"👥 Найдено пользователей: {len(users)}. Отправляю список...")

    for user in users:
        user_info = (
            f"👤 <b>Имя:</b> {user.username}\n"
            f"🆔 <b>Telegram ID:</b> <code>{user.telegram_id}</code>\n"
            f"🏢 <b>Megaplan ID:</b> <code>{user.megaplan_user_id}</code>\n"
            f"🔐 <b>Права:</b> <code>{user.permissions}</code>"
        )
        # Для каждого пользователя отправляем отдельное сообщение с его клавиатурой
        await message.answer(
            text=user_info, reply_markup=get_user_management_kb(user.telegram_id)
        )
    await get_admin_menu_message(message)


@admin_router.callback_query(
    UserCallback.filter(F.action == "delete"), HasPermissionFilter(Permission.MANAGE_USERS)
)
async def delete_user_callback(
    query: CallbackQuery,
    callback_data: UserCallback,
    session: AsyncSession,
):
    """
    Обрабатывает нажатие на кнопку "Удалить" под сообщением пользователя.
    """
    user_telegram_id_to_delete = callback_data.user_telegram_id

    try:
        # Пытаемся удалить пользователя
        deleted = await crud.delete_user_by_telegram_id(
            session=session, telegram_id=user_telegram_id_to_delete
        )

        if deleted:
            # Если удаление прошло успешно
            success_text = (
                f"✅ Пользователь <code>{user_telegram_id_to_delete}</code> успешно удален."
            )
            await query.message.edit_text(success_text)  # Редактируем исходное сообщение
            await query.answer("Пользователь удален", show_alert=False)
        else:
            not_found_text = f"⚠️ Пользователь <code>{user_telegram_id_to_delete}</code> не найден в базе данных (возможно, уже был удален)."
            await query.message.edit_text(not_found_text)
            await query.answer("Пользователь не найден", show_alert=True)

    except Exception as e:
        logger.error(
            f"Ошибка при удалении пользователя {user_telegram_id_to_delete}: {e}",
            exc_info=True,
        )
        await query.answer("❌ Произошла ошибка при удалении.", show_alert=True)


# Меню управления лимитами заявок
@admin_router.message(
    Command("ticket_limits"),
    HasPermissionFilter([Permission.MANAGE_USERS, Permission.SET_TRIP_LIMITS]),
)
async def ticket_limits_menu_cmd(message: Message, session: AsyncSession, state: FSMContext):
    await state.clear()
    await get_ticket_limit_menu_message(message, session=session)


@admin_router.callback_query(
    F.data == "admin_limits_date", HasPermissionFilter(Permission.SET_TRIP_LIMITS)
)
async def set_date_limit_start(query: CallbackQuery, session: AsyncSession):
    """
    Показывает меню для выбора даты для редактирования лимита.
    Сначала предлагает быстрый выбор из 7 дней с уже известными лимитами.
    """
    await query.answer()

    # 1. Получаем лимиты для следующих 7 дней
    limits_data = {}
    today = date.today()
    for i in range(7):
        current_date = today + timedelta(days=i)
        limit = await crud.get_actual_limit_for_date(session, current_date)
        limits_data[current_date] = limit

    # 2. Получаем лимит по умолчанию, чтобы передать его в клавиатуру для сравнения
    app_settings = await crud.get_app_settings(session)
    default_limit = app_settings.default_daily_limit

    # 3. Генерируем клавиатуру, передавая ей оба набора данных
    kb = get_view_limits_for_date_kb(daily_limits=limits_data, default_limit=default_limit)

    instruction_text = (
        "🗓 <b>Редактирование лимита на дату</b> 🗓\n\n"
        "Выберите дату для быстрого редактирования, или введите ее вручную.\n"
        "<i>✨ - на дату установлен особый лимит.</i>"
    )

    # 4. Отправляем сообщение с новой клавиатурой
    await query.message.answer(text=instruction_text, reply_markup=kb)


@admin_router.callback_query(
    F.data == "admin_limits_default", HasPermissionFilter(Permission.SET_TRIP_LIMITS)
)
async def set_default_limit_start(
    query: CallbackQuery, state: FSMContext, session: AsyncSession
):
    """
    Обрабатывает нажатие на кнопку "Лимиты по умолчанию".
    Запрашивает новое значение и переводит в состояние ожидания.
    """
    # Сначала отвечаем на callback, чтобы убрать "часики"
    await query.answer()

    # Получаем текущее значение лимита из БД
    app_settings = await crud.get_app_settings(session)
    current_limit = app_settings.default_daily_limit

    prompt_text = (
        f"Вы собираетесь изменить лимит по умолчанию.\n"
        f"<b>Текущее значение: {current_limit}</b>\n\n"
        f"Введите новое числовое значение и отправьте его в чат."
    )

    # Отправляем сообщение с запросом и клавиатурой отмены
    await query.message.answer(text=prompt_text, reply_markup=get_cancel_kb())

    # Устанавливаем состояние ожидания нового значения
    await state.set_state(SetDefaultLimitFSM.waiting_for_new_limit)


@admin_router.message(
    SetDefaultLimitFSM.waiting_for_new_limit,
    F.text,
    HasPermissionFilter(Permission.SET_TRIP_LIMITS),
)
async def process_new_default_limit(message: Message, state: FSMContext, session: AsyncSession):
    """
    Получает сообщение с новым лимитом, валидирует его,
    сохраняет в БД и выводит обновленное меню управления лимитами.
    """
    # 1. Валидация ввода
    try:
        new_limit = int(message.text.strip())
        if new_limit < 0:
            await message.answer(
                "❌ <b>Ошибка:</b> Лимит не может быть отрицательным числом. Попробуйте снова."
            )
            return
    except (ValueError, TypeError):
        await message.answer(
            "❌ <b>Ошибка:</b> Введенное значение не является целым числом. Пожалуйста, введите корректное число."
        )
        return

    # 2. Обновление значения в базе данных
    try:
        updated_settings = await crud.update_default_limit(session, new_limit)
        logger.info(
            f"Пользователь {message.from_user.id} изменил лимит по умолчанию на {new_limit}"
        )
        await message.answer(
            f"✅ Лимит по умолчанию успешно изменен на <b>{updated_settings.default_daily_limit}</b>."
        )
    except Exception as e:
        logger.error(f"Ошибка при обновлении лимита в БД: {e}", exc_info=True)
        await message.answer(
            f"❌ Произошла ошибка при сохранении нового лимита. Попробуйте позже. {e}"
        )
        await state.clear()
        return

    # 3. Завершение FSM и возврат в меню управления лимитами
    await state.clear()

    # Повторяем логику ticket_limits_menu_cmd, чтобы показать обновленное меню
    await get_ticket_limit_menu_message(message, session=session)


@admin_router.callback_query(
    F.data == "admin_limits_manual_input", HasPermissionFilter(Permission.SET_TRIP_LIMITS)
)
async def set_date_limit_manual_input(query: CallbackQuery, state: FSMContext):
    """
    Шаг 1 (ручной ввод): Запрашивает дату или диапазон дат.
    """
    # Этот хендлер остается почти без изменений
    await query.answer()
    await state.clear()
    instruction_text = (
        "⌨️ <b>Ручной ввод</b> ⌨️\n\n"
        "Введите дату или диапазон дат в формате <code>ДД.ММ.ГГГГ</code>.\n\n"
        "<b>Примеры:</b>\n"
        "• Одна дата: <code>25.12.2025</code>\n"
        "• Диапазон: <code>01.01.2026-07.01.2026</code>"
    )
    await query.message.answer(instruction_text, reply_markup=get_cancel_kb())
    await state.set_state(SetDateLimitFSM.waiting_for_date_range)


@admin_router.callback_query(
    DateLimitCallback.filter(F.action == "edit_limit"),
    HasPermissionFilter(Permission.SET_TRIP_LIMITS),
)
async def process_date_from_callback(
    query: CallbackQuery,
    callback_data: DateLimitCallback,
    state: FSMContext,
    session: AsyncSession,
):
    """
    Шаг 1 (быстрый выбор): Обрабатывает нажатие на кнопку с датой.
    Сразу запрашивает значение ЛИМИТА.
    """
    await query.answer()
    target_date = date.fromisoformat(callback_data.date_iso)
    await state.update_data(start_date=target_date, end_date=target_date)
    await state.set_state(SetDateLimitFSM.waiting_for_limit_value)

    current_limit = await crud.get_actual_limit_for_date(session, target_date)

    prompt_text = (
        f"Вы редактируете настройки для даты: <b>{target_date.strftime('%d.%m.%Y')}</b>.\n"
        f"Текущий лимит заявок: <code>{current_limit}</code>.\n\n"
        "Введите новое числовое значение для <b>лимита заявок</b>."
    )
    await query.message.answer(text=prompt_text, reply_markup=get_cancel_kb())


@admin_router.message(
    SetDateLimitFSM.waiting_for_date_range,
    F.text,
    HasPermissionFilter(Permission.SET_TRIP_LIMITS),
)
async def process_date_range(message: Message, state: FSMContext):
    """
    Шаг 2: Проверяет дату(ы), сохраняет их в state.data и запрашивает лимит.
    """
    date_text = message.text.strip()
    try:
        if "-" in date_text:
            # Обработка диапазона
            start_str, end_str = date_text.split("-")
            start_date = datetime.strptime(start_str.strip(), "%d.%m.%Y").date()
            end_date = datetime.strptime(end_str.strip(), "%d.%m.%Y").date()
            if start_date > end_date:
                await message.answer(
                    "❌ <b>Ошибка:</b> Начальная дата диапазона не может быть позже конечной. Попробуйте снова."
                )
                return
        else:
            # Обработка одной даты
            start_date = end_date = datetime.strptime(date_text, "%d.%m.%Y").date()

    except ValueError:
        await message.answer(
            "❌ <b>Ошибка формата!</b>\n"
            "Пожалуйста, используйте формат <code>ДД.ММ.ГГГГ</code> или <code>ДД.ММ.ГГГГ-ДД.ММ.ГГГГ</code>."
        )
        return

    # Сохраняем даты в FSM
    await state.update_data(start_date=start_date, end_date=end_date)

    # Запрашиваем значение лимита
    await message.answer(
        "Отлично! Теперь введите <b>числовое значение лимита</b>.\n"
        "`10` — установить лимит 10.\n"
    )
    await state.set_state(SetDateLimitFSM.waiting_for_limit_value)


@admin_router.message(
    SetDateLimitFSM.waiting_for_limit_value,
    F.text,
    HasPermissionFilter(Permission.SET_TRIP_LIMITS),
)
async def process_limit_for_date(message: Message, state: FSMContext, session: AsyncSession):
    """
    Шаг 3 (общий): Получает лимит, сохраняет его в state и запрашивает КОЛИЧЕСТВО БРИГАД.
    """
    try:
        limit_value = int(message.text.strip())
        if limit_value < 0:
            await message.answer("❌ <b>Ошибка:</b> Лимит не может быть отрицательным.")
            return
    except (ValueError, TypeError):
        await message.answer("❌ <b>Ошибка:</b> Введите целое число.")
        return

    # Сохраняем лимит в FSM и переходим на следующий шаг
    await state.update_data(limit_value=limit_value)

    # Узнаем текущее количество бригад для подсказки
    fsm_data = await state.get_data()
    start_date = fsm_data.get("start_date")  # Дата уже есть в FSM
    current_brigades = await crud.get_actual_brigades_for_date(session, start_date)

    await message.answer(
        f"Лимит <code>{limit_value}</code> принят.\n"
        f"Текущее количество бригад: <code>{current_brigades}</code>.\n\n"
        "Теперь введите новое <b>количество бригад</b>.\n"
        "Чтобы использовать значение по умолчанию, отправьте <code>0</code>."
    )
    await state.set_state(SetDateLimitFSM.waiting_for_brigades_count)


@admin_router.message(
    SetDateLimitFSM.waiting_for_brigades_count,
    F.text,
    HasPermissionFilter(Permission.SET_TRIP_LIMITS),
)
async def process_brigades_for_date(message: Message, state: FSMContext, session: AsyncSession):
    """
    Шаг 4 (общий): Получает кол-во бригад, сохраняет все в БД и завершает.
    """
    try:
        brigades_value = int(message.text.strip())
        if brigades_value < 0:
            await message.answer(
                "❌ <b>Ошибка:</b> Количество бригад не может быть отрицательным."
            )
            return
    except (ValueError, TypeError):
        await message.answer("❌ <b>Ошибка:</b> Введите целое число.")
        return

    # Если пользователь ввел 0, мы будем сохранять None, чтобы использовалось значение по умолчанию
    final_brigades_value = brigades_value if brigades_value > 0 else None

    # Получаем все данные из FSM
    fsm_data = await state.get_data()
    start_date = fsm_data.get("start_date")
    end_date = fsm_data.get("end_date")
    limit_value = fsm_data.get("limit_value")

    if not all([start_date, end_date, limit_value is not None]):
        await message.answer("❗️ Произошла внутренняя ошибка, попробуйте начать заново.")
        await state.clear()
        return

    # Сохраняем в БД
    try:
        await crud.set_daily_limit_override_range(
            session=session,
            start_date=start_date,
            end_date=end_date,
            limit=limit_value,
            brigades_count=final_brigades_value,
        )
    except Exception as e:
        logger.error(f"Ошибка при установке лимита на диапазон дат: {e}", exc_info=True)
        await message.answer("❌ Произошла ошибка при сохранении в базу данных.")
        await state.clear()
        return

    # Формируем сообщение об успехе
    brigade_info = (
        f", бригад: <b>{final_brigades_value}</b>"
        if final_brigades_value is not None
        else ", бригад: (по умолч.)"
    )
    if start_date == end_date:
        date_info = f"на дату <b>{start_date.strftime('%d.%m.%Y')}</b>"
    else:
        date_info = f"для диапазона дат с <b>{start_date.strftime('%d.%m.%Y')}</b> по <b>{end_date.strftime('%d.%m.%Y')}</b>"

    await message.answer(
        f"✅ Успешно! Установлен лимит <b>{limit_value}</b>{brigade_info} {date_info}."
    )

    # Завершаем FSM и показываем обновленное меню
    await state.clear()
    await get_ticket_limit_menu_message(message, session=session)


@admin_router.callback_query(
    F.data == "admin_limits_view", HasPermissionFilter(Permission.SET_TRIP_LIMITS)
)
async def view_date_limit_start(query: CallbackQuery, state: FSMContext):
    """Шаг 1: Запрашивает дату или диапазон для просмотра."""
    await query.answer()
    await state.clear()

    instruction_text = (
        "🔍 <b>Просмотр лимитов</b> 🔍\n\n"
        "Введите дату или диапазон дат (не более 31 дня) в формате <code>ДД.ММ.ГГГГ</code>.\n\n"
        "<b>Примеры:</b>\n"
        "• Одна дата: <code>25.12.2025</code>\n"
        "• Диапазон: <code>01.01.2026-15.01.2026</code>"
    )
    await query.message.answer(instruction_text, reply_markup=get_cancel_kb())
    await state.set_state(ViewDateLimitFSM.waiting_for_date_range_to_view)


@admin_router.message(
    ViewDateLimitFSM.waiting_for_date_range_to_view,
    F.text,
    HasPermissionFilter(Permission.SET_TRIP_LIMITS),
)
async def process_date_range_for_view(
    message: Message, state: FSMContext, session: AsyncSession
):
    """Шаг 2: Валидирует диапазон, получает данные из БД и выводит результат."""
    date_text = message.text.strip()
    try:
        if "-" in date_text:
            start_str, end_str = date_text.split("-")
            start_date = datetime.strptime(start_str.strip(), "%d.%m.%Y").date()
            end_date = datetime.strptime(end_str.strip(), "%d.%m.%Y").date()
            if start_date > end_date:
                await message.answer(
                    "❌ <b>Ошибка:</b> Начальная дата не может быть позже конечной."
                )
                return
            if (end_date - start_date).days > 30:
                await message.answer("❌ <b>Ошибка:</b> Диапазон не может превышать 31 день.")
                return
        else:
            start_date = end_date = datetime.strptime(date_text, "%d.%m.%Y").date()
    except ValueError:
        await message.answer("❌ <b>Ошибка формата!</b> Используйте <code>ДД.ММ.ГГГГ</code>.")
        return

    # Получаем лимиты для диапазона
    day_names_ru = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")
    results = []
    app_settings = await crud.get_app_settings(session)
    default_limit = app_settings.default_daily_limit

    current_date = start_date
    while current_date <= end_date:
        actual_limit = await crud.get_actual_limit_for_date(session, current_date)
        day_name = day_names_ru[current_date.weekday()]
        date_str = current_date.strftime("%d.%m.%Y")
        override_marker = " ✨" if actual_limit != default_limit else ""
        results.append(f"{day_name}, {date_str}: <b>{actual_limit}</b>{override_marker}")
        current_date += timedelta(days=1)

    # Вывод результата
    results_text = "\n".join(results)
    final_message = f"📊 <b>Лимиты на выбранный период:</b>\n\n{results_text}"
    await message.answer(final_message)

    # Завершаем FSM и возвращаемся в меню лимитов
    await state.clear()
    await get_ticket_limit_menu_message(message, session)


@admin_router.message(
    Command("fill_not_working_days_for_limit"), HasPermissionFilter(Permission.MANAGE_USERS)
)
async def fill_not_working_days_cmd(message: Message, session: AsyncSession, state: FSMContext):
    await state.clear()
    await message.answer(
        "Введите ссылку из консультант плюс, на производственный календарь для нужного года. \n\n"
        "Данные беруться по ссылке вида https://www.consultant.ru/law/ref/calendar/proizvodstvennye/2025/ \n\n"
        "После выполнения этой команды, уже установленные лимиты на нерабочие дни будут перезаписаны и станут 0"
    )
    await state.set_state(SetNonWorkingDaysFSM.waiting_for_calendar_url)


@admin_router.message(
    SetNonWorkingDaysFSM.waiting_for_calendar_url,
    F.text,
    HasPermissionFilter(Permission.MANAGE_USERS),
)
async def process_calendar_url_cmd(message: Message, state: FSMContext, session: AsyncSession):
    """
    Этот хендлер получает ссылку на производственный календарь,
    парсит её и устанавливает лимит 0 на все выходные и праздничные дни.
    """
    calendar_url = message.text.strip()
    await message.answer(
        f"Принял ссылку: {calendar_url}\nНачинаю обработку, это может занять некоторое время..."
    )

    try:
        # 1. Вызываем утилиту для получения списка дат
        holidays = await fetch_holidays_from_url(calendar_url)

        if not holidays:
            await message.answer(
                "Не удалось найти нерабочие дни по указанной ссылке. Проверьте ссылку или содержимое страницы."
            )
            await state.clear()
            await get_ticket_limit_menu_message(message, session=session)
            return

        await message.answer(
            f"✅ Найдено {len(holidays)} нерабочих дней. Начинаю установку нулевых лимитов..."
        )

        # 2. Проходим по списку и устанавливаем лимит 0 для каждой даты
        processed_count = 0
        for holiday_date in holidays:
            try:
                await crud.set_daily_limit_override(session, target_date=holiday_date, limit=0)
                processed_count += 1
            except Exception as e:
                logger.error(f"Не удалось установить лимит для даты {holiday_date}: {e}")
                # Продолжаем со следующей датой
                pass

        # 3. Отправляем итоговый отчет
        success_message = f"✅ Обработка завершена! Установлен нулевой лимит для {processed_count} из {len(holidays)} нерабочих дней."
        if processed_count < len(holidays):
            success_message += "\n❗️ Во время установки лимитов для некоторых дат произошли ошибки. Подробности в логах."

        await message.answer(success_message)

    except Exception as e:
        logger.error(
            f"Ошибка при обработке календаря по ссылке {calendar_url}: {e}", exc_info=True
        )
        await message.answer(
            "❌ Произошла критическая ошибка при получении или обработке данных с сайта. "
            "Проверьте ссылку и повторите попытку позже. Подробности в логах."
        )
    finally:
        # В любом случае завершаем FSM
        await state.clear()
        # И возвращаемся в меню управления лимитами, чтобы показать обновленные данные.
        await get_ticket_limit_menu_message(message, session=session)


@admin_router.callback_query(
    F.data == "admin_brigades_default", HasPermissionFilter(Permission.SET_TRIP_LIMITS)
)
async def set_default_brigades_start(
    query: CallbackQuery, state: FSMContext, session: AsyncSession
):
    await query.answer()
    settings = await crud.get_app_settings(session)
    await query.message.answer(
        f"Текущее количество бригад по умолчанию: <b>{settings.default_brigades_count}</b>.\n\n"
        "Введите новое числовое значение:",
        reply_markup=get_cancel_kb(),
    )
    await state.set_state(SetDefaultBrigadesFSM.waiting_for_new_brigades_count)


@admin_router.message(
    SetDefaultBrigadesFSM.waiting_for_new_brigades_count,
    F.text,
    HasPermissionFilter(Permission.SET_TRIP_LIMITS),
)
async def process_new_default_brigades_count(
    message: Message, state: FSMContext, session: AsyncSession
):
    try:
        new_count = int(message.text.strip())
        if new_count <= 0:
            await message.answer("❌ <b>Ошибка:</b> Количество бригад должно быть больше нуля.")
            return
    except (ValueError, TypeError):
        await message.answer("❌ <b>Ошибка:</b> Введите целое число.")
        return

    try:
        await crud.update_default_brigades_count(session, new_count)
        await message.answer(
            f"✅ Количество бригад по умолчанию успешно изменено на <b>{new_count}</b>."
        )
    except Exception:
        # ... (обработка ошибок) ...
        return
    finally:
        await state.clear()

    await get_ticket_limit_menu_message(message, session=session)
