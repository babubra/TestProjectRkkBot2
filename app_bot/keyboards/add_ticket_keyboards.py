import datetime
from collections import Counter

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


class AddTicketDateCallback(CallbackData, prefix="add_ticket_date"):
    """
    Фабрика Callback-данных для выбора даты при создании заявки.
    - action: 'select_date' - действие выбора даты.
    - date_iso: Выбранная дата в формате ISO (ГГГГ-ММ-ДД).
    """

    action: str
    date_iso: str


class AddTicketTimeCallback(CallbackData, prefix="add_ticket_time"):
    """
    Фабрика Callback-данных для выбора времени при создании заявки.
    - action: 'select_time'
    - time_iso: Выбранное время в формате ISO (ЧЧ:ММ).
    """

    action: str
    time_str: str  # Используем строку, т.к. datetime.time не сериализуется напрямую


def get_add_ticket_date_kb(
    daily_stats: dict[datetime.date, tuple[int, int]],
) -> InlineKeyboardMarkup:
    """
    Создает инлайн-клавиатуру для выбора даты выезда.

    Отображает кнопку "Без выезда", 5 ближайших дней, их загруженность (принято/лимит)
    и помечает дни с достигнутым лимитом.

    Args:
        daily_stats: Словарь, где ключ - дата, а значение - кортеж (принято, лимит).
        Пример: {datetime.date(2024, 7, 8): (5, 10)}

    Returns:
        Инлайн-клавиатура для выбора даты.
    """

    # TODO При добавлении времени также на кнопках добавления времени
    #  надо проверять количество завяок на конкретное время. то есть пробрасывать в
    # хендлер добавления времени список сделок и заполнять кнопки добавления времени.
    # также надо будет ввести новый параметр - максимаольное количество заявок на одно время

    builder = InlineKeyboardBuilder()
    today = datetime.date.today()
    day_names_ru = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")

    builder.button(text="🏠 Без выезда", callback_data="add_ticket_no_visit")

    # --- Генерация кнопок с датами (остается без изменений) ---
    for i in range(5):  # 5 дней, включая сегодня
        current_date = today + datetime.timedelta(days=i)
        stats = daily_stats.get(current_date, (0, 0))  # (принято, лимит)
        count, limit = stats

        # Определяем, заполнен ли день
        is_full = count >= limit
        limit_marker = " 🔴" if is_full else ""

        # Формируем текст для кнопки
        if i == 0:
            button_text = f"Сегодня ({count}/{limit}){limit_marker}"
        else:
            day_name = day_names_ru[current_date.weekday()]
            date_str = current_date.strftime("%d.%m")
            button_text = f"{day_name}, {date_str} ({count}/{limit}){limit_marker}"

        builder.button(
            text=button_text,
            callback_data=AddTicketDateCallback(
                action="select_date", date_iso=current_date.isoformat()
            ).pack(),
        )

    builder.button(text="❌ Отмена", callback_data="add_ticket_cancel")

    # Располагаем все кнопки по одной в строке
    builder.adjust(1)

    return builder.as_markup()


def get_add_ticket_time_kb(
    occupied_slots: list[str], brigades_count: int
) -> InlineKeyboardMarkup:
    """
    Создает инлайн-клавиатуру для выбора времени выезда,
    учитывая занятые слоты.
    """
    builder = InlineKeyboardBuilder()

    # Считаем, сколько раз каждый слот занят
    # Например: {'09:00': 1, '12:00': 2}
    occupation_counter = Counter(occupied_slots)

    for hour in range(8, 18):
        time_for_button = f"{hour:02d}:00"
        time_for_callback = f"{hour:02d}-00"

        # --- НОВАЯ ЛОГИКА ОТОБРАЖЕНИЯ ---
        current_occupation = occupation_counter.get(time_for_button, 0)

        button_text = f"{time_for_button}"
        if current_occupation > 0:
            # Если слот занят, показываем счетчик
            button_text += f" ({current_occupation}/{brigades_count})"
            if current_occupation >= brigades_count:
                # Если все бригады заняты, добавляем маркер
                button_text += " 🔴"
        # --- КОНЕЦ НОВОЙ ЛОГИКИ ---

        builder.button(
            text=button_text,
            callback_data=AddTicketTimeCallback(
                action="select_time", time_str=time_for_callback
            ).pack(),
        )

    builder.button(text="❌ Отмена", callback_data="add_ticket_cancel")

    time_buttons_count = 10
    adjust_pattern = [2] * (time_buttons_count // 2)
    adjust_pattern.append(1)

    builder.adjust(*adjust_pattern)

    return builder.as_markup()
