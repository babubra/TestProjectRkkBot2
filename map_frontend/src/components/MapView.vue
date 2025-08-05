<template>
  <div id="map" class="map-container"></div>
</template>

<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import { loadYandexMaps } from '../utils/yandexMaps.js'

// Принимаем проп с данными о сделках
const props = defineProps({
  deals: {
    type: Array,
    required: true
  }
})

// Реф для хранения экземпляра карты
const mapInstance = ref(null)

// Map для хранения соответствия исполнителей и цветов
const executorsColorMap = new Map()
let executorColorIndex = 0

// Палитра цветов для исполнителей (основная заливка)
const executorColors = [
  '#3498db', // синий
  '#e74c3c', // красный
  '#2ecc71', // зеленый
  '#f39c12', // оранжевый
  '#9b59b6', // фиолетовый
  '#1abc9c', // бирюзовый
  '#34495e', // темно-серый
  '#e67e22', // темно-оранжевый
  '#16a085', // темно-бирюзовый
  '#c0392b', // темно-красный
  '#27ae60', // темно-зеленый
  '#2980b9', // темно-синий
  '#8e44ad', // темно-фиолетовый
  '#d35400', // коричневый
]

// Палитра цветов для сделок (обводка)
const dealColors = [
  '#e74c3c', // красный
  '#3498db', // синий
  '#2ecc71', // зеленый
  '#f39c12', // оранжевый
  '#9b59b6', // фиолетовый
  '#1abc9c', // бирюзовый
  '#34495e', // темно-серый
  '#e67e22', // темно-оранжевый
]

// Функция для получения цвета исполнителей
function getExecutorColor(executors) {
  // Сортируем исполнителей по алфавиту для консистентности
  const sortedExecutors = [...executors].sort().join(', ')
  
  // Если комбинация уже есть, возвращаем её цвет
  if (executorsColorMap.has(sortedExecutors)) {
    return executorsColorMap.get(sortedExecutors)
  }
  
  // Назначаем новый цвет
  const color = executorColors[executorColorIndex % executorColors.length]
  executorsColorMap.set(sortedExecutors, color)
  executorColorIndex++
  
  return color
}

// Функция для получения цвета сделки (для обводки)
function getDealColor(dealIndex) {
  return dealColors[dealIndex % dealColors.length]
}

// Функция для создания HTML контента маркера
function createMarkerHTML(deal, dealIndex, locationIndex) {
  const executorColor = getExecutorColor(deal.executors)
  const dealColor = getDealColor(dealIndex)
  
  return `
    <div class="custom-map-marker" style="
      background: ${executorColor};
      color: white;
      padding: 8px 12px;
      border: 4px solid ${dealColor};
      border-radius: 20px;
      font-weight: bold;
      font-size: 13px;
      cursor: pointer;
      box-shadow: 0 2px 10px rgba(0,0,0,0.3);
      white-space: nowrap;
      user-select: none;
      position: relative;
      transform: translate(-50%, -50%);
      transition: all 0.2s ease;
    " 
    onmouseover="this.style.transform='translate(-50%, -50%) scale(1.1)'; this.style.zIndex='1000'"
    onmouseout="this.style.transform='translate(-50%, -50%) scale(1)'; this.style.zIndex='1'">
      ${deal.deal_id}.${locationIndex + 1}
    </div>
  `
}

// Функция для создания контента попапа
function createPopupHTML(deal, cadastral) {
  const executorColor = getExecutorColor(deal.executors)
  
  return `
    <div style="
      background: white;
      padding: 15px;
      border-radius: 8px;
      box-shadow: 0 2px 10px rgba(0,0,0,0.2);
      max-width: 350px;
      font-family: Arial, sans-serif;
      border-top: 4px solid ${executorColor};
    ">
      <h3 style="margin: 0 0 10px 0; font-size: 16px;">
        <a href="${deal.deal_url}" target="_blank" style="color: #0066cc; text-decoration: none;">
          ${deal.deal_name}
        </a>
      </h3>
      <div style="margin: 8px 0; font-size: 14px; color: #555;">
        <strong>ID сделки:</strong> ${deal.deal_id}
      </div>
      <div style="margin: 8px 0; font-size: 14px; color: #555;">
        <strong>Время визита:</strong> ${deal.visit_time}
      </div>
      <div style="margin: 8px 0; font-size: 14px; color: #555;">
        <strong>Исполнители:</strong><br>
        <div style="
          background: ${executorColor}20;
          padding: 5px 10px;
          border-radius: 4px;
          margin-top: 5px;
          border-left: 3px solid ${executorColor};
        ">
          ${deal.executors.join(', ')}
        </div>
      </div>
      <div style="margin: 8px 0; font-size: 14px; color: #555;">
        <strong>Кадастровый номер:</strong><br>
        <span style="font-family: monospace; background: #f5f5f5; padding: 2px 5px; border-radius: 3px;">
          ${cadastral}
        </span>
      </div>
    </div>
  `
}

