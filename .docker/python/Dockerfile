# Используем официальный Python 3.13
FROM python:3.13-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем все requirements (и для app_bot и для map_backend)
COPY app_bot/requirements.txt ./app_bot/
COPY map_backend/requirements.txt ./map_backend/

# Устанавливаем зависимости для обоих модулей
RUN pip install --no-cache-dir -r ./app_bot/requirements.txt && \
    pip install --no-cache-dir -r ./map_backend/requirements.txt

# Копируем весь проект
COPY app_bot ./app_bot
COPY map_backend ./map_backend

# Копируем .env если нужно (опционально, мы будем монтировать)
# COPY .env.docker ./.env

# Открываем порт 8000
EXPOSE 8000

# Команда запуска приложения
CMD ["uvicorn", "map_backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
