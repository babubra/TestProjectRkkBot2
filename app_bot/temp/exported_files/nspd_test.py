import asyncio
import json
import traceback
from typing import Any, List, Literal, Optional
from urllib.parse import urlencode

import httpx
from pydantic import BaseModel, Field, field_validator
from pyproj import CRS, Transformer


# --- Конфигурация систем координат ---
CRS_WEB_MERCATOR = CRS.from_epsg(3857)
CRS_WGS84 = CRS.from_epsg(4326)


# --- Модель данных для результата (Pydantic) ---
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
    related_cadastral_numbers: Optional[List[str]] = Field(
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


class NspdClient:
    """
    Асинхронный клиент для взаимодействия с геопорталом nspd.gov.ru.

    Предназначен для получения структурированной информации о кадастровых объектах
    (участках, зданиях, сооружениях) по их кадастровому номеру.

    Ключевые возможности:
    - Возвращает данные в виде удобной Pydantic-модели `CadastralObject`.
    - Корректно обрабатывает разные типы геометрии (Полигоны, Точки).
    - Автоматически вычисляет центр (центроид) для объектов-полигонов.
    - Различает характеристики "площадь" и "протяженность".
    - Имеет встроенную обработку таймаутов и сетевых ошибок.
    - **Находит связанные кадастровые номера (например, здания на участке).**
    """

    def __init__(self, timeout: float = 5.0):
        """
        Инициализирует асинхронный клиент.

        :param timeout: Таймаут ожидания ответа от сервера в секундах.
        """
        self.base_url = "https://nspd.gov.ru"
        self._transformer = Transformer.from_crs(CRS_WEB_MERCATOR, CRS_WGS84, always_xy=True)
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
                "Accept": "application/json, text/plain, */*",
                "Referer": f"{self.base_url}/map",
            },
            timeout=timeout,
            verify=False,
        )

    def _transform_polygon(
        self, polygon_coords: list[list[list[float]]]
    ) -> list[list[list[float]]]:
        return [
            [list(self._transformer.transform(x, y)) for x, y in ring]
            for ring in polygon_coords
        ]

    def _transform_point(self, point_coords: list[float]) -> list[float]:
        return list(self._transformer.transform(point_coords[0], point_coords[1]))

    def _calculate_polygon_centroid(
        self, polygon_wgs84: list[list[list[float]]]
    ) -> list[float]:
        outer_ring = polygon_wgs84[0]
        num_points = len(outer_ring) - 1
        if num_points < 1:
            return []
        sum_lon = sum(point[0] for point in outer_ring[:-1])
        sum_lat = sum(point[1] for point in outer_ring[:-1])
        return [sum_lon / num_points, sum_lat / num_points]

    async def _get_related_objects(self, geom_id: int, category_id: int) -> Optional[List[str]]:
        """Вспомогательный метод для получения связанных объектов."""
        params = {"tabClass": "objectsList", "categoryId": category_id, "geomId": geom_id}
        url = f"/api/geoportal/v1/tab-group-data?{urlencode(params)}"
        try:
            response = await self.client.get(url)
            if response.status_code != 200:
                return None

            data = response.json()
            related_numbers = []
            if data and isinstance(data.get("object"), list):
                for item in data["object"]:
                    if isinstance(item.get("value"), list):
                        related_numbers.extend(item["value"])

            if related_numbers:
                print(f"-> Найдены связанные объекты: {related_numbers}")
                return related_numbers
            return None
        except (httpx.RequestError, json.JSONDecodeError) as e:
            print(f"-> Не удалось получить связанные объекты: {type(e).__name__}")
            return None

    async def get_object_info(
        self, cadastral_number: str, coords_order: Literal["lon,lat", "lat,lon"] = "lon,lat"
    ) -> Optional[CadastralObject]:
        """
        Основной метод для получения информации об объекте по кадастровому номеру.

        В случае успеха возвращает Pydantic-модель `CadastralObject`, содержащую
        всю извлеченную информацию. В случае любой ошибки (объект не найден,
        сетевая ошибка, таймаут) возвращает `None`.

        :param cadastral_number: Кадастровый номер объекта для поиска (например, "39:03:000000:4646").
        :param coords_order: Порядок возвращаемых координат.
        'lon,lat' - долгота, широта (стандарт WGS 84).
        'lat,lon' - широта, долгота (удобно для API Яндекс.Карт).
        По умолчанию 'lon,lat'.
        :return: Экземпляр `CadastralObject` или `None` в случае ошибки.
        """
        print(f"Ищу информацию по кадастровому номеру: {cadastral_number}")
        search_params = {"thematicSearchId": 1, "query": cadastral_number}
        search_url = f"/api/geoportal/v2/search/geoportal?{urlencode(search_params)}"
        try:
            response = await self.client.get(search_url)
            response.raise_for_status()
            data = response.json()

            if not data.get("data") or not data["data"].get("features"):
                print(f"-> Объект с номером {cadastral_number} не найден.")
                return None

            feature = data["data"]["features"][0]
            properties = feature.get("properties", {})
            options = properties.get("options", {})
            geometry = feature.get("geometry")

            cad_num = options.get("cad_num") or options.get("cad_number")
            address = options.get("readable_address") or options.get("address_readable_address")
            area = (
                options.get("specified_area")
                or options.get("build_record_area")
                or options.get("params_area")
                or options.get("land_record_area")
                or options.get("area")
            )
            extension = options.get("params_extension")

            result_data = {
                "cadastral_number": cad_num,
                "category_name": properties.get("categoryName"),
                "address": address,
                "area_sq_m": area,
                "extension_m": extension,
                "original_geometry": geometry,
            }

            # --- Новая логика для получения связанных объектов ---
            geom_id = feature.get("id")
            category_id = properties.get("category")
            if geom_id and category_id:
                related_numbers = await self._get_related_objects(geom_id, category_id)
                if related_numbers:
                    result_data["related_cadastral_numbers"] = related_numbers
            # --- Конец новой логики ---

            if geometry and geometry.get("coordinates"):
                geom_type = geometry.get("type")
                result_data["geometry_type"] = geom_type
                if geom_type == "Polygon":
                    coords_wgs84 = self._transform_polygon(geometry["coordinates"])
                    result_data["coordinates_wgs84"] = coords_wgs84
                    result_data["centroid_wgs84"] = self._calculate_polygon_centroid(
                        coords_wgs84
                    )
                elif geom_type == "Point":
                    result_data["coordinates_wgs84"] = self._transform_point(
                        geometry["coordinates"]
                    )

            if coords_order == "lat,lon":
                coords = result_data.get("coordinates_wgs84")
                if coords is not None:
                    if result_data.get("geometry_type") == "Point":
                        coords.reverse()
                    elif result_data.get("geometry_type") == "Polygon":
                        result_data["coordinates_wgs84"] = [
                            [[point[1], point[0]] for point in ring] for ring in coords
                        ]
                centroid = result_data.get("centroid_wgs84")
                if centroid:
                    centroid.reverse()

            return CadastralObject.model_validate(result_data)

        except (
            httpx.TimeoutException,
            httpx.ConnectError,
            httpx.HTTPStatusError,
            json.JSONDecodeError,
        ) as e:
            print(f"-> Произошла сетевая ошибка или ошибка API: {type(e).__name__}")
            return None
        except Exception:
            print(
                f"-> Произошла непредвиденная ошибка при обработке номера {cadastral_number}:"
            )
            traceback.print_exc()
            return None

    async def close(self):
        """Корректно закрывает сессию httpx клиента."""
        if not self.client.is_closed:
            await self.client.aclose()


