# Dockerfile для бэкенда
FROM python:3.11-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем файл зависимостей
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код приложения
COPY . .

# Создаем директорию для базы данных
RUN mkdir -p /app/data

# Устанавливаем переменную окружения для Python
ENV PYTHONPATH=/app

# Открываем порт
EXPOSE 8000

# Команда запуска
CMD ["uvicorn", "map_backend.main:app", "--host", "0.0.0.0", "--port", "8000"]