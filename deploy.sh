#!/bin/bash

# Скрипт для развертывания проекта RKK Bot

echo "🚀 Начинаем развертывание проекта RKK Bot..."

# Проверяем наличие Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker не установлен. Установите Docker и повторите попытку."
    exit 1
fi

# Проверяем наличие Docker Compose
if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose не установлен. Установите Docker Compose и повторите попытку."
    exit 1
fi

# Проверяем наличие .env файла
if [ ! -f .env ]; then
    echo "⚠️  Файл .env не найден. Создаем из примера..."
    cp .env.example .env
    echo "📝 Отредактируйте файл .env и укажите ваши настройки, затем запустит�� скрипт снова."
    exit 1
fi

# Создаем директорию для данных
mkdir -p data

# Останавливаем существующие контейнеры
echo "🛑 Останавливаем существующие контейнеры..."
docker-compose down

# Собираем образы
echo "🔨 Собираем Docker образы..."
docker-compose build --no-cache

# Запускаем сервисы
echo "▶️  Запускаем сервисы..."
docker-compose up -d

# Проверяем статус
echo "📊 Проверяем статус сервисов..."
docker-compose ps

echo ""
echo "✅ Развертывание завершено!"
echo ""
echo "🌐 Доступ к сервисам:"
echo "   Frontend: http://localhost"
echo "   Backend API: http://localhost:8000"
echo "   API документация: http://localhost:8000/docs"
echo ""
echo "📋 Полезные команды:"
echo "   Просмотр логов: docker-compose logs -f [service_name]"
echo "   Остановка: docker-compose down"
echo "   Перезапуск: docker-compose restart"
echo ""