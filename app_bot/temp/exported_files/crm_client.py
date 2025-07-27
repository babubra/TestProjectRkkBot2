import asyncio
import json
import logging
import urllib
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from pydantic import ValidationError

from app_bot.config.config import get_env_settings

from .schemas import Deal


logger = logging.getLogger(__name__)


class CRMClient:
    """
    Класс для работы с API Мегаплана.
    Необходимо единожды создать его экземпляр при запуске приложения и передавать в хендлеры и иные методы,
    желательно через Middleware
    """

    def __init__(self, base_url: str, username: str, password: str, program_id: int):
        self.base_url = base_url
        self.username = username
        self.password = password
        self.program_id = program_id

        self._access_token: str | None = None
        self._token_expires_at: datetime | None = None
        self._client_session: httpx.AsyncClient | None = None
        self._lock = asyncio.Lock()  # Для предотвращения одновременного обновления токена

    async def _get_client_session(self) -> httpx.AsyncClient:
        if self._client_session is None or self._client_session.is_closed:
            timeout_config = httpx.Timeout(30.0, connect=5.0)
            self._client_session = httpx.AsyncClient(
                base_url=self.base_url, timeout=timeout_config
            )
        return self._client_session

    async def _login(self) -> bool:
        """
        Выполняет вход в CRM, получает и сохраняет токен доступа.
        Это внутренний метод.
        """
        session = await self._get_client_session()
        # URL для аутентификации относительно base_url
        auth_url_path = "/api/v3/auth/access_token"

        form_data = {
            "username": self.username,
            "password": self.password,
            "grant_type": "password",
        }

        try:
            logger.info(f"Попытка аутентификации в CRM для пользователя {self.username}...")
            response = await session.post(auth_url_path, data=form_data)
            response.raise_for_status()  # Выбросит исключение для HTTP-ошибок 4xx/5xx

            token_data = response.json()
            self._access_token = token_data.get("access_token")

            if not self._access_token:
                logger.error("Токен доступа не найден в ответе CRM.")
                self._token_expires_at = None
                return False

            expires_in = token_data.get("expires_in", 3600)  # Время жизни токена в секундах
            # Устанавливаем время истечения с небольшим запасом (например, 60 секунд)
            # Используем timezone.utc для корректной работы с временем
            buffer_seconds = 60
            self._token_expires_at = datetime.now(timezone.utc) + timedelta(
                seconds=expires_in - buffer_seconds
            )
            logger.info(
                f"Успешная аутентификация. Токен действителен до: {self._token_expires_at}"
            )
            return True

        except httpx.HTTPStatusError as e:
            logger.error(
                f"Ошибка HTTP при получении токена: {e.response.status_code} - {e.response.text}"
            )
            self._access_token = None
            self._token_expires_at = None
            return False
        except httpx.RequestError as e:
            logger.error(f"Ошибка запроса при получении токена: {e}")
            self._access_token = None
            self._token_expires_at = None
            return False
        except Exception as e:
            logger.error(f"Непредвиденная ошибка при аутентификации: {e}")
            self._access_token = None
            self._token_expires_at = None
            return False

    def _is_token_valid(self) -> bool:
        """Проверяет, действителен ли текущий токен."""
        return bool(
            self._access_token
            and self._token_expires_at
            and self._token_expires_at > datetime.now(timezone.utc)
        )

    async def get_access_token(self) -> str | None:
        """
        Возвращает действительный токен доступа.
        Если токен недействителен или отсутствует, пытается его обновить.
        """
        async with self._lock:  # Блокировка для предотвращения гонки
            if not self._is_token_valid():
                logger.info("Токен недействителен или истек. Попытка обновления...")
                if not await self._login():
                    logger.error("Не удалось обновить токен.")
                    return None
            return self._access_token

    async def close_session(self):
        """Закрывает сессию httpx.AsyncClient."""
        if self._client_session and not self._client_session.is_closed:
            await self._client_session.aclose()
            self._client_session = None
            logger.info("Сессия CRMClient закрыта.")

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: dict | None = None,
        json_data: dict | None = None,
        files_payload: dict | None = None,
    ) -> dict | None:
        """Обертка для выполнения запросов к API CRM."""
        token = await self.get_access_token()
        if not token:
            logger.error("Не удалось получить токен доступа для выполнения запроса.")
            return None

        # Получаем настройки, чтобы узнать наш часовой пояс
        settings = get_env_settings()
        timezone_offset_seconds = -(settings.APP_TIMEZONE_OFFSET * 3600)

        # Формируем заголовки, добавляя ключевой заголовок x-time-zone
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Time-Zone": str(timezone_offset_seconds),
        }

        session = await self._get_client_session()

        try:
            logger.debug(
                f"Выполнение запроса: {method} {endpoint}, params={params}, json={json_data}"
            )
            response = await session.request(
                method,
                endpoint,
                headers=headers,
                params=params,
                json=json_data,
                files=files_payload,
            )

            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"Ошибка HTTP при запросе к {endpoint}: {e.response.status_code} - {e.response.text}"
            )
            if e.response.status_code == 401:
                logger.warning(
                    "Получен 401 Unauthorized. Возможно, токен отозван. Попытка сбросить токен."
                )
                async with self._lock:
                    self._access_token = None  # Сброс токена для принудительного обновления при следующем запросе
            return None
        except httpx.RequestError as e:
            logger.error(f"Ошибка запроса к {endpoint}: {e}")
            return None
        except Exception as e:
            logger.error(f"Непредвиденная ошибка при запросе к {endpoint}: {e}")
            return None

    def _recursively_build_cache(self, data_structure: Any, cache: dict[str, dict]) -> None:
        """
        Рекурсивно обходит структуру данных (dict, list) и находит все
        ПОЛНЫЕ объекты Employee для наполнения кэша.
        """
        if isinstance(data_structure, dict):
            # Если текущий узел - это полный объект сотрудника, кэшируем его
            if (
                data_structure.get("contentType") == "Employee"
                and "id" in data_structure
                and "name" in data_structure
            ):
                cache[data_structure["id"]] = data_structure

            # Продолжаем обход вглубь словаря
            for value in data_structure.values():
                self._recursively_build_cache(value, cache)

        elif isinstance(data_structure, list):
            # Продолжаем обход для каждого элемента списка
            for item in data_structure:
                self._recursively_build_cache(item, cache)

    def _recursively_enrich_employees(
        self, data_structure: Any, cache: dict[str, dict]
    ) -> None:
        """
        Рекурсивно обходит структуру и заменяет НЕПОЛНЫЕ объекты Employee
        данными из кэша.
        """
        if isinstance(data_structure, dict):
            # Если текущий узел - это неполный объект сотрудника, который есть в кэше
            if (
                data_structure.get("contentType") == "Employee"
                and "id" in data_structure
                and "name" not in data_structure  # Ключевое условие - 'name' отсутствует
                and data_structure["id"] in cache
            ):
                # Обогащаем/заменяем неполные данные полными из кэша
                full_employee_data = cache[data_structure["id"]]
                data_structure.update(full_employee_data)
                # После обогащения нет смысла идти вглубь этого объекта
                return

            # Если это не объект для обогащения, продолжаем обход вглубь
            for value in data_structure.values():
                self._recursively_enrich_employees(value, cache)

        elif isinstance(data_structure, list):
            # Обходим каждый элемент списка
            for item in data_structure:
                self._recursively_enrich_employees(item, cache)

    async def get_deals_for_date_range(
        self,
        start_date: datetime,
        end_date: datetime,
        executor_id: str | None = None,
        limit: int = 200,  # Лимит по умолчанию выше, т.к. запрашиваем диапазон
    ) -> list[dict[str, any]] | None:
        """
        Асинхронно получает список сделок из Мегаплана за ДИАПАЗОН ДАТ (включительно).
        """
        if start_date > end_date:
            logger.error("Начальная дата не может быть позже конечной.")
            raise ValueError("Начальная дата не может быть позже конечной.")

        # 1. Формирование тела запроса (payload) для Мегаплана
        deal_payload = {
            "filter": {
                "contentType": "TradeFilter",
                "id": None,
                "program": {"id": self.program_id, "contentType": "Program"},
            },
            "limit": limit,
            "onlyRequestedFields": True,
            "sortBy": [
                {
                    "contentType": "SortField",
                    "fieldName": "Category1000076CustomFieldViezdIspolnitel",
                    "desc": False,
                }
            ],
        }

        filter_terms = []

        filter_terms.append(
            {
                "contentType": "FilterTermDate",
                "field": "Category1000076CustomFieldViezdDataVremyaViezda",
                "comparison": "equals",  # Для интервала используется "equals"
                "value": {
                    "contentType": "IntervalDates",
                    "from": {
                        "contentType": "DateOnly",
                        "year": start_date.year,
                        "month": start_date.month - 1,  # Мегаплан ожидает месяц 0-11
                        "day": start_date.day,
                    },
                    "to": {
                        "contentType": "DateOnly",
                        "year": end_date.year,
                        "month": end_date.month - 1,
                        "day": end_date.day,
                    },
                },
            }
        )

        if executor_id:
            filter_terms.append(
                {
                    "contentType": "FilterTermRef",
                    "field": "Category1000076CustomFieldViezdIspolnitel",
                    "comparison": "equals",
                    "value": [{"id": executor_id, "contentType": "Employee"}],
                }
            )

        excluded_status_ids = [202]
        filter_terms.append(
            {
                "contentType": "FilterTermRef",
                "field": "state",
                "comparison": "not_equals",
                "value": [
                    {"id": status_id, "contentType": "ProgramState"}
                    for status_id in excluded_status_ids
                ],
            }
        )

        if filter_terms:
            deal_payload["filter"]["config"] = {
                "contentType": "FilterConfig",
                "termGroup": {
                    "contentType": "FilterTermGroup",
                    "join": "and",
                    "terms": filter_terms,
                },
            }

        fields_to_request = [
            "editableFields",
            "possibleActions",
            "Category1000076CustomFieldPredmetRabotAdres",
            "Category1000076CustomFieldPredmetRabotKadastroviyNomer",
            "Category1000076CustomFieldViezdDataVremyaViezda",
            "Category1000076CustomFieldViezdIspolnitel",
            "Category1000076CustomFieldViezdFayliDlyaViezda",
            "Category1000076CustomFieldSluzhebniyTelegramuserid",
            "Category1000076CustomFieldViezdRezultatViezda",
            "Category1000076CustomFieldServiceData",
            {
                "contractor": [
                    "avatar",
                    "canSeeFull",
                    "firstName",
                    "lastName",
                    "middleName",
                    "name",
                    "type",
                    "contactInfo",
                ]
            },
            "description",
            "isFavorite",
            "name",
            "nearTodo",
            "number",
            "price",
            "program",
            "state",
            "tags",
            "tagsCount",
            "unreadCommentsCount",
        ]
        deal_payload["fields"] = fields_to_request

        try:
            json_payload_str = json.dumps(deal_payload)
            encoded_query_string = urllib.parse.quote(json_payload_str)
        except Exception as e:
            logger.error(f"Ошибка при сериализации или кодировании payload для сделок: {e}")
            return None

        endpoint_with_query = f"/api/v3/deal?{encoded_query_string}"
        response_json = await self._request("GET", endpoint_with_query)

        if (
            not response_json
            or "data" not in response_json
            or not isinstance(response_json["data"], list)
        ):
            logger.error(f"Неожиданный формат ответа от API Мегаплана: {response_json}")
            return None

        deals: list[dict[str, any]] = response_json["data"]
        logger.info(
            f"Получено {len(deals)} сделок из Мегаплана за диапазон {start_date} - {end_date}."
        )

        # --- Этап 1: Рекурсивно строим кэш всех полных данных о сотрудниках ---
        executors_cache: dict[str, dict[str, any]] = {}
        for deal in deals:
            self._recursively_build_cache(deal, executors_cache)

        logger.debug(
            f"Кэш исполнителей собран. Найдено {len(executors_cache)} уникальных сотрудников."
        )

        # --- Этап 2: Рекурсивно обогащаем все сделки данными из кэша ---
        for deal in deals:
            self._recursively_enrich_employees(deal, executors_cache)

        logger.debug("Обогащение данных по сотрудникам завершено.")

        return deals

    async def get_deal_by_id(self, deal_id: int | str) -> dict[str, Any] | None:
        """
        Асинхронно получает одну сделку по ее ID из Мегаплана.
        Возвращает необработанный словарь данных сделки.
        """
        logger.info(f"Запрос сделки по ID: {deal_id}")
        endpoint = f"/api/v3/deal/{deal_id}"

        response_data = await self._request(method="GET", endpoint=endpoint)

        if not response_data:
            return None

        if "data" in response_data and isinstance(response_data["data"], dict):
            deal_data = response_data["data"]
            # Выполняем обогащение данных по сотрудникам для консистентности
            executors_cache: dict[str, dict[str, any]] = {}
            self._recursively_build_cache(deal_data, executors_cache)
            self._recursively_enrich_employees(deal_data, executors_cache)
            logger.info(f"Сделка ID {deal_id} получена и обогащена.")
            return deal_data
        else:
            logger.error(f"Неожиданный формат ответа для сделки ID {deal_id}: {response_data}")
            return None

    async def get_deal_by_id_model(self, deal_id: int | str) -> Deal | None:
        """
        Асинхронно получает одну сделку по ID и возвращает ее
        в виде типизированного объекта Deal.
        """
        raw_deal = await self.get_deal_by_id(deal_id=deal_id)

        if raw_deal is None:
            return None

        try:
            deal_model = Deal.model_validate(raw_deal)
            logger.info(f"Успешно спарсена сделка ID {deal_id} в Pydantic модель.")
            return deal_model
        except ValidationError as e:
            logger.error(f"Ошибка валидации Pydantic для сделки ID {deal_id}: {e}")
            return None

    async def create_deal(
        self,
        description: str | None = None,
        manager_id: int | None = None,
        ticket_visit_datetime: datetime | None = None,
        megaplan_user_id: int | None = None,
        name: str | None = None,
        cadastral_to_visit: str | None = None,
        address_to_visit: str | None = None,
    ) -> dict[str, Any] | None:
        """
        Асинхронно создает новую сделку в Мегаплане.

        Args:
            description (str): Описание сделки.
            manager_id (int, optional): ID менеджера.
            ticket_visit_datetime (datetime.datetime, optional): Дата и время выезда.
            megaplan_user_id (str, optional): ID пользователя в Мегаплан (исполнитель).
            name (str, optional): Название сделки.
            cadastral_to_visit (str, optional): Кадастровый номер для выезда.
            address_to_visit (str, optional): Адрес для выезда.

        Returns:
            Dict[str, Any] | None: Данные созданной сделки или None в случае ошибки.
        """
        logger.info(f"Попытка создания сделки с названием: {name if name else 'Без названия'}")

        deal_payload: dict[str, any] = {
            "contentType": "Deal",
            "program": {"contentType": "Program", "id": self.program_id},
        }

        if description is not None:
            deal_payload["description"] = description

        if name is not None:
            deal_payload["name"] = name

        if manager_id is not None:
            deal_payload["manager"] = {"contentType": "Employee", "id": manager_id}

        if ticket_visit_datetime is not None:
            user_local_timezone = timezone(timedelta(hours=2))
            if (
                ticket_visit_datetime.tzinfo is None
                or ticket_visit_datetime.tzinfo.utcoffset(ticket_visit_datetime) is None
            ):
                # Наивный datetime, делаем его "осведомленным" для UTC+2
                aware_local_dt = ticket_visit_datetime.replace(tzinfo=user_local_timezone)
            else:
                # Уже "осведомленный", приведем его к вашему UTC+2 для единообразия перед конвертацией в UTC
                aware_local_dt = ticket_visit_datetime.astimezone(user_local_timezone)
            # Шаг 2: Конвертируем в UTC
            utc_dt = aware_local_dt.astimezone(timezone.utc)
            # Шаг 3: Форматируем в ISO 8601 (теперь строка будет содержать +00:00 или Z)
            iso_value_for_api = utc_dt.isoformat()
            deal_payload["Category1000076CustomFieldViezdDataVremyaViezda"] = {
                "contentType": "DateTime",
                "value": iso_value_for_api,
            }

        if megaplan_user_id is not None:
            # Поле для исполнителя часто является списком, даже если исполнитель один
            deal_payload["Category1000076CustomFieldSluzhebniyTelegramuserid"] = [
                {"contentType": "Employee", "id": str(megaplan_user_id)}
            ]

        if cadastral_to_visit is not None:
            deal_payload["Category1000076CustomFieldPredmetRabotKadastroviyNomer"] = (
                cadastral_to_visit
            )

        if address_to_visit is not None:
            deal_payload["Category1000076CustomFieldPredmetRabotAdres"] = address_to_visit

        # Выполняем POST-запрос для создания сделки
        response_data = await self._request(
            method="POST",
            endpoint="/api/v3/deal",  # Эндпоинт для создания сделки
            json_data=deal_payload,
        )

        if not response_data:
            logger.error("Не удалось создать сделку: _request вернул None.")
            return None

        if "data" in response_data and isinstance(response_data["data"], dict):
            created_deal = response_data["data"]
            deal_id = created_deal.get("id")
            deal_number = created_deal.get("number")
            logger.info(f"Сделка успешно создана. ID: {deal_id}, Номер: {deal_number}")
            return created_deal
        else:
            logger.error(
                f"Ошибка при создании сделки: неожиданный формат ответа от API. Ответ: {response_data}"
            )
            return None

    async def update_deal(
        self, deal_id: int | str, update_data: dict[str, Any]
    ) -> dict[str, Any] | None:
        """
        Асинхронно обновляет существующую сделку в Мегаплане.

        Args:
            deal_id: ID сделки, которую нужно обновить.
            update_data: Словарь с полями для обновления.
                         Например: {'name': 'Новое название', 'description': 'Новое описание'}

        Returns:
            Данные обновленной сделки от CRM или None в случае ошибки.
        """
        if not update_data:
            logger.warning(
                f"Попытка обновить сделку {deal_id} без данных для обновления. Операция пропущена."
            )
            return None

        logger.info(f"Попытка обновления сделки ID {deal_id} данными: {update_data}")

        # Эндпоинт для обновления конкретной сделки
        endpoint = f"/api/v3/deal/{deal_id}"

        # Согласно документации, тело запроса должно содержать ID и contentType
        payload = {"id": str(deal_id), "contentType": "Deal"}
        # Добавляем в payload поля, которые пришли для обновления
        payload.update(update_data)

        # Выполняем POST-запрос для обновления
        response_data = await self._request(
            method="POST",
            endpoint=endpoint,
            json_data=payload,
        )

        if not response_data:
            logger.error(f"Не удалось обновить сделку {deal_id}: _request вернул None.")
            return None

        # Проверяем, что ответ содержит данные
        if "data" in response_data and isinstance(response_data["data"], dict):
            updated_deal = response_data["data"]
            logger.info(f"Сделка ID {deal_id} успешно обновлена.")
            return updated_deal
        else:
            logger.error(
                f"Ошибка при обновлении сделки {deal_id}: неожиданный формат ответа от API. Ответ: {response_data}"
            )
            return None

    async def upload_file_from_bytes(
        self,
        file_content: bytes,
        file_name: str,
        file_type: str | None = None,
    ) -> dict[str, any] | None:
        """
        Асинхронно загружает файл (представленный как байты) в Мегаплан,
        используя обновленный метод _request.

        Args:
            file_content (bytes): Содержимое файла в виде байтов.
            file_name (str): Имя файла, которое будет сохранено в Мегаплане.
            file_type (str, optional): MIME-тип файла.

        Returns:
            Dict[str, Any] | None: Информация о загруженном файле от API Мегаплана или None в случае ошибки.
        """
        logger.info(
            f"Подготовка к загрузке файла '{file_name}' (тип: {file_type if file_type else 'не указан'}). Размер: {len(file_content)} байт."
        )

        # Эндпоинт для загрузки файлов
        upload_endpoint = "/api/file"

        # Подготовка данных для multipart/form-data
        # Ключ "files[]" согласно документации Мегаплана
        files_data_for_request = {"files[]": (file_name, file_content, file_type)}

        response_json = await self._request(
            method="POST",
            endpoint=upload_endpoint,
            files_payload=files_data_for_request,
        )

        if not response_json:
            # Ошибка уже залогирована в _request
            logger.error(
                f"Загрузка файла '{file_name}' не удалась (ответ от _request is None)."
            )
            return None

        # Анализ ответа согласно документации ("В ответ получаем id созданного файла")
        # и вашего предыдущего кода (ожидание списка в "data")
        if (
            "data" in response_json
            and isinstance(response_json["data"], list)
            and len(response_json["data"]) > 0
        ):
            uploaded_file_info = response_json["data"][0]
            file_id = uploaded_file_info.get("id", "неизвестен")
            logger.info(
                f"Файл '{file_name}' успешно загружен через _request. ID файла: {file_id}"
            )
            return uploaded_file_info
        elif (
            "id" in response_json and response_json.get("contentType") == "File"
        ):  # Если API вернуло одиночный объект файла напрямую
            logger.info(
                f"Файл '{file_name}' успешно загружен через _request. ID файла: {response_json.get('id')}"
            )
            return response_json  # Возвращаем весь объект файла
        else:
            logger.error(
                f"Ошибка при загрузке файла '{file_name}': неожиданный формат JSON-ответа от API. Ответ: {response_json}"
            )
            return None

    async def _generic_attach_files_to_deal_field(
        self,
        deal_id: int | str,
        field_name: str,
        file_ids: list[str | int],
    ) -> bool:
        """
        Внутренний универсальный метод для ПЕРЕЗАПИСИ поля сделки списком файлов.
        Если передан пустой список file_ids, поле будет очищено.
        """
        if not deal_id or not field_name:
            logger.error(
                f"Для обновления поля '{field_name}' сделки не указан ID сделки или имя поля."
            )
            return False

        logger.info(
            f"Попытка перезаписи поля '{field_name}' сделки ID {str(deal_id)} файлами: {file_ids}"
        )

        file_objects_payload = [
            {"contentType": "File", "id": str(fid)} for fid in file_ids if fid
        ]

        # Payload для обновления сделки. API Мегаплана перезаписывает поле полностью.
        # Логика "добавления" реализуется в вызывающих методах.
        update_payload = {
            "id": str(deal_id),
            "contentType": "Deal",
            field_name: file_objects_payload,
        }

        endpoint = f"/api/v3/deal/{str(deal_id)}"
        http_method_for_update = "POST"

        response_data = await self._request(
            method=http_method_for_update, endpoint=endpoint, json_data=update_payload
        )

        if response_data:
            meta = response_data.get("meta")
            if meta and not meta.get("errors"):  # Добавлена проверка на существование meta
                logger.info(
                    f"Поле '{field_name}' сделки ID {deal_id} успешно обновлено файлами: {file_ids}."
                )
                return True
            else:
                logger.warning(
                    f"Обновление поля '{field_name}' для сделки {deal_id} файлами {file_ids} могло завершиться с ошибкой. Ответ API: {response_data}"
                )
                # Считаем успешным, если нет явной ошибки, но логируем
                return True
        else:
            logger.error(
                f"Не удалось обновить поле '{field_name}' сделки {deal_id} файлами {file_ids}."
            )
            return False

    async def attach_files_to_deal_visit_docs(
        self, deal_id: int | str, file_ids: list[str | int] | str | int
    ) -> bool:
        """
        ДОБАВЛЯЕТ файлы (документы и фото с выезда) к соответствующему полю сделки.
        Существующие файлы не удаляются.
        """
        field_name = "Category1000076CustomFieldViezdDokumentiIFotoSViezda"
        logger.info(
            f"Вызов ДОБАВЛЕНИЯ файлов в поле '{field_name}' для сделки ID: {deal_id}, файлы: {file_ids}"
        )

        # 1. Нормализуем входящие ID в список строк
        if isinstance(file_ids, (str, int)):
            new_file_ids_str = [str(file_ids)]
        elif isinstance(file_ids, list):
            new_file_ids_str = [str(fid) for fid in file_ids if fid]
        else:
            logger.error(f"Некорректный тип для file_ids: {type(file_ids)}")
            return False

        if not new_file_ids_str:
            logger.warning("Список новых файлов для добавления пуст. Операция не требуется.")
            return True  # Считаем операцию успешной, т.к. добавлять нечего

        # 2. Получаем текущее состояние сделки
        deal = await self.get_deal_by_id_model(deal_id)
        if not deal:
            logger.error(f"Не удалось получить сделку {deal_id} для добавления файлов.")
            return False

        # 3. Собираем ID существующих файлов
        existing_file_ids = [file.id for file in deal.files_from_visit]

        # 4. Объединяем списки и удаляем дубликаты
        combined_ids = list(set(existing_file_ids + new_file_ids_str))

        # 5. Вызываем низкоуровневый метод с полным списком
        return await self._generic_attach_files_to_deal_field(
            deal_id=deal_id, field_name=field_name, file_ids=combined_ids
        )

    async def attach_files_to_deal_main_attachments(
        self, deal_id: int | str, file_ids: list[str | int] | str | int
    ) -> bool:
        """
        ДОБАВЛЯЕТ файлы к основному полю аттачей сделки ('attaches').
        Существующие файлы не удаляются.
        """
        field_name = "attaches"
        logger.info(
            f"Вызов ДОБАВЛЕНИЯ файлов в поле '{field_name}' для сделки ID: {deal_id}, файлы: {file_ids}"
        )
        # 1. Нормализуем входящие ID в список строк
        if isinstance(file_ids, (str, int)):
            new_file_ids_str = [str(file_ids)]
        elif isinstance(file_ids, list):
            new_file_ids_str = [str(fid) for fid in file_ids if fid]
        else:
            logger.error(f"Некорректный тип для file_ids: {type(file_ids)}")
            return False

        if not new_file_ids_str:
            logger.warning("Список новых файлов для добавления пуст. Операция не требуется.")
            return True

        # 2. Получаем текущее состояние сделки
        deal = await self.get_deal_by_id_model(deal_id)
        if not deal:
            logger.error(f"Не удалось получить сделку {deal_id} для добавления файлов.")
            return False

        # 3. Собираем ID существующих файлов из поля 'attaches'
        existing_file_ids = [file.id for file in deal.attaches]

        # 4. Объединяем списки и удаляем дубликаты
        combined_ids = list(set(existing_file_ids + new_file_ids_str))

        # 5. Вызываем низкоуровневый метод с полным списком
        return await self._generic_attach_files_to_deal_field(
            deal_id=deal_id, field_name=field_name, file_ids=combined_ids
        )

    async def get_deals_for_date_range_model(
        self,
        start_date: datetime,
        end_date: datetime,
        executor_id: str | None = None,
        limit: int = 1000,
    ) -> list[Deal] | None:
        """
        Асинхронно получает список сделок за диапазон дат, обогащает данные и
        возвращает список типизированных объектов Deal.
        """
        raw_deals = await self.get_deals_for_date_range(
            start_date=start_date, end_date=end_date, executor_id=executor_id, limit=limit
        )

        if raw_deals is None:
            return None

        try:
            deals = [Deal.model_validate(deal_data) for deal_data in raw_deals]
            logger.info(
                f"Успешно спарсено {len(deals)} сделок в Pydantic модели "
                f"за диапазон {start_date} - {end_date}."
            )
            return deals
        except ValidationError as e:
            logger.error(f"Ошибка валидации Pydantic при получении сделок для диапазона: {e}")
            return None
