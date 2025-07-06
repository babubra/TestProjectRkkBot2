import asyncio
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path


# --- НАЧАЛО БЛОКА ДЛЯ КОРРЕКТНЫХ ИМПОРТОВ ---
# Этот блок должен идти ПЕРЕД всеми импортами из вашего проекта.

# 1. Получаем путь к текущему файлу
current_file_path = Path(__file__)

# 2. Находим корневую директорию проекта (поднимаемся на ТРИ уровня)
# crm_client_test.py -> temp -> app_bot -> TestProjectRkkBot2
project_root = current_file_path.parent.parent.parent

# 3. Добавляем корневую директорию в sys.path, чтобы Python "видел" app_bot
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
# --- КОНЕЦ БЛОКА ---


# Теперь, когда путь настроен, эти импорты сработают без ошибок
from app_bot.config.config import get_env_settings
from app_bot.crm_service.crm_client import CRMClient

# Импортируем нашу Pydantic модель, чтобы IDE знала о ее полях
from app_bot.crm_service.schemas import Deal


# Настраиваем логирование
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)


async def main():
    """
    Основная асинхронная функция для тестирования.
    """
    print("--- Запуск теста метода get_deals_for_date_range_MODEL ---")
    print(f"Корень проекта определен как: {project_root}")

    try:
        env_settings = get_env_settings()
        crm_client = CRMClient(
            base_url=env_settings.MEGAPLAN_BASE_URL,
            username=env_settings.MEGAPLAN_LOGIN,
            password=env_settings.MEGAPLAN_PASSWORD,
            program_id=env_settings.MEGAPLAN_PROGRAM_ID,
        )
        print("CRM клиент успешно инициализирован.")
    except Exception as e:
        print(f"❌ Ошибка при инициализации: {e}")
        return

    # Определяем диапазон дат для теста
    start_date = datetime.now() - timedelta(days=30)
    end_date = datetime.now() + timedelta(days=7)

    print(f"\nЗапрашиваем сделки для диапазона: {start_date.date()} - {end_date.date()}")

    try:
        # --- ВЫЗЫВАЕМ НОВЫЙ МЕТОД ---
        # Он вернет список объектов Deal, а не словарей
        deals: list[Deal] | None = await crm_client.get_deals_for_date_range_model(
            start_date=start_date,
            end_date=end_date,
            limit=5,  # Ограничим для наглядности
        )

        # --- ДЕМОНСТРАЦИЯ ДОСТУПА К ДАННЫМ ---
        if deals:
            print(f"\n✅ Успех! Получено сделок: {len(deals)}. Вывод данных:")
            for i, deal in enumerate(deals):
                print(f"\n--- Сделка #{i + 1} ---")

                # Простое обращение к полям через точку
                print(f"  ID: {deal.id}, Номер: {deal.number}")
                print(f"  Название: {deal.name}")

                # Обращение к полю через АЛИАС
                print(f"  Кадастровый номер: {deal.cadastral_number or 'Не указан'}")

                # Обращение к вложенной модели
                print(f"  Статус: {deal.state.name}")

                # Безопасное обращение к опциональному полю
                if deal.price:
                    print(f"  Цена: {deal.price.value} {deal.price.currency}")

                # Обращение к списку вложенных моделей
                if deal.executors:
                    executor_names = ", ".join([e.name for e in deal.executors])
                    print(f"  Исполнители: {executor_names}")

                # Использование вычисляемого свойства @property
                if deal.contractor:
                    print(f"  Клиент: {deal.contractor.full_name}")

        elif deals == []:
            print("\n✅ Успех! Список сделок для данного диапазона пуст.")
        else:
            print("\n❌ Не удалось получить сделки. Метод вернул None.")

    except Exception as e:
        print(f"\n❌ Произошла непредвиденная ошибка: {e}")
        logging.error("Ошибка в тестовом скрипте", exc_info=True)
    finally:
        if crm_client:
            await crm_client.close_session()
        print("\n--- Тест завершен ---")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Выполнение прервано пользователем.")
