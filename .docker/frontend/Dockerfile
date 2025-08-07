# Этап 1: Сборка приложения
FROM node:20-alpine AS builder

# Объявляем ARG для передачи при сборке
ARG VITE_YANDEX_MAPS_API_KEY
ARG VITE_API_BASE_URL=""

WORKDIR /app

# Копируем package.json и package-lock.json
COPY map_frontend/package*.json ./

# Устанавливаем зависимости
RUN npm ci

# Копируем исходный код
COPY map_frontend/ .

# Создаем .env.production из переданных ARG
RUN echo "VITE_API_BASE_URL=${VITE_API_BASE_URL}" > .env.production && \
    echo "VITE_YANDEX_MAPS_API_KEY=${VITE_YANDEX_MAPS_API_KEY}" >> .env.production

# Собираем приложение для production
RUN npm run build

# Этап 2: Production образ с nginx
FROM nginx:alpine

# Копируем собранное приложение из builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Копируем конфигурацию nginx из нового расположения
COPY .docker/nginx/nginx.conf /etc/nginx/conf.d/default.conf # <--- ИЗМЕНЕНО

# Открываем порт 80
EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]