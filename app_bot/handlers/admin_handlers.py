from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

# Импортируем роли и функции для работы с БД
from app_bot.config.user_roles_config import (
    USER_ROLE_PERMISSIONS,
    MANAGER_ROLE_PERMISSIONS,
    ADMIN_ROLE_PERMISSIONS,
)
from app_bot.database import crud
from app_bot.keyboards.admin_keyboards import get_cancel_kb

admin_router = Router()


class CreateUserFSM(StatesGroup):
    """
    Машина состояний для процесса создания нового пользователя.
    """

    waiting_for_user_data = State()


ROLES_MAP = {
    "USER_ROLE_PERMISSIONS": USER_ROLE_PERMISSIONS,
    "MANAGER_ROLE_PERMISSIONS": MANAGER_ROLE_PERMISSIONS,
    "ADMIN_ROLE_PERMISSIONS": ADMIN_ROLE_PERMISSIONS,
}


@admin_router.message(Command("admin"))
async def admin_cmd(message: Message):
    instruction_text = """
        🔧 **РЕЖИМ АДМИНИСТРАТОРА** 🔧

        Добро пожаловать в панель управления!
        Выберите необходимое действие:

        👤 /create_user - Создание нового пользователя
        📋 /users_list - Просмотр всех пользователей
        
        🏠 /start - Главное меню        
        """
    await message.answer(text=instruction_text)


@admin_router.message(Command("create_user"))
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


@admin_router.message(CreateUserFSM.waiting_for_user_data, F.text)
async def process_and_save_user_data_cmd(
    message: Message, state: FSMContext, session: AsyncSession
):
    """
    Этот хендлер ловит сообщение с данными, проверяет их
    и сразу сохраняет в БД без дополнительного подтверждения.
    """
    pass
