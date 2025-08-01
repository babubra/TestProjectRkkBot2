# Файл: map_backend/main.py

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Импортируем роутер, который мы создали на предыдущем шаге
from map_backend.api.v1.endpoints import router as api_router_v1

# Импортируем настройки, чтобы получить URL фронтенда
from map_backend.core.config import get_env_settings


# Настройка базового логирования
logging.basicConfig(level=logging.INFO)

# Получаем настройки из .env
settings = get_env_settings()

# Создаем экземпляр приложения FastAPI
app = FastAPI(
    title="Map Backend API",
    description="API для предоставления данных о заявках для отображения на карте.",
    version="1.0.0",
)

# --- Настройка CORS (Cross-Origin Resource Sharing) ---
# Это КРИТИЧЕСКИ ВАЖНО для взаимодействия с фронтендом,
# который будет работать на другом домене/порту.

# Список источников, которым разрешено делать запросы к нашему API.
origins = [
    settings.FRONTEND_BASE_URL,
    # Можно добавить и другие адреса, например, для продакшн-сборки
    # "https://your-production-frontend.com",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # Разрешаем запросы от указанных источников
    allow_credentials=True,  # Разрешаем передачу cookie (хотя в нашем случае не используется)
    allow_methods=["GET"],  # Разрешаем только GET-запросы
    allow_headers=["*"],  # Разрешаем любые заголовки
)

# --- Подключение роутера ---
# Включаем в наше приложение все эндпоинты из api_router_v1
app.include_router(api_router_v1)


# Добавляем простой корневой эндпоинт для проверки, что сервер жив
@app.get("/", tags=["Root"])
async def read_root():
    return {"message": "Map Backend is running!"}
