# Проект RKK Bot

Проект состоит из трех модулей:
- **app_bot** - Телеграм бот
- **map_backend** - Backend API (FastAPI)
- **map_frontend** - Frontend (Vue.js)

## Развертывание через Docker

### Предварительные требования

- Docker
- Docker Compose

### Быстрое развертывание

**Linux/macOS:**
```bash
chmod +x deploy.sh
./deploy.sh
```

**Windows:**
```cmd
deploy.bat
```

### Ручное развертывание

1. **Клонируйте репозиторий:**
   ```bash
   git clone <repository_url>
   cd TestProjectRkkBot2
   ```

2. **Настройте переменные окружения:**
   ```bash
   cp .env.example .env
   ```
   Отредактируйте файл `.env` и укажите ваши настройки:
   - `BOT_TOKEN` - токен вашего Telegram бота
   - `ADMIN_ID` - ваш Telegram ID
   - `MEGAPLAN_*` - настройки CRM системы
   - `PERPLEXITY_API_KEY` - API ключ для Perplexity
   - `FRONTEND_BASE_URL` - URL фронтенда (для продакшена)

3. **Создайте директорию для данных:**
   ```bash
   mkdir -p data
   ```

4. **Запустите все сервисы:**
   ```bash
   docker-compose up -d
   ```

5. **Проверьте статус сервисов:**
   ```bash
   docker-compose ps
   ```

### Доступ к сервисам

- **Frontend:** http://localhost
- **Backend API:** http://localhost:8000
- **API документация:** http://localhost:8000/docs

### Управление сервисами

- **Остановить все сервисы:**
  ```bash
  docker-compose down
  ```

- **Перезапустить сервисы:**
  ```bash
  docker-compose restart
  ```

- **Просмотр логов:**
  ```bash
  docker-compose logs -f [service_name]
  ```

- **Обновление после изменений в коде:**
  ```bash
  docker-compose down
  docker-compose build --no-cache
  docker-compose up -d
  ```

### Структура проекта

```
TestProjectRkkBot2/
├── app_bot/                 # Телеграм бот
│   ├── Dockerfile
│   ├── requirements.txt
│   └── ...
├── map_backend/             # Backend API
│   ├── Dockerfile
│   ├── requirements.txt
│   └── ...
├── map_frontend/            # Frontend
│   ├── Dockerfile
│   ├── package.json
│   ├── nginx.conf
│   └── ...
├── docker-compose.yml       # Конфигурация Docker Compose
├── .env                     # Переменные окружения
├── .env.example            # Пример переменных окружения
└── your_database.db        # База данных SQLite
```

### Особенности

- База данных SQLite (`your_database.db`) используется совместно ботом и бэкендом
- Все сервисы работают в одной Docker сети для взаимодействия
- Frontend проксирует API запросы к бэкенду через nginx
- Логи всех сервисов доступны через `docker-compose logs`

### Продакшен

Для продакшена рекомендуется:
1. Использовать PostgreSQL вместо SQLite
2. Настроить SSL сертификаты
3. Использовать внешний reverse proxy (nginx/traefik)
4. Настроить мониторинг и логирование
5. Использовать Docker Swarm или Kubernetes для оркестрации