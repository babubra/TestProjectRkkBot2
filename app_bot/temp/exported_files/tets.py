import os

from openai import OpenAI


api_key = "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"


# Чтение системной инструкции из файла
def load_system_instruction():
    system_file_path = os.path.join(os.path.dirname(__file__), "system.txt")
    try:
        with open(system_file_path, "r", encoding="utf-8") as file:
            return file.read().strip()
    except FileNotFoundError:
        print(f"Файл {system_file_path} не найден. Используется инструкция по умолчанию.")
        return "Ты полезный помощник."
    except Exception as e:
        print(f"Ошибка при чтении файла: {e}. Используется инструкция по умолчанию.")
        return "Ты полезный помощник."


# Чтение пользовательского сообщения из файла
def load_user_message():
    user_file_path = os.path.join(os.path.dirname(__file__), "user.txt")
    try:
        with open(user_file_path, "r", encoding="utf-8") as file:
            return file.read().strip()
    except FileNotFoundError:
        print(f"Файл {user_file_path} не найден. Используется сообщение по умолчанию.")
        return "Что такое искусственный интеллект?"
    except Exception as e:
        print(f"Ошибка при чтении файла: {e}. Используется сообщение по умолчанию.")
        return "Что такое искусственный интеллект?"


# Создание клиента
client = OpenAI(api_key=api_key, base_url="https://api.perplexity.ai")

# Загрузка системной инструкции и пользовательского сообщения
system_content = load_system_instruction()
user_content = load_user_message()

# Выполнение запроса
response = client.chat.completions.create(
    model="sonar",
    messages=[
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ],
)

# Вывод результата
print(response.choices[0].message.content)
