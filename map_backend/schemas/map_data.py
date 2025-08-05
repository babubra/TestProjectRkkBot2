"""
Pydantic-схемы, описывающие структуру данных для API-ответов.
"""

from typing import Optional

from pydantic import BaseModel


class MapLocation(BaseModel):
    """Схема для координат на карте."""
    
    latitude: float
    longitude: float


class MapDealData(BaseModel):
    """Схема для данных сделки на карте."""
    
    deal_id: int
    deal_name: str
    deal_status: str
    location: Optional[MapLocation] = None
    address: Optional[str] = None
    cadastral_number: Optional[str] = None
    visit_date: Optional[str] = None
    description: Optional[str] = None


# __all__ сообщает Python и анализаторам кода, что эти имена
# являются частью публичного API этого модуля.
__all__ = [
    "MapDealData",
    "MapLocation",
]
