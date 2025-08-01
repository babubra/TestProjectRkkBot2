# Файл: map_backend/core/config.py

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class EnvSettings(BaseSettings):
    """
    Класс для хранения настроек бэкенд-приложения.
    Настройки загружаются из файла .env в КОРНЕ проекта и переменных окружения.
    """

    DATABASE_URL: str
    FRONTEND_BASE_URL: str = (
        "http://localhost:5173"  # URL для разработки фронтенда по умолчанию
    )

    model_config = SettingsConfigDict(
        # Указываем путь к .env файлу на два уровня выше
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_env_settings() -> EnvSettings:
    """
    Функция для получения единственного экземпляра настроек (Singleton).
    """
    return EnvSettings()
