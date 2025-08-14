import asyncio
import enum
import json
import logging
import traceback
from datetime import datetime, timedelta
from typing import Literal, Optional
from urllib.parse import urlencode

import httpx
from pyproj import CRS, Transformer

from app_bot.config.config import get_env_settings
from app_bot.nspd_service.schemas import CadastralObject


logger = logging.getLogger(__name__)

# --- Конфигурация систем координат ---
CRS_WEB_MERCATOR = CRS.from_epsg(3857)
CRS_WGS84 = CRS.from_epsg(4326)


# 1. Создаем Enum для состояний для лучшей читаемости
class CircuitState(enum.Enum):
    CLOSED = "CLOSED"  # Запросы разрешены
    OPEN = "OPEN"  # Запросы блокируются
    HALF_OPEN = "HALF_OPEN"  # Один тестовый запрос разрешен


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

    def __init__(self, timeout: float = 5.0, cooldown_minutes: int = 5):
        """
        Инициализирует асинхронный клиент.

        :param timeout: Таймаут ожидания ответа от сервера в секундах.
        :param cooldown_minutes: Время в минутах, на которое блокируются запросы после сбоя.
        """
        self.base_url = "https://nspd.gov.ru"
        self._transformer = Transformer.from_crs(CRS_WEB_MERCATOR, CRS_WGS84, always_xy=True)

        # Получаем настройки из конфигурации
        settings = get_env_settings()

        # Настройка прокси
        proxy = None
        if settings.NSPD_PROXY:
            # Формат: user:password@host:port
            proxy = f"http://{settings.NSPD_PROXY}"
            logger.info(f"NSPD_CLIENT: Используется прокси для запросов к {self.base_url}")

        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
                "Accept": "application/json, text/plain, */*",
                "Referer": f"{self.base_url}/map",
            },
            timeout=timeout,
            verify=False,
            proxy=proxy,
        )

        # --- ПОЛЯ ДЛЯ CIRCUIT BREAKER ---
        self._circuit_state = CircuitState.CLOSED
        self._cooldown_period = timedelta(minutes=cooldown_minutes)
        self._last_failure_time: datetime | None = None
        # Блокировка, чтобы избежать гонки состояний при одновременных запросах
        self._lock = asyncio.Lock()
        # Счетчик последовательных ошибок
        self._failure_count = 0
        # Порог ошибок для размыкания цепи
        self._failure_threshold = 2

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

    async def _get_related_objects(self, geom_id: int, category_id: int) -> Optional[list[str]]:
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
        # --- НАЧАЛО ЛОГИКИ CIRCUIT BREAKER ---
        async with self._lock:
            if self._circuit_state == CircuitState.OPEN:
                # Проверяем, не пора ли попробовать снова
                if datetime.now() > self._last_failure_time + self._cooldown_period:
                    self._circuit_state = CircuitState.HALF_OPEN
                    logger.warning(
                        "NSPD_CLIENT: Cooldown over. Circuit is now HALF-OPEN. Trying one request..."
                    )
                else:
                    # Еще не время, быстро отказываем
                    logger.warning(
                        f"NSPD_CLIENT: Circuit is OPEN. Failing fast for {cadastral_number}."
                    )
                    return None
        # --- КОНЕЦ ЛОГИКИ CIRCUIT BREAKER ---

        print(f"Ищу информацию по кадастровому номеру: {cadastral_number}")
        search_params = {"thematicSearchId": 1, "query": cadastral_number}
        search_url = f"/api/geoportal/v2/search/geoportal?{urlencode(search_params)}"
        try:
            response = await self.client.get(search_url)
            response.raise_for_status()
            data = response.json()

            # --- Обработка УСПЕХА ---
            await self._handle_success()

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

            geom_id = feature.get("id")
            category_id = properties.get("category")
            if geom_id and category_id:
                related_numbers = await self._get_related_objects(geom_id, category_id)
                if related_numbers:
                    result_data["related_cadastral_numbers"] = related_numbers

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
            await self._handle_failure()
            return None
        except Exception:
            print(
                f"-> Произошла непредвиденная ошибка при обработке номера {cadastral_number}:"
            )
            traceback.print_exc()
            return None

    async def _handle_success(self):
        """Обрабатывает успешный запрос, сбрасывая счетчики и замыкая цепь."""
        async with self._lock:
            if self._circuit_state == CircuitState.HALF_OPEN:
                logger.info("NSPD_CLIENT: Success on HALF-OPEN. Circuit is now CLOSED.")
            self._failure_count = 0
            self._circuit_state = CircuitState.CLOSED

    async def _handle_failure(self):
        """Обрабатывает сбойный запрос, увеличивая счетчик или размыкая цепь."""
        async with self._lock:
            if self._circuit_state == CircuitState.HALF_OPEN:
                # Если тест в полуразомкнутом состоянии провалился, снова размыкаем
                self._circuit_state = CircuitState.OPEN
                self._last_failure_time = datetime.now()
                logger.error(
                    f"NSPD_CLIENT: Failure on HALF-OPEN. Circuit is OPEN again for {self._cooldown_period}."
                )
            else:
                self._failure_count += 1
                if self._failure_count >= self._failure_threshold:
                    self._circuit_state = CircuitState.OPEN
                    self._last_failure_time = datetime.now()
                    logger.error(
                        f"NSPD_CLIENT: Failure threshold reached. Circuit is now OPEN for {self._cooldown_period}."
                    )

    async def close(self):
        """Корректно закрывает сессию httpx клиента."""
        if not self.client.is_closed:
            await self.client.aclose()
