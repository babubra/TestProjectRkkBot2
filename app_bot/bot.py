import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app_bot.crm_service.crm_client import CRMClient
from app_bot.middlewares.crm_client_middleware import CrmClientMiddleware
from app_bot.middlewares.db_session_middleware import DbSessionMiddleware

from .config.config import get_env_settings
from .database.engine import DatabaseManager
from .handlers.admin_handlers import admin_router
from .handlers.common_handlers import common_router


logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)

# Отключаем debug логи от aiosqlite
logging.getLogger("aiosqlite").setLevel(logging.INFO)

logger = logging.getLogger(__name__)


async def main() -> None:
    env_settings = get_env_settings()
    crm_client = CRMClient(
        base_url=env_settings.MEGAPLAN_BASE_URL,
        username=env_settings.MEGAPLAN_LOGIN,
        password=env_settings.MEGAPLAN_PASSWORD,
        program_id=env_settings.MEGAPLAN_PROGRAM_ID,
    )
    db_manager = DatabaseManager(url=env_settings.DATABASE_URL)
    await db_manager.create_all()

    default_props = DefaultBotProperties(parse_mode=ParseMode.HTML)
    bot = Bot(token=env_settings.BOT_TOKEN, default=default_props)

    dp = Dispatcher()

    dp.update.middleware(DbSessionMiddleware(session_pool=db_manager.session_factory))
    dp.update.middleware(CrmClientMiddleware(crm_client=crm_client))

    dp.include_router(admin_router)
    dp.include_router(common_router)

    await bot.delete_webhook(drop_pending_updates=True)

    try:
        logger.info("Запуск полинга...")
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Ошибка при работе бота: {e}", exc_info=True)
    finally:
        logger.info("Остановка бота...")
        # Корректное закрытие сессии бота
        await bot.session.close()
        logger.info("Сессия бота закрыта.")
        # # Корректное закрытие сессии CRM клиента
        # if crm_client:  # Добавим проверку, что crm_client был успешно инициализирован
        #     await crm_client.close_session()
        #     logger.info("Сессия CRM клиента закрыта.")
        # # Корректное освобождение ресурсов DatabaseManager
        # if db_manager:  # Добавим проверку, что db_manager был успешно инициализирован
        #     await db_manager.dispose()
        #     logger.info("Пул соединений с БД освобожден.")
        logger.info("Бот успешно остановлен.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Выполнение прервано пользователем (KeyboardInterrupt/SystemExit).")


# async with db_manager.session() as session:
#     all_users_sequence = await get_users(session, limit=10)
# print(f"ВСЕ ЮЗЕРЫ {all_users_sequence}")

# async with db_manager.session() as session:
#     app_settings = await get_app_settings(session=session)
#     print(app_settings.default_daily_limit)
#     target_date = datetime.date.fromisoformat("2024-05-27")
#     daily_limit_override = await set_daily_limit_override(
#         session=session, target_date=target_date, limit=66
#     )
#     print(daily_limit_override.daily_limit)
# crm_client = CRMClient(
#     base_url=env_settings.MEGAPLAN_BASE_URL,
#     username=env_settings.MEGAPLAN_LOGIN,
#     password=env_settings.MEGAPLAN_PASSWORD,
#     program_id=env_settings.MEGAPLAN_PROGRAM_ID,
# )
