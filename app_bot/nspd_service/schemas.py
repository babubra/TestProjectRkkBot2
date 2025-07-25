from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class CadastralObject(BaseModel):
    """
    Структурированная информация о кадастровом объекте.

    Модель используется для валидации и удобного доступа к данным,
    полученным от API nspd.gov.ru.
    """

    cadastral_number: str = Field(description="Кадастровый номер")
    category_name: Optional[str] = Field(
        None, description="Категория объекта (Здание, Участок и т.д.)"
    )
    address: Optional[str] = Field(None, description="Читаемый адрес объекта")

    # Основные характеристики объекта
    area_sq_m: Optional[float] = Field(None, description="Площадь в квадратных метрах")
    extension_m: Optional[float] = Field(
        None, description="Протяженность в метрах (для линейных объектов)"
    )

    # Геометрия
    geometry_type: Optional[Literal["Point", "Polygon"]] = Field(
        None, description="Тип геометрии"
    )
    coordinates_wgs84: Optional[Any] = Field(None, description="Координаты в системе WGS 84")
    centroid_wgs84: Optional[list[float]] = Field(
        None, description="Центр полигона [lon, lat] или [lat, lon]"
    )

    # Связанные объекты
    related_cadastral_numbers: Optional[list[str]] = Field(
        None, description="Список кадастровых номеров связанных дочерних объектов"
    )

    original_geometry: Optional[dict[str, Any]] = Field(
        None, description="Исходные данные геометрии от сервера"
    )

    @field_validator("area_sq_m", "extension_m")
    def clean_float_fields(cls, v):
        if v is not None:
            return float(v)
        return v
