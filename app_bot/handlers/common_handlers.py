from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def get_main_menu_kb() -> InlineKeyboardMarkup:
    """
    Создает инлайн-клавиатуру для главного меню пользователя.
    """
    builder = InlineKeyboardBuilder()

    builder.button(text="➕ Добавить заявку", callback_data="add_ticket")
    builder.button(text="🗓️ Заявки на сегодня", callback_data="view_tickets_today")
    builder.button(text="🗓️ Заявки на завтра", callback_data="view_tickets_tomorrow")
    builder.button(text="📅 Заявки на другую дату", callback_data="view_tickets_other_date")

    # Располагаем все кнопки в один столбец
    builder.adjust(1)

    return builder.as_markup()
