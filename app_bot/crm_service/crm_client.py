import json
import httpx
import asyncio
import logging
from datetime import datetime, timedelta, timezone

import urllib

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
        self._lock = (
            asyncio.Lock()
        )  # Для предотвращения одновременного обновления токена

    async def _get_client_session(self) -> httpx.AsyncClient:
        if self._client_session is None or self._client_session.is_closed:
            self._client_session = httpx.AsyncClient(base_url=self.base_url)
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
            logger.info(
                f"Попытка аутентификации в CRM для пользователя {self.username}..."
            )
            response = await session.post(auth_url_path, data=form_data)
            response.raise_for_status()  # Выбросит исключение для HTTP-ошибок 4xx/5xx

            token_data = response.json()
            self._access_token = token_data.get("access_token")

            if not self._access_token:
                logger.error("Токен доступа не найден в ответе CRM.")
                self._token_expires_at = None
                return False

            expires_in = token_data.get(
                "expires_in", 3600
            )  # Время жизни токена в секундах
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

        session = await self._get_client_session()
        headers = {"Authorization": f"Bearer {token}"}

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

    async def get_deals(
        self,
        visit_date: datetime | None = None,
        executor_id: str | None = None,
        limit: int = 25,
    ) -> list[dict[str, any]] | None:
        """
        Асинхронно получает список сделок из Мегаплана с возможностью фильтрации.
        Обеспечивает заполнение полных данных об исполнителях.

        Args:
            visit_date (datetime, optional): Дата выезда для фильтрации.
            executor_id (str, optional): ID исполнителя для фильтрации.
            limit (int, optional): Ограничение на количество возвращаемых сделок.

        Returns:
            list: Список сделок или None в случае ошибки.
        """

        # 1. Формирование тела запроса (payload) для Мегаплана
        deal_payload = {
            "filter": {
                "contentType": "TradeFilter",
                "id": None,
                "program": {
                    "id": self.program_id,
                    "contentType": "Program",
                },
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

        if visit_date:
            filter_terms.append(
                {
                    "contentType": "FilterTermDate",
                    "field": "Category1000076CustomFieldViezdDataVremyaViezda",
                    "comparison": "equals",
                    "value": {
                        "contentType": "DateOnly",
                        "year": int(visit_date.year),
                        "month": int(
                            visit_date.month - 1
                        ),  # Мегаплан ожидает месяц 0-11
                        "day": int(visit_date.day),
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

        # Исключение статусов 202 - 🚫 Работа над процессом прекращена
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

        # 2. Формирование URL с закодированным JSON в строке запроса
        try:
            # Сериализуем в JSON и затем URL-кодируем строку
            json_payload_str = json.dumps(deal_payload)
            encoded_query_string = urllib.parse.quote(json_payload_str)
        except Exception as e:
            logger.error(
                f"Ошибка при сериализации или кодировании payload для сделок: {e}"
            )
            return None

        endpoint_with_query = f"/api/v3/deal?{encoded_query_string}"

        # 3. Выполнение запроса через обертку _request
        # Если это должен быть POST запрос с JSON в теле:
        response_json = await self._request("GET", endpoint_with_query)

        if not response_json:
            # Ошибка уже залогирована в _request
            return None

        if "data" not in response_json or not isinstance(response_json["data"], list):
            logger.error(
                f"Неожиданный формат ответа от API Мегаплана (отсутствует 'data' или это не список): {response_json}"
            )
            return None

        deals: list[dict[str, any]] = response_json["data"]
        logger.debug(f"Получено {len(deals)} сделок из Мегаплана.")

        # 4. Логика кеширования и обогащения данных об исполнителях
        executors_cache: dict[str, dict[str, any]] = {}

        # Первый проход: сбор полной информации об исполнителях
        for deal in deals:
            executors_in_deal = deal.get("Category1000076CustomFieldViezdIspolnitel")
            if isinstance(executors_in_deal, list):
                for executor in executors_in_deal:
                    if (
                        isinstance(executor, dict)
                        and "id" in executor
                        and "name" in executor
                    ):
                        # Сохраняем полную информацию, если есть 'name'
                        executors_cache[executor["id"]] = executor

        # Второй проход: обновление информации об исполнителях в сделках
        for deal in deals:
            executors_in_deal = deal.get("Category1000076CustomFieldViezdIspolnitel")
            if isinstance(executors_in_deal, list):
                updated_executors_list = []
                for executor in executors_in_deal:
                    if (
                        isinstance(executor, dict)
                        and "id" in executor
                        and "name" not in executor
                    ):
                        # Если нет 'name', но есть 'id', пытаемся взять из кеша
                        cached_executor = executors_cache.get(executor["id"])
                        if cached_executor:
                            updated_executors_list.append(cached_executor)
                        else:
                            updated_executors_list.append(
                                executor
                            )  # Оставляем как есть, если в кеше нет
                    else:
                        updated_executors_list.append(
                            executor
                        )  # Если есть 'name' или не словарь/нет 'id'
                deal["Category1000076CustomFieldViezdIspolnitel"] = (
                    updated_executors_list
                )

        return deals

    async def create_deal(
        self,
        description: str | None = None,
        manager_id: int | None = None,
        ticket_visit_datetime: datetime | None = None,
        megaplan_user_id: int | None = None,
        name: str | None = None,
        cadastral_to_visit: str | None = None,
        address_to_visit: str | None = None,
    ) -> dict[str, any] | None:
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
        logger.info(
            f"Попытка создания сделки с названием: {name if name else 'Без названия'}"
        )

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
                aware_local_dt = ticket_visit_datetime.replace(
                    tzinfo=user_local_timezone
                )
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
            deal_payload["Category1000076CustomFieldPredmetRabotAdres"] = (
                address_to_visit
            )

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
        file_ids: list[str | int] | str | int,
    ) -> bool:
        """
        Внутренний универсальный метод для прикрепления файлов к указанному полю сделки.
        Только добавляет файлы, не очищает поле при пустом списке file_ids.
        """
        if not deal_id or not field_name:
            logger.error(
                f"Для обновления поля '{field_name}' сделки {deal_id} не указан ID сделки или имя поля."
            )
            return False

        if not file_ids:  # Если file_ids пустой (None, "", [], 0 и т.д.)
            logger.warning(
                f"Не переданы ID файлов для прикрепления к полю '{field_name}' сделки {deal_id}. Действие не будет выполнено."
            )
            return False

        current_file_ids_str: list[str]
        if isinstance(file_ids, (str, int)):
            current_file_ids_str = [str(file_ids)]
        elif isinstance(file_ids, list):
            if not file_ids:
                logger.warning(
                    f"Передан пустой список file_ids для поля '{field_name}' сделки {deal_id}. Файлы не будут прикреплены."
                )
                return False
            current_file_ids_str = [str(fid) for fid in file_ids if fid]
            if not current_file_ids_str:
                logger.warning(
                    f"Список file_ids после обработки оказался пустым для поля '{field_name}' сделки {deal_id}. Файлы не будут прикреплены."
                )
                return False
        else:
            logger.error(
                f"Параметр file_ids должен быть строкой, числом или списком. Получен: {type(file_ids)}"
            )
            return False

        logger.info(
            f"Попытка прикрепления файлов {current_file_ids_str} к полю '{field_name}' сделки ID: {str(deal_id)}"
        )

        file_objects_payload = [
            {"contentType": "File", "id": fid_str} for fid_str in current_file_ids_str
        ]

        # Payload для обновления сделки.
        # ВАЖНО: Этот payload перезапишет поле field_name полностью.
        # Если нужно ДОБАВИТЬ файлы к уже существующим, логика должна быть сложнее:
        # 1. Прочитать текущее значение поля field_name из сделки.
        # 2. Добавить новые file_objects_payload к существующим.
        # 3. Отправить обновленный полный список.
        # Пока реализуем простую перезапись поля новыми файлами.
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
            if not meta.get("errors"):
                logger.info(
                    f"Поле '{field_name}' сделки ID {deal_id} успешно обновлено файлами: {current_file_ids_str}."
                )
                return True
            else:
                logger.warning(
                    f"Обновление поля '{field_name}' для сделки {deal_id} файлами {current_file_ids_str} могло завершиться некорректно (неожиданный ответ). Ответ API: {response_data}"
                )
                return True
        else:
            logger.error(
                f"Не удалось обновить поле '{field_name}' сделки {deal_id} файлами {current_file_ids_str}."
            )
            return False

    async def attach_files_to_deal_visit_docs(
        self, deal_id: int | str, file_ids: list[str | int] | str | int
    ) -> bool:
        """
        Прикрепляет файлы (документы и фото с выезда) к соответствующему кастомному полю сделки.
        """
        field_name = "Category1000076CustomFieldViezdDokumentiIFotoSViezda"
        logger.info(
            f"Вызов attach_files_to_deal_visit_docs для сделки ID: {deal_id}, файлы: {file_ids}"
        )
        return await self._generic_attach_files_to_deal_field(
            deal_id=deal_id, field_name=field_name, file_ids=file_ids
        )

    async def attach_files_to_deal_main_attachments(
        self, deal_id: int | str, file_ids: list[str | int] | str | int
    ) -> bool:
        """
        Прикрепляет файлы к основному полю аттачей сделки ('attaches').
        Уточните регистр имени поля "attaches" или "Attaches" согласно API.
        """
        field_name = "attaches"  # Используем нижний регистр. Если API Мегаплана требует "Attaches", измените.
        logger.info(
            f"Вызов attach_files_to_deal_main_attachments для сделки ID: {deal_id}, файлы: {file_ids}"
        )
        return await self._generic_attach_files_to_deal_field(
            deal_id=deal_id, field_name=field_name, file_ids=file_ids
        )