// Функция для создания легенды
function createLegend() {
  let legendHTML = `
    <div style="
      position: absolute;
      bottom: 20px;
      right: 20px;
      background: white;
      padding: 15px;
      border-radius: 8px;
      box-shadow: 0 2px 10px rgba(0,0,0,0.2);
      max-width: 300px;
      max-height: 400px;
      overflow-y: auto;
      font-family: Arial, sans-serif;
      z-index: 1000;
    ">
      <h4 style="margin: 0 0 10px 0; font-size: 14px; color: #333;">Исполнители:</h4>
      <div style="font-size: 12px;">
  `
  
  // Добавляем исполнителей в легенду
  executorsColorMap.forEach((color, executors) => {
    legendHTML += `
      <div style="margin: 5px 0; display: flex; align-items: center;">
        <div style="
          width: 20px;
          height: 20px;
          background: ${color};
          border-radius: 50%;
          margin-right: 8px;
          flex-shrink: 0;
        "></div>
        <div style="color: #555; line-height: 1.2;">${executors}</div>
      </div>
    `
  })
  
  legendHTML += `
      </div>
      <div style="margin-top: 15px; padding-top: 10px; border-top: 1px solid #eee;">
        <p style="margin: 0; font-size: 11px; color: #888;">
          Цвет маркера - исполнитель<br>
          Цвет обводки - сделка
        </p>
      </div>
    </div>
  `
  
  return legendHTML
}

// Функция инициализации карты
async function initMap() {
  try {
    console.log('Начинаем загрузку Яндекс.Карт...')
    const ymaps3 = await loadYandexMaps()
    
    // Собираем все координаты для определения границ
    const allCoords = []
    props.deals.forEach(deal => {
      deal.locations.forEach(location => {
        allCoords.push(location.coords)
      })
    })
    
    console.log('Всего точек на карте:', allCoords.length)
    
    // Вычисляем центр и границы
    const bounds = calculateBounds(allCoords)
    const center = calculateCenter(bounds)
    const zoom = calculateZoom(bounds)
    
    // Создаем карту
    const map = new ymaps3.YMap(document.getElementById('map'), {
      location: {
        center: center,
        zoom: zoom
      },
      behaviors: ['drag', 'pinchZoom', 'scrollZoom', 'dblClick']
    })
    
    // Добавляем необходимые слои
    const layer = new ymaps3.YMapDefaultSchemeLayer()
    map.addChild(layer)
    
    const features = new ymaps3.YMapDefaultFeaturesLayer()
    map.addChild(features)
    
    // Переменная для хранения текущего открытого попапа
    let currentPopup = null
    
    // Создаем маркеры для каждой сделки
    props.deals.forEach((deal, dealIndex) => {
      deal.locations.forEach((location, locationIndex) => {
        // Создаем HTML элемент маркера
        const markerElement = document.createElement('div')
        markerElement.innerHTML = createMarkerHTML(deal, dealIndex, locationIndex)
        
        // Создаем маркер с использованием YMapMarker
        const marker = new ymaps3.YMapMarker({
          coordinates: location.coords,
          draggable: false
        }, markerElement)
        
        // Добавляем обработчик клика на маркер
        markerElement.addEventListener('click', (e) => {
          e.stopPropagation()
          
          // Удаляем предыдущий попап если есть
          if (currentPopup) {
            map.removeChild(currentPopup)
            currentPopup = null
          }
          
          // Создаем элемент попапа
          const popupElement = document.createElement('div')
          popupElement.innerHTML = createPopupHTML(deal, location.cadastral_number)
          popupElement.style.transform = 'translate(-50%, -100%) translateY(-20px)'
          
          // Создаем попап как отдельный маркер
          const popup = new ymaps3.YMapMarker({
            coordinates: location.coords,
            draggable: false
          }, popupElement)
          
          // Добавляем попап на карту
          map.addChild(popup)
          currentPopup = popup
          
          // Закрываем попап при клике на него
          popupElement.addEventListener('click', (e) => {
            e.stopPropagation()
            if (e.target.tagName !== 'A') {
              map.removeChild(popup)
              currentPopup = null
            }
          })
        })
        
        // Добавляем маркер на карту
        map.addChild(marker)
      })
    })
    
    // Добавляем легенду
    const legendElement = document.createElement('div')
    legendElement.innerHTML = createLegend()
    document.getElementById('map').appendChild(legendElement.firstElementChild)
    
    // Закрываем попап при клике на карту
    const mapContainer = document.getElementById('map')
    mapContainer.addEventListener('click', () => {
      if (currentPopup) {
        map.removeChild(currentPopup)
        currentPopup = null
      }
    })
    
    // Сохраняем экземпляр карты
    mapInstance.value = map
    
    console.log('Карта успешно инициализирована')
    console.log('Уникальных комбинаций исполнителей:', executorsColorMap.size)
    
  } catch (error) {
    console.error('Ошибка при инициализации карты:', error)
  }
}

