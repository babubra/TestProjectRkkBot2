// Получаем API ключ из переменных окружения
const API_KEY = import.meta.env.VITE_YANDEX_MAPS_API_KEY

// Флаг для отслеживания загрузки
let isLoading = false
let isLoaded = false
let loadPromise = null

/**
 * Загружает API Яндекс.Карт версии 3.0
 * @returns {Promise} Промис, который резолвится когда карты загружены
 */
export function loadYandexMaps() {
  // Если уже загружено, возвращаем resolved промис
  if (isLoaded && window.ymaps3) {
    return Promise.resolve(window.ymaps3)
  }

  // Если уже загружается, возвращаем существующий промис
  if (isLoading && loadPromise) {
    return loadPromise
  }

  // Начинаем загрузку
  isLoading = true
  
  loadPromise = new Promise((resolve, reject) => {
    // Создаем script тег
    const script = document.createElement('script')
    script.src = `https://api-maps.yandex.ru/3.0/?apikey=${API_KEY}&lang=ru_RU`
    script.async = true
    
    script.onload = async () => {
      try {
        // Ждем инициализации ymaps3
        await ymaps3.ready
        isLoaded = true
        isLoading = false
        console.log('Яндекс.Карты 3.0 загружены успешно')
        resolve(window.ymaps3)
      } catch (error) {
        isLoading = false
        reject(new Error('Ошибка инициализации Яндекс.Карт'))
      }
    }
    
    script.onerror = () => {
      isLoading = false
      reject(new Error('Не удалось загрузить Яндекс.Карты. Проверьте API ключ.'))
    }
    
    document.head.appendChild(script)
  })
  
  return loadPromise
}