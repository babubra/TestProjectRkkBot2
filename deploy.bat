@echo off
chcp 65001 >nul

echo 🚀 Начинаем развертывание проекта RKK Bot...

REM Проверяем наличие Docker
docker --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Docker не установлен. Установите Docker и повторите попытку.
    pause
    exit /b 1
)

REM Проверяем наличие Docker Compose
docker-compose --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Docker Compose не установлен. Установите Docker Compose и повторите попытку.
    pause
    exit /b 1
)

REM Проверяем наличие .env файла
if not exist .env (
    echo ⚠️  Файл .env не найден. Создаем из примера...
    copy .env.example .env >nul
    echo 📝 Отредактируйте файл .env и укажите ваши настройки, затем запустите скрипт снова.
    pause
    exit /b 1
)

REM Создаем директорию для данных
if not exist data mkdir data

REM Останавливаем существующие контейнеры
echo 🛑 Останавливаем существующие контейнеры...
docker-compose down

REM Собираем образы
echo 🔨 Собираем Docker образы...
docker-compose build --no-cache

REM Запускаем сервисы
echo ▶️  Запускаем сервисы...
docker-compose up -d

REM Проверяем статус
echo 📊 Проверяем статус сервисов...
docker-compose ps

echo.
echo ✅ Развертывание завершено!
echo.
echo 🌐 Доступ к сервисам:
echo    Frontend: http://localhost
echo    Backend API: http://localhost:8000
echo    API документация: http://localhost:8000/docs
echo.
echo 📋 Полезные команды:
echo    Просмотр логов: docker-compose logs -f [service_name]
echo    Остановка: docker-compose down
echo    Перезапуск: docker-compose restart
echo.
pause