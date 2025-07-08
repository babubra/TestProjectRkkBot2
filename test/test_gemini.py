import os

import google.generativeai as genai


# --- 1. НАСТРОЙКА API-КЛЮЧА ---
# ВАЖНО: Ключ должен быть в переменной окружения, а не в коде!
# Перед запуском установите его в терминале:
# Windows:       set GEMINI_API_KEY="ВАШ_КЛЮЧ"
# macOS / Linux: export GEMINI_API_KEY="ВАШ_КЛЮЧ"

api_key = "AIzaSyCze7cOvq05VTQFGZbnX3FPNnhHDSiMPBc"

try:
    genai.configure(api_key=api_key)
except Exception as e:
    print(f"Ошибка конфигурации API: {e}")
    exit()

# --- 2. ЧТЕНИЕ ЗАПРОСА ИЗ ФАЙЛА ---
# Путь к файлу с запросом, как вы и просили.
prompt_filename = "gemini_instruction.txt"
user_file_path = os.path.join(os.path.dirname(__file__), prompt_filename)

try:
    with open(user_file_path, "r", encoding="utf-8") as file:
        user_prompt = file.read().strip()
except FileNotFoundError:
    print(f"ОШИБКА: Файл '{prompt_filename}' не найден.")
    print(
        f"Создайте этот файл в той же папке, где находится скрипт '{os.path.basename(__file__)}'."
    )
    exit()
except Exception as e:
    print(f"Ошибка при чтении файла: {e}")
    exit()


# --- 3. ЗАПРОС К МОДЕЛИ И ВЫВОД ОТВЕТА ---

# Используем правильное имя модели
model_name = "gemini-2.5-flash-lite-preview-06-17"
model = genai.GenerativeModel(model_name=model_name)

print(f"--- Модель: {model_name} ---")
print(f"--- Запрос из файла '{prompt_filename}' ---")
print("------------------------------------------")
print("...Отправка запроса, ожидание ответа...")

try:
    # Отправляем запрос и получаем ответ
    response = model.generate_content(user_prompt)

    # Выводим ответ
    print("\n--- Ответ от Gemini ---")
    print(response.text)

except Exception as e:
    print(f"\n--- Произошла ошибка во время запроса к API ---")
    print(e)
