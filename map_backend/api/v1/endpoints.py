# Файл: map_backend/api/v1/endpoints.py

import json
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

# Импортируем нашу CRUD-функцию
from map_backend.crud.crud_map_request import get_valid_map_request_by_token

# Импортируем наш "поставщик" сессий БД
from map_backend.db.session import get_db_session

# Импортируем Pydantic-схему для валидации ответа
from map_backend.schemas.map_data import MapDealData


# Создаем роутер для нашего эндпоинта.
# prefix - будет добавлен ко всем URL в этом роутере (т.е. итоговый путь будет /api/v1/map-data/{token})
# tags - для красивой группировки в Swagger/OpenAPI документации
router = APIRouter(prefix="/api/v1", tags=["Map Data"])
logger = logging.getLogger(__name__)


@router.get(
    "/map-data/{token}",
    response_model=list[MapDealData],
    summary="Получение данных о сделках для карты",
    description="""
    Возвращает список объектов сделок по валидному токену.
    Если токен не найден или просрочен, возвращает ошибку 404.
    """,
)
async def get_map_data_by_token(token: str, db_session: AsyncSession = Depends(get_db_session)):
    """
    API эндпоинт для получения данных по сделке для отображения на карте.

    - **token**: Уникальный токен, сгенерированный ботом.
    - **db_session**: Асинхронная сессия БД, предоставляемая через Dependency Injection.
    """
    # 1. Вызываем CRUD-функцию для получения записи из БД.
    #    В нее мы передаем токен из URL и сессию, которую нам предоставил FastAPI.
    map_request = await get_valid_map_request_by_token(token=token, db_session=db_session)

    # 2. Если CRUD-функция вернула None (токен не найден или просрочен),
    #    возвращаем стандартный ответ 404 Not Found.
    if not map_request:
        logger.warning(f"Запрос с недействительным или просроченным токеном: {token[:8]}...")
        return JSONResponse(
            status_code=404,
            content={"detail": "Token not found or has expired"},
        )

    # 3. Если все в порядке, парсим JSON-строку из БД в Python-объект (список словарей).
    try:
        deals_data = json.loads(map_request.deals_data_json)
        logger.info(f"Успешно отправлены данные для токена: {token[:8]}...")

        # 4. Возвращаем этот объект. FastAPI автоматически проверит,
        #    соответствует ли он схеме `list[MapDealData]` из `response_model`,
        #    и преобразует его в JSON-ответ.
        return deals_data
    except json.JSONDecodeError as e:
        logger.error(
            f"Критическая ошибка: не удалось распарсить deals_data_json для токена {token[:8]}... "
            f"ID записи: {map_request.id}. Ошибка: {e}"
        )
        # Если данные в БД повреждены, это ошибка на стороне сервера
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error: failed to parse map data"},
        )
