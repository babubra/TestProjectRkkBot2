import asyncio
import datetime
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

    yesterday = datetime.date.today() - datetime.timedelta(days=1)
    deals = await crm_client.get_deals(visit_date=yesterday)
    print(len(deals))

    deal = await crm_client.create_deal(
        description="ТЕСТ",
        manager_id=1000003,
        ticket_visit_datetime=datetime.datetime.now(),
        megaplan_user_id=1000003,
        name="ТЕСТ",
        cadastral_to_visit="ТЕСТ",
        address_to_visit="ТЕСТ",
    )
    print(deal)


if __name__ == "__main__":
    asyncio.run(main())
