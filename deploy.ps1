# ===========================================
# deploy.ps1 - Скрипт развёртывания на сервере
# ===========================================
# Запускать на сервере из директории проекта:
#   .\deploy.ps1
#
# Что делает:
#   1. Стягивает последние изменения из GitHub
#   2. Пересобирает Docker-образы
#   3. Перезапускает контейнеры с новым кодом
# ===========================================

param(
    [switch]$Force,       # Принудительное обновление (сброс локальных изменений)
    [switch]$NoPull,      # Пропустить git pull (только пересборка)
    [switch]$SkipBuild    # Пропустить сборку (только перезапуск)
)

$ErrorActionPreference = "Stop"

# Цвета для вывода
function Write-Step { param($msg) Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-Success { param($msg) Write-Host "[OK] $msg" -ForegroundColor Green }
function Write-Warn { param($msg) Write-Host "[!] $msg" -ForegroundColor Yellow }
function Write-Fail { param($msg) Write-Host "[ERROR] $msg" -ForegroundColor Red }

Write-Host ""
Write-Host "============================================" -ForegroundColor Magenta
Write-Host "   RKK Bot - Deployment Script" -ForegroundColor Magenta
Write-Host "============================================" -ForegroundColor Magenta
Write-Host "   Время: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host ""

# Проверка что мы в правильной директории
if (-not (Test-Path "docker-compose.yml")) {
    Write-Fail "Файл docker-compose.yml не найден!"
    Write-Host "Убедитесь, что вы находитесь в корне проекта." -ForegroundColor Yellow
    exit 1
}

# Проверка что Docker запущен
try {
    docker info | Out-Null
} catch {
    Write-Fail "Docker не запущен или недоступен!"
    exit 1
}

# ========================================
# ШАГ 1: Получение обновлений из GitHub
# ========================================
if (-not $NoPull) {
    Write-Step "Получение обновлений из GitHub..."
    
    # Проверяем текущую ветку
    $currentBranch = git rev-parse --abbrev-ref HEAD
    Write-Host "Текущая ветка: $currentBranch"
    
    # Получаем информацию о remote
    git fetch origin
    
    # Проверяем есть ли локальные изменения
    $status = git status --porcelain
    if ($status) {
        if ($Force) {
            Write-Warn "Обнаружены локальные изменения. Сбрасываем (--Force)..."
            git reset --hard HEAD
            git clean -fd
        } else {
            Write-Warn "Обнаружены локальные изменения:"
            git status --short
            Write-Host ""
            Write-Host "Используйте -Force для сброса локальных изменений" -ForegroundColor Yellow
            Write-Host "Или закоммитьте/сохраните изменения вручную" -ForegroundColor Yellow
            exit 1
        }
    }
    
    # Показываем что будет обновлено
    $behind = git rev-list --count HEAD..origin/$currentBranch 2>$null
    if ($behind -gt 0) {
        Write-Host "Доступно $behind новых коммитов:"
        git log --oneline HEAD..origin/$currentBranch | Select-Object -First 5
        if ($behind -gt 5) { Write-Host "... и ещё $($behind - 5) коммитов" }
    } else {
        Write-Success "Код уже актуален!"
    }
    
    # Применяем изменения
    git pull origin $currentBranch
    Write-Success "Код обновлён!"
} else {
    Write-Warn "Пропуск git pull (--NoPull)"
}

# ========================================
# ШАГ 2: Пересборка Docker-образов
# ========================================
if (-not $SkipBuild) {
    Write-Step "Пересборка Docker-образов..."
    
    # Сборка с использованием кэша для ускорения
    docker-compose build
    
    Write-Success "Образы пересобраны!"
} else {
    Write-Warn "Пропуск сборки (--SkipBuild)"
}

# ========================================
# ШАГ 3: Перезапуск контейнеров
# ========================================
Write-Step "Перезапуск контейнеров..."

# Останавливаем пересобранные сервисы
docker-compose stop bot map-backend

# Запускаем с принудительным пересозданием (новые IP-адреса)
docker-compose up -d --force-recreate bot map-backend

# Перезапускаем nginx чтобы он обновил DNS-резолюцию внутренней сети
Write-Step "Перезапуск nginx для обновления DNS..."
docker-compose restart nginx

Write-Success "Контейнеры перезапущены!"

# ========================================
# ШАГ 4: Проверка статуса
# ========================================
Write-Step "Проверка статуса контейнеров..."
Start-Sleep -Seconds 3

docker-compose ps

# Показываем последние логи каждого сервиса
Write-Step "Последние логи (5 строк)..."
Write-Host ""
Write-Host "--- rkk-bot ---" -ForegroundColor Yellow
docker logs rkk-bot --tail 5 2>&1
Write-Host ""
Write-Host "--- rkk-map-backend ---" -ForegroundColor Yellow
docker logs rkk-map-backend --tail 5 2>&1

Write-Host ""
Write-Host "============================================" -ForegroundColor Magenta
Write-Host "   Развёртывание завершено!" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Magenta
Write-Host ""
Write-Host "Полезные команды:" -ForegroundColor Gray
Write-Host "  docker-compose logs -f bot        # Логи бота в реальном времени"
Write-Host "  docker-compose logs -f map-backend # Логи бэкенда"
Write-Host "  docker-compose restart bot        # Перезапуск только бота"
Write-Host ""
