import logging
from datetime import timedelta, timezone  # Добавим импорт datetime

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app_bot.config.config import get_env_settings
from app_bot.crm_service.crm_client import CRMClient
from app_bot.utils.ui_utils import get_main_menu_message


common_router = Router()
logger = logging.getLogger(__name__)

settings = get_env_settings()
APP_TIMEZONE = timezone(timedelta(hours=settings.APP_TIMEZONE_OFFSET))


@common_router.message(CommandStart())
async def start_cmd(message: Message, session: AsyncSession, crm_client: CRMClient):
    """
    Обрабатывает команду /start.
    Приветствует пользователя и показывает главное меню с актуальным
    количеством всех заявок на сегодня и завтра.
    """
    await get_main_menu_message(message=message, session=session, crm_client=crm_client)
