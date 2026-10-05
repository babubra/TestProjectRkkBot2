import logging
from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from app_bot.keyboards.view_ticket_keyboards import ViewDateCallback
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app_bot.config.config import get_env_settings
from app_bot.crm_service.crm_client import CRMClient
from app_bot.keyboards.view_ticket_keyboards import get_map_url_kb
from app_bot.nspd_service.nspd_client import NspdClient
from app_bot.utils.ui_utils import (
    get_main_menu_message,
    prepare_deal_view_data,
)


logger = logging.getLogger(__name__)

view_tickets_router = Router()

settings = get_env_settings()
APP_TIMEZONE = timezone(timedelta(hours=settings.APP_TIMEZONE_OFFSET))


async def send_deal_messages(message: Message, items: list[dict]) -> None:
    """
    Отправляет подготовленные сообщения по заявкам.

    Сбой на одной заявке не должен обрывать весь список: раньше слишком длинное
    сообщение (лимит Telegram — 4096 символов) роняло обработчик целиком, и
    пользователь не получал ни эту заявку, ни все последующие.
    """
    for item in items:
        try:
            await message.answer(
                text=item["text"],
                reply_markup=item["reply_markup"],
                disable_web_page_preview=True,
            )
        except TelegramBadRequest as e:
            logger.error(
                f"Telegram отклонил сообщение по заявке "
                f"({len(item['text'])} символов): {e}"
            )
            await message.answer(
                "⚠️ Одну заявку показать не удалось — Telegram отклонил сообщение. "
                "Откройте её в CRM по кнопке ниже.",
                reply_markup=item["reply_markup"],
            )


class ViewTicketsByDateFSM(StatesGroup):
    """
    Машина состояний для процесса просмотра заявок на определенную дату.
    """

    waiting_for_date = State()


@view_tickets_router.callback_query(ViewDateCallback.filter())
async def view_deals_by_selected_date_handler(
    query: CallbackQuery,
    callback_data: ViewDateCallback,
    crm_client: CRMClient,
    session: AsyncSession,
    nspd_client: NspdClient,
):
    await query.answer()

    target_date = datetime.fromisoformat(callback_data.date).date()

    today = datetime.now(APP_TIMEZONE).date()
    if target_date == today:
        loading_text = "Загружаю заявки на сегодня..."
    elif target_date == today + timedelta(days=1):
        loading_text = "Загружаю заявки на завтра..."
    else:
        loading_text = f"Загружаю заявки на {target_date.strftime('%d.%m.%Y')}..."

    await query.message.answer(loading_text)

    result = await prepare_deal_view_data(
        crm_client=crm_client,
        start_date=target_date,
        end_date=target_date,
        nspd_client=nspd_client,
        session=session,
        user_telegram_id=query.from_user.id,
    )

    await send_deal_messages(query.message, result["messages_to_send"])

    map_url = result.get("map_url")
    if map_url:
        await send_map_url_message(query.message, map_url)

    await get_main_menu_message(query.message, session, crm_client)




@view_tickets_router.callback_query(F.data == "view_tickets_other_date")
async def view_other_date_deals_start(query: CallbackQuery, state: FSMContext):
    """
    Запускает процесс просмотра заявок на другую дату.
    Запрашивает у пользователя дату.
    """
    await query.answer()
    await query.message.answer("Введите дату в формате <b>ДД.ММ.ГГГГ</b> для просмотра заявок.")
    await state.set_state(ViewTicketsByDateFSM.waiting_for_date)


@view_tickets_router.message(ViewTicketsByDateFSM.waiting_for_date, F.text)
async def process_date_for_view(
    message: Message,
    state: FSMContext,
    crm_client: CRMClient,
    session: AsyncSession,
    nspd_client: NspdClient,
):
    """
    Обрабатывает введенную пользователем дату, загружает и отображает заявки.
    """
    await state.clear()
    try:
        target_date = datetime.strptime(message.text.strip(), "%d.%m.%Y").date()
    except ValueError:
        await message.answer(
            "❌ <b>Ошибка:</b> Неверный формат даты. Пожалуйста, используйте <b>ДД.ММ.ГГГГ</b>."
        )
        await get_main_menu_message(message, session, crm_client)
        return

    await message.answer(f"⏳ Загружаю заявки на <b>{target_date.strftime('%d.%m.%Y')}</b>...")

    result = await prepare_deal_view_data(
        crm_client=crm_client,
        start_date=target_date,
        end_date=target_date,
        nspd_client=nspd_client,
        session=session,
        user_telegram_id=message.from_user.id,
    )

    await send_deal_messages(message, result["messages_to_send"])

    map_url = result.get("map_url")
    if map_url:
        await send_map_url_message(message, map_url)

    await get_main_menu_message(message, session, crm_client)


async def send_map_url_message(message: Message, map_url: str):
    """
    Отправляет пользователю сообщение со ссылкой на карту.
    Формат сообщения зависит от того, является ли ссылка "боевой" (HTTPS)
    или "отладочной" (HTTP).
    """
    text = "🗺️ <b>Карта выездов ��отова!</b>\n\n"
    reply_markup = None
    disable_web_page_preview = True

    # Если ссылка "боевая" (начинается с https), то создаем кнопку
    if map_url.startswith("https://"):
        text += "Нажмите на кнопку ниже, чтобы открыть карту в браузере:"
        reply_markup = get_map_url_kb(map_url)
    # Если ссылка "отладочная" (localhost), то просто показываем ее для копирования
    else:
        text += (
            "Скопируйте ссылку ниже и откройте ее в браузере:\n"
            f"<code>{map_url}</code>\n\n"
            "<i>Ссылка действительна 5 минут.</i>"
        )

    await message.answer(
        text=text,
        reply_markup=reply_markup,
        disable_web_page_preview=disable_web_page_preview,
    )
