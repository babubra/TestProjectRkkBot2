from pydantic import BaseModel


class MapLocation(BaseModel):
    """Координаты одного кадастрового объекта."""

    cadastral_number: str
    coords: list[float]  # [longitude, latitude]


class MapDealData(BaseModel):
    """Структурированные данные по одной сделке для карты."""

    deal_id: str
    deal_url: str
    deal_name: str
    visit_time: str
    executors: list[str]
    locations: list[MapLocation]
