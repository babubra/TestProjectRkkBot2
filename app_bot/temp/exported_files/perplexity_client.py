import json
import logging
import os
from functools import lru_cache

from openai import AsyncOpenAI, OpenAIError

from app_bot.config.config import get_env_settings


logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_system_prompt() -> str | None:
    """
    Загружает системный промпт из файла и кэширует его.
    Возвращает None в случае ошибки.
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    prompt_path = os.path.join(current_dir, "prompts", "format_ticket_prompt.txt")

    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        logger.error(f"Файл с промптом не найден по пути: {prompt_path}")
        return None
    except Exception as e:
        logger.error(f"Ошибка при чтении файла с промптом: {e}")
        return None


async def format_ticket_with_perplexity(raw_description: str) -> dict[str, str] | None:
    """
    Отправляет сырое описание заявки в Perplexity, получает ответ в виде строки,
    извлекает из нее JSON-объект и возвращает его как словарь.
    """
    env_settings = get_env_settings()
    api_key = env_settings.PERPLEXITY_API_KEY

    if not api_key:
        logger.error("API-ключ для Perplexity не найден в настройках.")
        return None

    client = AsyncOpenAI(api_key=api_key, base_url="https://api.perplexity.ai")

    system_prompt = get_system_prompt()
    if not system_prompt:
        logger.error("Не удалось загрузить системный промпт. Запрос к Perplexity отменен.")
        return None

    full_prompt = f"{system_prompt}\n\nотформатируй в соответствии с инструкцией заявку:\n{raw_description}"

    try:
        logger.info("Отправка запроса в Perplexity AI...")
        response = await client.chat.completions.create(
            model="sonar",
            messages=[
                {"role": "user", "content": full_prompt},
            ],
            timeout=15.0,
        )

        # --- КЛЮЧЕВОЕ ИСПРАВЛЕНИЕ ---
        # Обращаемся к ПЕРВОМУ элементу списка choices
        raw_response_text = response.choices[0].message.content
        logger.info(f"Получен сырой ответ от Perplexity AI: {raw_response_text}")

        # --- Логика извлечения JSON ---
        try:
            start_index = raw_response_text.find("{")
            end_index = raw_response_text.rfind("}")

            if start_index == -1 or end_index == -1:
                logger.error(
                    f"В ответе Perplexity не найдена структура JSON (фигурные скобки): {raw_response_text}"
                )
                return None

            json_string = raw_response_text[start_index : end_index + 1]
            parsed_data = json.loads(json_string)

            if (
                isinstance(parsed_data, dict)
                and "name" in parsed_data
                and "description" in parsed_data
            ):
                logger.info("Ответ успешно извлечен и распарсен в словарь.")
                return parsed_data
            else:
                logger.error(
                    f"Извлеченный JSON не является словарем или не содержит нужных ключей. JSON: {json_string}"
                )
                return None

        except json.JSONDecodeError:
            logger.error(
                f"Не удалось распарсить извлеченный JSON из ответа. Извлеченная строка: {json_string}",
                exc_info=True,
            )
            return None

    except OpenAIError as e:
        logger.error(f"Ошибка API Perplexity: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Непредвиденная ошибка при обращении к Perplexity: {e}", exc_info=True)
        return None


# --- Блок для тестирования ---
if __name__ == "__main__":
    import asyncio
    import sys
    import time

    async def main_interactive_test():
        """
        Интерактивная консольная утилита для тестирования форматирования заявок.
        """
        print("--- Интерактивный тест клиента Perplexity ---")

        # 1. Загружаем промпт один раз при старте
        print("\n1. Загрузка системного промпта...")
        prompt = get_system_prompt()
        if not prompt:
            print("   ...Критическая ошибка! Промпт не загружен. Выход.")
            return
        print(f"   ...Успешно! Промпт из {len(prompt)} символов загружен.")

        print("\n========================================================")
        print("Введите текст заявки. Для многострочного ввода,")
        print(
            "вставьте текст и нажмите Enter, затем Ctrl+D (macOS/Linux) или Ctrl+Z+Enter (Windows)."
        )
        print("Для выхода из программы введите 'exit' или 'quit'.")
        print("========================================================")

        while True:
            try:
                # --- Чтение многострочного ввода от пользователя ---
                print("\n>>> Введите текст заявки:")
                user_lines = []
                while True:
                    try:
                        line = input()
                        user_lines.append(line)
                    except EOFError:
                        # Срабатывает на Ctrl+D или Ctrl+Z
                        break

                raw_description = "\n".join(user_lines).strip()
                # --- Конец чтения ввода ---

                if not raw_description:
                    print("--- Ввод пустой, попробуйте снова. ---")
                    continue

                if raw_description.lower() in ["exit", "quit"]:
                    print("--- Завершение работы. ---")
                    break

                # --- Запуск форматирования ---
                start_time = time.time()
                formatted_result = await format_ticket_with_perplexity(raw_description)
                end_time = time.time()

                duration = end_time - start_time

                print("\n----------------- ОТВЕТ МОДЕЛИ -----------------")
                print(f"(Выполнено за {duration:.2f} сек)")

                if formatted_result:
                    print(formatted_result)
                else:
                    print("!!! Ошибка! Результат не получен (None). Проверьте логи. !!!")

                print("--------------------------------------------------")

            except KeyboardInterrupt:
                # Позволяет выйти по Ctrl+C
                print("\n--- Прервано пользователем. Завершение работы. ---")
                break

    # Запускаем асинхронную тестовую функцию
    if sys.platform == "win32":
        # Для Windows требуется особая политика событий asyncio для корректной работы
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    try:
        asyncio.run(main_interactive_test())
    except KeyboardInterrupt:
        pass  # Игнорируем ошибку от повторного нажатия Ctrl+C
