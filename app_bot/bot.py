import asyncio
from .config.config import get_env_settings
from .database.crud import (
    get_user_by_telegram_id,
    create_user,
    get_users,
    get_app_settings,
    set_daily_limit_override,
)
from .database.engine import DatabaseManager
from .crm_service.crm_client import CRMClient
import logging
from .config.user_roles_config import MANAGER_ROLE_PERMISSIONS
from .database.models import AppSettings
import datetime

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
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


if __name__ == "__main__":
    asyncio.run(main())
