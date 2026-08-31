# ===========================================
# deploy.ps1 — единый скрипт развёртывания
# ===========================================
# Запускать НА СЕРВЕРЕ из боевого каталога C:\Apps\TESTPROJECTRKKOBT2
#
#   .\deploy.ps1                      # обновить только бота (самый частый случай)
#   .\deploy.ps1 -Service all         # обновить весь стек
#   .\deploy.ps1 -NoPull -NoBuild     # перечитать .env без обновления кода
#
# Подробности и разбор нештатных ситуаций — в DEPLOY.md
# ===========================================

param(
    # Что обновляем: bot | backend | web | all
    [ValidateSet("bot", "backend", "web", "all")]
    [string]$Service = "bot",

    [switch]$NoPull,    # не тянуть код из git
    [switch]$NoBuild    # не пересобирать образ (нужно, если поменялся только .env)
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# Имя тома с боевой БД. Должно совпадать с `name:` в docker-compose.yml + "_data".
$DataVolume = "testprojectrkkobt2_data"

function Step { param($m) Write-Host "`n==> $m" -ForegroundColor Cyan }
function Ok   { param($m) Write-Host "[OK] $m" -ForegroundColor Green }
function Warn { param($m) Write-Host "[!] $m" -ForegroundColor Yellow }
function Fail { param($m) Write-Host "[ERROR] $m" -ForegroundColor Red }

Write-Host "===== RKK deploy | сервис: $Service =====" -ForegroundColor Magenta
Write-Host "Каталог: $PSScriptRoot"
Write-Host "Время:   $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"

# --- Проверки окружения -------------------------------------------------
Step "Проверки"

if (-not (Test-Path "docker-compose.yml")) {
    Fail "Нет docker-compose.yml — запусти скрипт из корня боевого каталога."
    exit 1
}
if (-not (Test-Path ".env")) {
    Fail "Нет .env — без него контейнеры стартуют без токенов и прокси."
    Write-Host "Состав переменных смотри в .env.example" -ForegroundColor Yellow
    exit 1
}
try { docker info *> $null } catch { Fail "Docker недоступен."; exit 1 }

# Том с боевой базой должен существовать. Если его нет — почти наверняка
# сбито имя проекта, и compose вот-вот создаст пустую БД вместо рабочей.
$volumeExists = docker volume ls --format "{{.Name}}" | Select-String -SimpleMatch $DataVolume
if (-not $volumeExists) {
    Fail "Не найден том $DataVolume — велик риск стартовать с ПУСТОЙ базой."
    Write-Host "Проверь строку 'name:' в docker-compose.yml и вывод 'docker volume ls'." -ForegroundColor Yellow
    exit 1
}

# Бот, запущенный мимо compose (через docker run), займёт имя контейнера
# и compose упадёт с 'container name already in use'. Ловим это заранее.
# Разбираем JSON, а не --format: PowerShell 5.1 портит вложенные кавычки
# в Go-шаблонах при передаче аргументов нативной команде.
$botJson = (docker inspect rkk-bot 2>$null | Out-String).Trim()
$botProject = $null
if ($botJson) {
    $botProject = (ConvertFrom-Json $botJson)[0].Config.Labels.'com.docker.compose.project'
}
if ($botJson -and [string]::IsNullOrWhiteSpace($botProject)) {
    Warn "Контейнер rkk-bot создан вручную (docker run), а не через compose."
    Write-Host "Убери его, прежде чем продолжать — том с БД при этом не пострадает:" -ForegroundColor Yellow
    Write-Host "  docker rename rkk-bot rkk-bot-manual; docker stop rkk-bot-manual" -ForegroundColor Gray
    exit 1
}
Ok "Окружение в порядке"

# --- 1. Обновление кода -------------------------------------------------
if (-not $NoPull) {
    Step "git pull --ff-only origin main"
    $branch = (git rev-parse --abbrev-ref HEAD).Trim()
    if ($branch -ne "main") {
        Fail "Текущая ветка '$branch', а прод живёт на 'main'. Переключись: git switch main"
        exit 1
    }
    if (git status --porcelain) {
        Fail "В рабочем дереве есть незакоммиченные изменения:"
        git status --short
        Write-Host "Закоммить их или откати — прод должен точно соответствовать git." -ForegroundColor Yellow
        exit 1
    }
    git pull --ff-only origin main
    Ok "Код обновлён до $((git rev-parse --short HEAD).Trim())"
} else {
    Warn "Пропуск git pull (-NoPull)"
}

# --- 2. Какие сервисы трогаем -------------------------------------------
switch ($Service) {
    "bot"     { $targets = @("bot") }
    "backend" { $targets = @("map-backend") }
    "web"     { $targets = @("nginx") }
    "all"     { $targets = @("map-backend", "bot", "nginx") }
}

# --- 3. Сборка ----------------------------------------------------------
if (-not $NoBuild) {
    Step "Сборка образов: $($targets -join ', ')"
    docker compose build $targets
    Ok "Образы собраны"
} else {
    Warn "Пропуск сборки (-NoBuild)"
}

# --- 4. Пересоздание контейнеров ----------------------------------------
# --no-deps обязателен: без него depends_on подтянет и пересоздаст map-backend
# даже при обновлении одного бота, а после этого nginx отдаёт 502.
# Все нужные сервисы перечислены в $targets явно.
Step "Пересоздание: $($targets -join ', ')"
docker compose up -d --force-recreate --no-deps $targets
Ok "Контейнеры подняты"

# nginx кеширует IP контейнера map-backend на момент своего старта.
# Если бэкенд пересоздан — nginx до перезапуска будет отдавать 502.
if (($targets -contains "map-backend") -and ($targets -notcontains "nginx")) {
    Step "Перезапуск nginx (сброс кеша DNS для map-backend)"
    docker compose restart nginx
    Ok "nginx перезапущен"
}

# --- 5. Статус и логи ---------------------------------------------------
Start-Sleep -Seconds 3
Step "Статус"
docker compose ps

Step "Логи (последние 20 строк по каждому обновлённому сервису)"
foreach ($t in $targets) {
    Write-Host "`n--- $t ---" -ForegroundColor Yellow
    docker compose logs --tail 20 $t
}

Write-Host "`nГотово." -ForegroundColor Green
if ($targets -contains "bot") {
    Write-Host "Проверь в Telegram, что бот отвечает и список заявок отдаётся с данными." -ForegroundColor Gray
}
if ($targets -contains "nginx") {
    Write-Host "Проверь https://turbomap.mooo.com — карта открывается, сертификат валиден." -ForegroundColor Gray
}
