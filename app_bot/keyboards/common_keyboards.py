from datetime import date

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app_bot.keyboards.view_ticket_keyboards import ViewDateCallback


def get_main_menu_kb(
    tickets_today_count: int,
    limit_today: int,
    tickets_tomorrow_count: int,
    limit_tomorrow: int,
    next_days: list[tuple[date, int, int]],
    today_date: date,
    tomorrow_date: date,
) -> InlineKeyboardMarkup:
    """
    Создает инлайн-клавиатуру для главного меню пользователя.
    Отображает количество созданных заявок на сегодня, на завтра и на следующие 5 дней.

    Args:
        tickets_today_count: Количество созданных заявок на сегодня.
        limit_today: Общий лимит заявок на сегодня.
        tickets_tomorrow_count: Количество созданных заявок на завтра.
        limit_tomorrow: Общий лимит заявок на завтра.
        next_days: Список из 5 элементов вида (дата, количество, лимит) для последующих дней.

    Returns:
        Инлайн-клавиатура главного меню.
    """
    builder = InlineKeyboardBuilder()

    today_str = f"Принято {tickets_today_count} из {limit_today}"
    tomorrow_str = f"Принято {tickets_tomorrow_count} из {limit_tomorrow}"

    # Верхние кнопки по одной в ряд
    add_btn = InlineKeyboardButton(text="➕ Добавить заявку", callback_data="add_ticket")
    today_btn = InlineKeyboardButton(
        text=f"🗓️ Заявки на сегодня. ({today_str})",
        callback_data=ViewDateCallback(date=today_date.isoformat()).pack(),
    )
    tomorrow_btn = InlineKeyboardButton(
        text=f"🗓️ Заявки на завтра. ({tomorrow_str})",
        callback_data=ViewDateCallback(date=tomorrow_date.isoformat()).pack(),
    )

    builder.row(add_btn)
    builder.row(today_btn)
    builder.row(tomorrow_btn)

    # Последующие 5 дней: по две кнопки в ряд, формат текста "ДД.ММ вт 3/5" (дата, день недели, счётчик/лимит)
    date_buttons: list[InlineKeyboardButton] = []
    weekdays = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
    for dt, cnt, lim in next_days:
        abbr = weekdays[dt.weekday()]
        text = f"🗓️ {abbr} {dt.strftime('%d.%m')} {cnt}/{lim}"
        cb = ViewDateCallback(date=dt.isoformat()).pack()
        date_buttons.append(InlineKeyboardButton(text=text, callback_data=cb))

    for i in range(0, len(date_buttons), 2):
        if i + 1 < len(date_buttons):
            builder.row(date_buttons[i], date_buttons[i + 1])
        else:
            builder.row(date_buttons[i])

    # Кнопка выбора другой даты отдельно
    other_date_btn = InlineKeyboardButton(
        text="📅 Заявки на другую дату", callback_data="view_tickets_other_date"
    )
    builder.row(other_date_btn)

    return builder.as_markup()
