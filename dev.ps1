# ===========================================
# dev.ps1 - Скрипт запуска локальной разработки
# ===========================================
# Запускает:
#   1. Backend (FastAPI/uvicorn) на порту 8000
#   2. Telegram Bot
#   3. Frontend (Vite dev server) на порту 5173
# ===========================================

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
$EnvFile = Join-Path $ProjectRoot ".env.local"

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "  RKK Bot - Development Environment" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""

# Проверяем наличие .env.local
if (-not (Test-Path $EnvFile)) {
    Write-Host "[ERROR] Файл .env.local не найден!" -ForegroundColor Red
    Write-Host "Создайте его на основе .env.example" -ForegroundColor Yellow
    exit 1
}

# Функция для загрузки переменных окружения из .env файла
function Load-EnvFile {
    param([string]$Path)
    $envVars = @{}
    Get-Content $Path | ForEach-Object {
        if ($_ -match '^([^#][^=]+)=(.*)$') {
            $envVars[$matches[1].Trim()] = $matches[2].Trim()
        }
    }
    return $envVars
}

# Загружаем переменные окружения
$envVars = Load-EnvFile -Path $EnvFile
$envString = ($envVars.GetEnumerator() | ForEach-Object { "`$env:$($_.Key)='$($_.Value)'" }) -join "; "

Write-Host "[1/3] Запуск Backend (FastAPI)..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", @"
    Set-Location '$ProjectRoot'
    `$env:PYTHONPATH = '$ProjectRoot'
    $envString
    Write-Host '=== BACKEND (port 8000) ===' -ForegroundColor Cyan
    .\.venv\Scripts\Activate.ps1
    uvicorn map_backend.main:app --reload --port 8000 --host 0.0.0.0
"@

Start-Sleep -Seconds 2

Write-Host "[2/3] Запуск Telegram Bot..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", @"
    Set-Location '$ProjectRoot'
    `$env:PYTHONPATH = '$ProjectRoot'
    $envString
    Write-Host '=== TELEGRAM BOT ===' -ForegroundColor Cyan
    .\.venv\Scripts\Activate.ps1
    python -m app_bot.bot
"@

Start-Sleep -Seconds 2

Write-Host "[3/3] Запуск Frontend (Vite)..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", @"
    Set-Location '$ProjectRoot\map_frontend'
    Write-Host '=== FRONTEND (port 5173) ===' -ForegroundColor Cyan
    npm run dev
"@

Write-Host ""
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "  Все сервисы запущены!" -ForegroundColor Green
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Backend:  http://localhost:8000" -ForegroundColor Yellow
Write-Host "  Frontend: http://localhost:5173" -ForegroundColor Yellow
Write-Host "  Bot:      Работает в Telegram" -ForegroundColor Yellow
Write-Host ""
Write-Host "Для остановки закройте все открытые терминалы." -ForegroundColor Gray
