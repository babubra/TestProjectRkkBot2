import asyncio
from config import get_env_settings
from crm_service.crm_client import CRMClient
import logging

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

    s = await crm_client.attach_files_to_deal_visit_docs(
        file_ids=[80088, 80087], deal_id=4937
    )

    print(s)


if __name__ == "__main__":
    asyncio.run(main())
