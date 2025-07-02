from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def get_add_files_kb() -> InlineKeyboardMarkup:
    """
    Создает клавиатуру для процесса добавления файлов.
    Содержит кнопки "Завершить и прикрепить" и "Отмена".
    """
    builder = InlineKeyboardBuilder()

    builder.button(text="✅ Завершить и прикрепить", callback_data="add_files_complete")
    builder.button(text="❌ Отмена", callback_data="add_files_cancel")
    builder.adjust(1)
    return builder.as_markup()
