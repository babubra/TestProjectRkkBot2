import asyncio
from .config.config import get_env_settings
from .database.crud import get_user_by_telegram_id, create_user, get_users
from .database.engine import DatabaseManager
from .crm_service.crm_client import CRMClient
import logging
from .config.user_roles_config import MANAGER_ROLE_PERMISSIONS

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
    await db_manager.drop_all()
    # async with db_manager.session() as session:
    #     all_users_sequence = await get_users(session, limit=10)
    # print(f"ВСЕ ЮЗЕРЫ {all_users_sequence}")


if __name__ == "__main__":
    asyncio.run(main())
