from aiogram import Router, types
from aiogram.filters import Command
import logging
from app_bot.database.engine import DatabaseManager
from app_bot.database.crud import get_users
from app_bot.database.models import User  # Для аннотации типов

admin_router = Router()
logger = logging.getLogger(__name__)


@admin_router.message(Command("admin"))
async def cmd_admin(message: types.Message):
    await message.answer(
        "Добро пожаловать в админ-панель\n\n"
        "Доступные команды:\n"
        "/users_list - Просмотр списка пользователей бота\n"
        "/add_user - Просмотр списка пользователей бота\n"
    )


@admin_router.message(Command("users_list"))
async def cmd_users_list(
    message: types.Message,
    db_manager: DatabaseManager,  # Получаем db_manager из контекста диспетчера
):
    """
    Обработчик команды /users_list.
    Отображает список пользователей бота, каждого в отдельном сообщении.
    """
    # Пока не делаем проверку прав, как и договаривались
    # В будущем здесь будет проверка полномочий пользователя

    try:
        async with db_manager.session() as session:  # Открываем сессию БД
            users: list[User] = await get_users(session, limit=20)

        if not users:
            await message.answer("В базе данных пока нет пользователей.")
            await message.answer(
                "Добро пожаловать в админ-панель\n\n"
                "Доступные команды:\n"
                "/users_list - Просмотр списка пользователей бота\n"
                "/add_user - Просмотр списка пользователей бота\n"
            )
            return

        await message.answer("<b>Список пользователей бота:</b>\n")

        for user in users:
            username = f"@{user.username}" if user.username else "N/A"
            megaplan_id = (
                user.megaplan_user_id if user.megaplan_user_id is not None else "N/A"
            )
            telegram_id = user.telegram_id if user.telegram_id is not None else "N/A"

            user_info_text = (
                f"👤 <b>Пользователь:</b>\n"
                f"ID: <code>{user.telegram_id}</code>\n"
                f"Username: {username}\n"
                f"Megaplan ID: {megaplan_id}\n"
                f"Telegram ID: {telegram_id}\n"
                f"Права: {user.permissions}\n"
                f"Добавлен: {user.created_at.strftime('%d.%m.%Y')}"
            )

            # Отправляем информацию о каждом пользователе отдельным сообщением
            # В будущем сюда можно будет добавить reply_markup с инлайн-клавиатурой
            await message.answer(user_info_text)

    except Exception as e:
        logger.error(f"Ошибка при получении списка пользователей: {e}", exc_info=True)
        await message.answer(f"Ошибка при получении списка пользователей: {e}")
