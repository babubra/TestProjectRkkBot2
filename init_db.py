#!/usr/bin/env python3
"""
Скрипт для инициализации базы данных.
Создает все необходимые таблицы.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Добавляем корневую директорию проекта в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent))

from app_bot.database.engine import DatabaseManager
from app_bot.config.config import get_env_settings


async def init_database():
    """Инициализация базы данных."""
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    try:
        # Получаем настройки
        settings = get_env_settings()
        
        # Создаем менеджер базы данных
        db_manager = DatabaseManager(url=settings.DATABASE_URL)
        
        # Создаем все таблицы
        await db_manager.create_all()
        
        logger.info("База данных успешно инициализирована!")
        
    except Exception as e:
        logger.error(f"Ошибка при инициализации базы данных: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(init_database())