async def main():
    """Тестовая функция для демонстрации работы клиента с разными типами объектов."""
    client = NspdClient(timeout=10.0)  # Увеличил таймаут для надежности
    test_numbers = {
        "ТЕСТ 1: Участок со связанным объектом": "39:15:110802:30",
        "ТЕСТ 2: Участок без связанных объектов": "39:05:050405:310",
    }

    for description, number in test_numbers.items():
        print("\n" + "=" * 50 + f"\n{description}")
        # Получаем объект с порядком lon,lat по умолчанию
        obj = await client.get_object_info(number, coords_order="lon,lat")
        if obj:
            print("  Статус: УСПЕХ")
            print(f"  Кадастровый номер: {obj.cadastral_number}")
            print(f"  Тип объекта: {obj.category_name}")
            print(f"  Адрес: {obj.address}")
            if obj.area_sq_m is not None and obj.area_sq_m > 0:
                print(f"  Площадь: {obj.area_sq_m} кв.м.")
            if obj.extension_m is not None and obj.extension_m > 0:
                print(f"  Протяженность: {obj.extension_m} м.")
            if obj.centroid_wgs84:
                print(f"  Центр (lon, lat): {obj.centroid_wgs84}")

            # Выводим связанные объекты, если они есть
            if obj.related_cadastral_numbers:
                print(f"  Связанные объекты: {obj.related_cadastral_numbers}")
            else:
                print("  Связанные объекты: не найдены")

        else:
            print("  Статус: НЕУДАЧА")

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
