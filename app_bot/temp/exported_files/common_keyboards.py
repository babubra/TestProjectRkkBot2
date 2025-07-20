from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def get_main_menu_kb(
    tickets_today_count: int,
    limit_today: int,
    tickets_tomorrow_count: int,
    limit_tomorrow: int,
) -> InlineKeyboardMarkup:
    """
    Создает инлайн-клавиатуру для главного меню пользователя.
    Отображает количество созданных заявок на сегодня и на завтра.

    Args:
        tickets_today_count: Количество созданных заявок на сегодня.
        limit_today: Общий лимит заявок на сегодня.
        tickets_tomorrow_count: Количество созданных заявок на завтра.
        limit_tomorrow: Общий лимит заявок на завтра.

    Returns:
        Инлайн-клавиатура главного меню.
    """
    builder = InlineKeyboardBuilder()

    # Формируем строки прямо здесь, внутри функции
    today_str = f"Принято {tickets_today_count} из {limit_today}"
    tomorrow_str = f"Принято {tickets_tomorrow_count} из {limit_tomorrow}"

    builder.button(text="➕ Добавить заявку", callback_data="add_ticket")
    builder.button(
        text=f"🗓️ Заявки на сегодня. ({today_str})",
        callback_data="view_tickets_today",
    )
    builder.button(
        text=f"🗓️ Заявки на завтра. ({tomorrow_str})",
        callback_data="view_tickets_tomorrow",
    )
    builder.button(text="📅 Заявки на другую дату", callback_data="view_tickets_other_date")

    # Располагаем все кнопки в один столбец
    builder.adjust(1)

    return builder.as_markup()
