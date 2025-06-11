from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup


def get_cancel_kb() -> InlineKeyboardMarkup:
    """
    Создает инлайн-клавиатуру с кнопками 'Отмена'
    """
    builder = InlineKeyboardBuilder()

    builder.button(text="❌ Отмена", callback_data="cancel_user_creation")

    return builder.as_markup()
