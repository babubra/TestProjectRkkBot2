# ===========================================
# deploy-bot.ps1 - Обновление Telegram-бота (rkk-bot) из ветки main
# ===========================================
# Запуск на сервере из корня репозитория:
#   .\deploy-bot.ps1
#
# Что делает (НЕ трогает nginx/certbot/map-backend/frontend):
#   1. git pull --ff-only origin main
#   2. Пересобирает Docker-образ бота
#   3. Заменяет контейнер rkk-bot новым образом (том с БД сохраняется)
#
# Требование: рядом со скриптом файл .env с секретами
#   (BOT_TOKEN, ADMIN_ID, MEGAPLAN_*, PERPLEXITY_API_KEY, FRONTEND_BASE_URL,
#    APP_TIMEZONE_OFFSET, TELEGRAM_PROXY, NSPD_PROXY, GEMINI_PROXY).
# ===========================================

param(
    [switch]$NoPull,     # Пропустить git pull (только пересборка + перезапуск)
    [switch]$SkipBuild   # Пропустить сборку (только перезапуск контейнера)
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# --- Параметры (менять только если реально менялись имена) ---
$ImageTag   = "rkkbot:latest"
$Container  = "rkk-bot"
$DataVolume = "testprojectrkkobt2_data"                        # том с боевой БД
$Dockerfile = ".docker/python/Dockerfile"
$EnvFile    = Join-Path $PSScriptRoot ".env"
$DbUrl      = "sqlite+aiosqlite:////app/data/your_database.db"

function Step { param($m) Write-Host "`n==> $m" -ForegroundColor Cyan }
function Ok   { param($m) Write-Host "[OK] $m" -ForegroundColor Green }
function Fail { param($m) Write-Host "[ERROR] $m" -ForegroundColor Red }

Write-Host "===== RKK Bot deploy =====" -ForegroundColor Magenta
Write-Host "Время: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"

# --- Проверки окружения ---
if (-not (Test-Path $Dockerfile)) { Fail "Нет $Dockerfile — запусти скрипт из корня репозитория."; exit 1 }
if (-not (Test-Path $EnvFile))    { Fail "Нет .env рядом со скриптом — секреты обязательны."; exit 1 }
try { docker info *> $null } catch { Fail "Docker недоступен."; exit 1 }

# --- 1. Обновление кода из main ---
if (-not $NoPull) {
    Step "git pull --ff-only origin main"
    $branch = (git rev-parse --abbrev-ref HEAD).Trim()
    if ($branch -ne "main") { Fail "Текущая ветка '$branch', нужна 'main'. Переключись: git switch main"; exit 1 }
    git pull --ff-only origin main
    Ok "Код обновлён"
} else {
    Write-Host "[skip] git pull (-NoPull)" -ForegroundColor Yellow
}

# --- 2. Сборка образа бота ---
if (-not $SkipBuild) {
    Step "Сборка образа $ImageTag"
    docker build -t $ImageTag -f $Dockerfile .
    Ok "Образ собран"
} else {
    Write-Host "[skip] сборка (-SkipBuild)" -ForegroundColor Yellow
}

# --- 3. Замена контейнера бота (том с БД сохраняется) ---
Step "Пересоздание контейнера $Container"
docker rm -f $Container *> $null
docker run -d --name $Container --restart unless-stopped `
    --env-file $EnvFile `
    -e "DATABASE_URL=$DbUrl" `
    -v "${DataVolume}:/app/data" `
    $ImageTag python -m app_bot.bot *> $null
Ok "Контейнер пересоздан"

# --- 4. Статус и логи ---
Start-Sleep -Seconds 3
Step "Статус контейнера"
docker ps --filter "name=$Container"
Step "Логи (последние 25 строк)"
docker logs --tail 25 $Container

Write-Host "`nГотово. Проверь в Telegram, что бот отвечает и строка времени выезда на месте." -ForegroundColor Green
