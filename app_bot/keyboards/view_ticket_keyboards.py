from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


class DealActionCallback(CallbackData, prefix="deal"):
    """
    Фабрика Callback-данных для действий со сделкой.
    - action: 'add_files' - конкретное действие.
    - deal_id: ID сделки, с которой совершается действие.
    """

    action: str
    deal_id: str


class ViewDateCallback(CallbackData, prefix="view_date"):
    """
    Фабрика Callback-данных для просмотра заявок на определенную дату.
    - date: строка даты в формате ISO (YYYY-MM-DD)
    """

    date: str


def get_deal_action_kb(deal_id: str | int) -> InlineKeyboardMarkup:
    """
    Создает ��нлайн-клавиатуру с действиями для конкретной сделки.
    """
    builder = InlineKeyboardBuilder()

    builder.button(
        text="📎 Добавить файлы с выезда",
        callback_data=DealActionCallback(action="add_files", deal_id=str(deal_id)).pack(),
    )

    return builder.as_markup()


def get_map_url_kb(map_url: str) -> InlineKeyboardMarkup:
    """
    Создает инлайн-клавиатуру с кнопкой для перехода по URL карты.
    """
    builder = InlineKeyboardBuilder()
    builder.button(text="Открыть карту 🗺️", url=map_url)
    return builder.as_markup()
