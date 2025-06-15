import logging

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
    MANAGER_ROLE_PERMISSIONS,
    USER_ROLE_PERMISSIONS,
)
from app_bot.database import crud
from app_bot.database.models import Permission
from app_bot.filters.permission_filters import HasPermissionFilter
from app_bot.keyboards.admin_keyboards import (
    UserCallback,
    get_cancel_kb,
    get_limits_management_kb,
    get_user_management_kb,
)


admin_router = Router()
logger = logging.getLogger(__name__)


class CreateUserFSM(StatesGroup):
    """
    Машина состояний для процесса создания нового пользователя.
    """

    waiting_for_user_data = State()


class EditUserFSM(StatesGroup):
    """
    Машина состояний для процесса редактирования пользователя.
    """

    waiting_for_new_data = State()


ROLES_MAP = {
    "USER_ROLE_PERMISSIONS": USER_ROLE_PERMISSIONS,
    "MANAGER_ROLE_PERMISSIONS": MANAGER_ROLE_PERMISSIONS,
    "ADMIN_ROLE_PERMISSIONS": ADMIN_ROLE_PERMISSIONS,
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
        "🏠 /start – Главное меню"
    )

    if isinstance(event, Message):
        await event.answer(text=instruction_text)
    elif isinstance(event, CallbackQuery):
        # Закрываем progress-bar; текст ≤200 симв.[8]
        await event.answer()
        await event.message.answer(text=instruction_text)
    else:
        raise TypeError("Аргумент должен быть Message или CallbackQuery")


@admin_router.callback_query(F.data == "admin_cancel")
async def cancel_cmd(query: CallbackQuery, state: FSMContext):
    await state.clear()
    await get_admin_menu_message(query)


@admin_router.message(
    Command("admin"), HasPermissionFilter([Permission.MANAGE_USERS, Permission.SET_TRIP_LIMITS])
)
async def admin_cmd(message: Message):
    await get_admin_menu_message(message)


@admin_router.message(
    Command("ticket_limits"),
    HasPermissionFilter([Permission.MANAGE_USERS, Permission.SET_TRIP_LIMITS]),
)
async def ticket_limits_menu_cmd(message: Message, session: AsyncSession):
    app_settings = await crud.get_app_settings(session)
    kb = get_limits_management_kb(default_limit=app_settings.default_daily_limit)
    await message.answer(""" 📋 Управление лимитами заявок 📋""", reply_markup=kb)


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
            • MANAGER_ROLE_PERMISSIONS (+ управление лимитами заявок)
            • ADMIN_ROLE_PERMISSIONS (+ управление пользователями)

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
            "Пользователь с таким <b>Telegram ID</b> или <b>Megaplan ID</b> "
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
