from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class EnvSettings(BaseSettings):
    """
    Класс для хранения настроек приложения.
    Настройки загружаются из файла .env и переменных окружения.
    """

    BOT_TOKEN: str
    DATABASE_URL: str
    ADMIN_ID: int
    MEGAPLAN_BASE_URL: str
    MEGAPLAN_LOGIN: str
    MEGAPLAN_PASSWORD: str
    MEGAPLAN_PROGRAM_ID: int

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache()
def get_env_settings() -> EnvSettings:
    """
    Функция для получения единственного экземпляра настроек (Singleton).
    При первом вызове создает объект Settings, при последующих возвращает уже созданный.
    """
    return EnvSettings()


# Пример получения экземпляра настроек (он будет создан при первом обращении)
# settings = get_settings()
