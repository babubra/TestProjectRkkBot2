import axios from 'axios'

// В production используем относительный путь (через nginx proxy)
// В development используем VITE_API_BASE_URL из .env
const API_BASE_URL = import.meta.env.PROD 
  ? ''  // Production: используем относительные пути (будет проксироваться через nginx)
  : (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000')

// Создаем экземпляр axios с базовыми настройками
const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10000, // 10 секунд таймаут
  headers: {
    'Content-Type': 'application/json',
  }
})

/**
 * Получает данные о сделках по токену
 * @param {string} token - Уникальный токен из URL
 * @returns {Promise<Array>} Массив данных о сделках
 */
export async function fetchMapData(token) {
  try {
    const response = await apiClient.get(`/api/v1/map-data/${token}`)
    return response.data
  } catch (error) {
    // Обрабатываем разные типы ошибок
    if (error.response) {
      // Сервер ответил с ошибкой
      if (error.response.status === 404) {
        throw new Error('Ссылка недействительна или устарела. Запросите новую ссылку в боте.')
      } else if (error.response.status === 500) {
        throw new Error('Ошибка на сервере. Попробуйте позже.')
      } else {
        throw new Error(`Ошибка сервера: ${error.response.status}`)
      }
    } else if (error.request) {
      // Запрос был отправлен, но ответ не получен
      throw new Error('Не удалось связаться с сервером. Проверьте подключение к интернету.')
    } else {
      // Что-то еще пошло не так
      throw new Error('Произошла неизвестная ошибка.')
    }
  }
}