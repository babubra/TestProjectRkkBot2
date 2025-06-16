from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


class UserCallback(CallbackData, prefix="user_manage"):
    """
    Фабрика Callback-данных для действий с пользователями.
    - prefix: 'user_manage' - общий префикс для всех колбэков этого типа.
    - action: 'edit' или 'delete' - конкретное действие.
    - user_id: ID пользователя в Telegram, с которым совершается действие.
    """

    action: str
    user_telegram_id: int


def get_cancel_kb() -> InlineKeyboardMarkup:
    """
    Создает инлайн-клавиатуру с кнопками 'Отмена'
    """
    builder = InlineKeyboardBuilder()

    builder.button(text="❌ Отмена", callback_data="admin_cancel")

    return builder.as_markup()


def get_user_management_kb(user_telegram_id: int) -> InlineKeyboardMarkup:
    """
    Создает инлайн-клавиатуру с кнопками 'Удалить'
    для конкретного пользователя.

    Args:
        user_telegram_id: Telegram ID пользователя, для которого создается клавиатура.

    Returns:
        Объект инлайн-клавиатуры.
    """
    builder = InlineKeyboardBuilder()

    # Кнопка "Редактировать"
    # builder.button(
    #     text="✍️ Редактировать",
    #     callback_data=UserCallback(action="edit", user_telegram_id=user_telegram_id).pack(),
    # )

    # Кнопка "Удалить"
    builder.button(
        text="🗑️ Удалить",
        callback_data=UserCallback(action="delete", user_telegram_id=user_telegram_id).pack(),
    )

    # Располагаем кнопки в один ряд
    # builder.adjust(2)

    return builder.as_markup()


def get_limits_management_kb(default_limit: int) -> InlineKeyboardMarkup:
    """
    Инлайн-клавиатура для управления лимитами заявок.
    Содержит кнопки Лимиты по умолчанию, Лимиты на дату, Отмена.
    """

    builder = InlineKeyboardBuilder()
    builder.button(
        text=f"📊 Изменить лимит по умолчанию ({default_limit})",
        callback_data="admin_limits_default",
    )
    builder.button(
        text="📅 Лимиты на дату",
        callback_data="admin_limits_date",
    )
    builder.button(text="❌ Отмена", callback_data="admin_cancel")
    builder.adjust(1)
    return builder.as_markup()
