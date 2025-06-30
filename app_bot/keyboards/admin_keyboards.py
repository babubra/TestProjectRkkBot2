import datetime

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


class DateLimitCallback(CallbackData, prefix="limit_date"):
    """
    Фабрика Callback-данных для действий с лимитами на конкретную дату.
    - prefix: 'limit_date' - общий префикс.
    - action: 'edit_limit' - действие (можно расширить в будущем, например, 'view_limit').
    - date_iso: Дата в формате ISO (ГГГГ-ММ-ДД) для надежной передачи и парсинга.
    """

    action: str
    date_iso: str


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
        text="📅 Редактировать лимиты на дату",
        callback_data="admin_limits_date",
    )
    builder.button(
        text="🔍 Просмотреть лимиты",
        callback_data="admin_limits_view",
    )
    builder.button(text="❌ Отмена", callback_data="admin_cancel")
    builder.adjust(1)
    return builder.as_markup()


def get_view_limits_for_date_kb(
    daily_limits: dict[datetime.date, int], default_limit: int
) -> InlineKeyboardMarkup:
    """
    Создает инлайн-клавиатуру для быстрого выбора даты для редактирования лимита.
    Включает кнопки на сегодня и следующие 6 дней, отображая день недели и текущий лимит.
    Помечает иконкой ✨ лимиты, отличные от стандартного.

    Args:
        daily_limits (dict[datetime.date, int]): Словарь с датами и их лимитами.
        default_limit (int): Лимит по умолчанию для сравнения.

    Returns:
        Инлайн-клавиатура с кнопками дат.
    """
    builder = InlineKeyboardBuilder()
    today = datetime.date.today()
    day_names_ru = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")

    # --- Обработка кнопок с датами ---

    # Кнопка "Сегодня"
    today_limit = daily_limits.get(today, "?")
    today_day_name = day_names_ru[today.weekday()]
    # Определяем, нужен ли маркер для сегодняшнего дня
    today_marker = (
        " ✨" if isinstance(today_limit, int) and today_limit != default_limit else ""
    )
    builder.button(
        text=f"Сегодня ({today_day_name}, {today_limit}){today_marker}",
        callback_data=DateLimitCallback(action="edit_limit", date_iso=today.isoformat()).pack(),
    )

    # Кнопки на следующие 6 дней
    for i in range(1, 7):
        current_date = today + datetime.timedelta(days=i)
        limit = daily_limits.get(current_date, "?")
        day_name = day_names_ru[current_date.weekday()]

        # Определяем, нужен ли маркер для текущей даты в цикле
        override_marker = " ✨" if isinstance(limit, int) and limit != default_limit else ""

        button_text = (
            f"{day_name}, {current_date.strftime('%d.%m.%y')} ({limit}){override_marker}"
        )

        builder.button(
            text=button_text,
            callback_data=DateLimitCallback(
                action="edit_limit", date_iso=current_date.isoformat()
            ).pack(),
        )

    # --- Обработка кнопок действий ---

    builder.button(text="⌨️ Ввести дату вручную", callback_data="admin_limits_manual_input")
    builder.button(text="❌ Отмена", callback_data="admin_cancel")

    builder.adjust(2, 2, 2, 1, 1, 1)

    return builder.as_markup()
