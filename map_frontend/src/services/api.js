// map_frontend/src/services/api.js

import axios from 'axios';

// Создаем экземпляр axios.
// Мы НЕ указываем здесь baseURL, чтобы запросы были относительными.
// Они будут отправляться на тот же хост, с которого загружен сайт.
const apiClient = axios.create({
  timeout: 10000, // 10 секунд таймаут
  headers: {
    'Content-Type': 'application/json',
  }
});

/**
 * Получает данные о сделках по токену
 * @param {string} token - Уникальный токен из URL
 * @returns {Promise<Array>} Массив данных о сделках
 */
export async function fetchMapData(token) {
  try {
    // Теперь путь начинается с /api/, как и ожидает наш Nginx.
    const response = await apiClient.get(`/api/v1/map-data/${token}`);
    return response.data;
  } catch (error) {
    // Блок обработки ошибок остается без изменений. Он написан хорошо.
    if (error.response) {
      if (error.response.status === 404) {
        throw new Error('Ссылка недействительна или устарела. Запросите новую ссылку в боте.');
      } else if (error.response.status === 500) {
        throw new Error('Ошибка на сервере. Попробуйте позже.');
      } else {
        throw new Error(`Ошибка сервера: ${error.response.status}`);
      }
    } else if (error.request) {
      throw new Error('Не удалось связаться с сервером. Проверьте подключение к интернету.');
    } else {
      throw new Error('Произошла неизвестная ошибка.');
    }
  }
}