// Вспомогательные функции
function calculateBounds(coords) {
  if (coords.length === 0) return { minLon: 37.6, maxLon: 37.7, minLat: 55.7, maxLat: 55.8 }
  
  const bounds = {
    minLon: coords[0][0],
    maxLon: coords[0][0],
    minLat: coords[0][1],
    maxLat: coords[0][1]
  }
  
  coords.forEach(coord => {
    bounds.minLon = Math.min(bounds.minLon, coord[0])
    bounds.maxLon = Math.max(bounds.maxLon, coord[0])
    bounds.minLat = Math.min(bounds.minLat, coord[1])
    bounds.maxLat = Math.max(bounds.maxLat, coord[1])
  })
  
  // Добавляем отступ
  const lonPadding = (bounds.maxLon - bounds.minLon) * 0.1 || 0.01
  const latPadding = (bounds.maxLat - bounds.minLat) * 0.1 || 0.01
  
  bounds.minLon -= lonPadding
  bounds.maxLon += lonPadding
  bounds.minLat -= latPadding
  bounds.maxLat += latPadding
  
  return bounds
}

function calculateCenter(bounds) {
  return [
    (bounds.minLon + bounds.maxLon) / 2,
    (bounds.minLat + bounds.maxLat) / 2
  ]
}

function calculateZoom(bounds) {
  const lonDiff = bounds.maxLon - bounds.minLon
  const latDiff = bounds.maxLat - bounds.minLat
  const maxDiff = Math.max(lonDiff, latDiff)
  
  if (maxDiff > 5) return 5
  if (maxDiff > 2) return 7
  if (maxDiff > 1) return 8
  if (maxDiff > 0.5) return 9
  if (maxDiff > 0.2) return 10
  if (maxDiff > 0.1) return 11
  if (maxDiff > 0.05) return 12
  if (maxDiff > 0.02) return 13
  if (maxDiff > 0.01) return 14
  if (maxDiff > 0.005) return 15
  return 16
}

// Хуки жизненного цикла
onMounted(() => {
  initMap()
})

onUnmounted(() => {
  if (mapInstance.value) {
    mapInstance.value.destroy()
  }
})
</script>

<style scoped>
.map-container {
  width: 100%;
  height: 100%;
  position: relative;
  overflow: hidden;
}

/* Мобильная адаптация */
@media (max-width: 768px) {
  :deep(.custom-map-marker) {
    font-size: 11px !important;
    padding: 6px 8px !important;
  }
  
  /* Легенда на мобильных */
  .map-container > div[style*="bottom: 20px"] {
    bottom: 10px !important;
    right: 10px !important;
    max-width: 200px !important;
    font-size: 11px !important;
  }
}
</style>