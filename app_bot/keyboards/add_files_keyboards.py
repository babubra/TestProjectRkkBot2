from collections import Counter

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app_bot.keyboards.add_ticket_keyboards import AddTicketTimeCallback


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
        time_for_callback = f"{hour:02d}00"

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
