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

// Палитры цветов
const executorColors = [
  '#3498db', '#e74c3c', '#2ecc71', '#f39c12', '#9b59b6', '#1abc9c', 
  '#34495e', '#e67e22', '#16a085', '#c0392b', '#27ae60', '#2980b9', 
  '#8e44ad', '#d35400',
]
const dealColors = [
  '#e74c3c', '#3498db', '#2ecc71', '#f39c12', '#9b59b6', '#1abc9c', 
  '#34495e', '#e67e22',
]

// Нейтральный цвет для кластеров
const NEUTRAL_CLUSTER_COLOR = '#7f8c8d'; 

// Переменная для хранения текущего открытого попапа
let currentPopup = null;

// --- Функции для стилизации и контента (без изменений) ---

function getExecutorColor(executors) {
  const sortedExecutors = [...executors].sort().join(', ')
  if (executorsColorMap.has(sortedExecutors)) {
    return executorsColorMap.get(sortedExecutors)
  }
  const color = executorColors[executorColorIndex % executorColors.length]
  executorsColorMap.set(sortedExecutors, color)
  executorColorIndex++
  return color
}

function getDealColor(dealIndex) {
  return dealColors[dealIndex % dealColors.length]
}

function createMarkerHTML(feature) {
  const { deal, dealIndex, locationIndex } = feature.properties;
  const executorColor = getExecutorColor(deal.executors)
  const dealColor = getDealColor(dealIndex)
  
  return `
    <div class="custom-map-marker" style="
      background: ${executorColor}; color: white; padding: 8px 12px;
      border: 4px solid ${dealColor}; border-radius: 20px; font-weight: bold;
      font-size: 13px; cursor: pointer; box-shadow: 0 2px 10px rgba(0,0,0,0.3);
      white-space: nowrap; user-select: none; position: relative;
      transform: translate(-50%, -50%); transition: all 0.2s ease;
    " 
    onmouseover="this.style.transform='translate(-50%, -50%) scale(1.1)'; this.style.zIndex='1000'"
    onmouseout="this.style.transform='translate(-50%, -50%) scale(1)'; this.style.zIndex='1'">
      ${deal.deal_id}.${locationIndex + 1}
    </div>
  `
}

function createPopupHTML(feature) {
  const { deal, location } = feature.properties;
  const executorColor = getExecutorColor(deal.executors)
  
  return `
    <div style="
      background: white; padding: 15px; border-radius: 8px;
      box-shadow: 0 2px 10px rgba(0,0,0,0.2); min-width: 380px; max-width: 450px;
      font-family: Arial, sans-serif; border-top: 4px solid ${executorColor};
    ">
      <h3 style="margin: 0 0 10px 0; font-size: 14px; line-height: 1.3;">
        <a href="${deal.deal_url}" target="_blank" style="color: #0066cc; text-decoration: none;">
          ${deal.deal_name}
        </a>
      </h3>
      <div style="margin: 8px 0; font-size: 13px; color: #555;"><strong>ID сделки:</strong> ${deal.deal_id}</div>
      <div style="margin: 8px 0; font-size: 13px; color: #555;"><strong>Время визита:</strong> ${deal.visit_time}</div>
      <div style="margin: 8px 0; font-size: 13px; color: #555;">
        <strong>Исполнители:</strong><br>
        <div style="background: ${executorColor}20; padding: 5px 10px; border-radius: 4px; margin-top: 5px; border-left: 3px solid ${executorColor}; font-size: 12px;">
          ${deal.executors.join(', ')}
        </div>
      </div>
      <div style="margin: 8px 0; font-size: 13px; color: #555;">
        <strong>Кадастровый номер:</strong><br>
        <span style="font-family: monospace; background: #f5f5f5; padding: 2px 5px; border-radius: 3px; font-size: 12px;">
          ${location.cadastral_number}
        </span>
      </div>
    </div>
  `
}

function createLegend() {
    let legendHTML = `
    <div style="
      position: absolute; bottom: 20px; right: 20px; background: white;
      padding: 15px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.2);
      max-width: 300px; max-height: 400px; overflow-y: auto;
      font-family: Arial, sans-serif; z-index: 1000;
    ">
      <h4 style="margin: 0 0 10px 0; font-size: 14px; color: #333;">Исполнители:</h4>
      <div style="font-size: 12px;">
  `;
  executorsColorMap.forEach((color, executors) => {
    legendHTML += `
      <div style="margin: 5px 0; display: flex; align-items: center;">
        <div style="width: 20px; height: 20px; background: ${color}; border-radius: 50%; margin-right: 8px; flex-shrink: 0;"></div>
        <div style="color: #555; line-height: 1.2;">${executors}</div>
      </div>
    `
  });
  legendHTML += `
      </div>
      <div style="margin-top: 15px; padding-top: 10px; border-top: 1px solid #eee;">
        <p style="margin: 0; font-size: 11px; color: #888;">
          Цвет маркера - исполнитель<br>
          Цвет обводки - сделка
        </p>
      </div>
    </div>
  `;
  return legendHTML;
}


// Функция инициализации карты
async function initMap() {
  try {
    const ymaps3 = await loadYandexMaps();
    const {YMap, YMapDefaultSchemeLayer, YMapDefaultFeaturesLayer, YMapMarker} = ymaps3;
    const {YMapClusterer, clusterByGrid} = await ymaps3.import('@yandex/ymaps3-clusterer');
    
    const allCoords = [];
    const points = [];
    props.deals.forEach((deal, dealIndex) => {
      deal.locations.forEach((location, locationIndex) => {
        allCoords.push(location.coords);
        points.push({
          type: 'Feature',
          id: `${deal.deal_id}-${locationIndex}`,
          geometry: { type: 'Point', coordinates: location.coords },
          properties: { deal, dealIndex, locationIndex, location }
        });
      });
    });

    const bounds = calculateBounds(allCoords);
    const center = calculateCenter(bounds);
    const zoom = calculateZoom(bounds);

    const map = new ymaps3.YMap(document.getElementById('map'), {
      location: { center, zoom },
      behaviors: ['drag', 'pinchZoom', 'scrollZoom', 'dblClick']
    });

    map.addChild(new YMapDefaultSchemeLayer({}));
    map.addChild(new YMapDefaultFeaturesLayer({}));
    mapInstance.value = map; 
    
    map.isPopupActionInProgress = false;

    const mapContainer = document.getElementById('map');
    mapContainer.addEventListener('click', () => {
      if (map.isPopupActionInProgress) { return; }
      if (currentPopup) { map.removeChild(currentPopup); currentPopup = null; }
    });

    const marker = (feature) => {
      const markerElement = document.createElement('div');
      markerElement.innerHTML = createMarkerHTML(feature);
      const ymapMarker = new YMapMarker({ coordinates: feature.geometry.coordinates, properties: feature.properties, draggable: false }, markerElement);

      markerElement.addEventListener('click', (e) => {
          e.stopPropagation();
          map.isPopupActionInProgress = true;
          if (currentPopup) { map.removeChild(currentPopup); currentPopup = null; }
          const popupElement = document.createElement('div');
          popupElement.innerHTML = createPopupHTML(feature);
          popupElement.style.transform = 'translate(-50%, -100%) translateY(-20px)';
          const popup = new YMapMarker({ coordinates: feature.geometry.coordinates, draggable: false }, popupElement);
          map.addChild(popup);
          currentPopup = popup;
          popupElement.addEventListener('click', (e) => {
            e.stopPropagation();
            if (e.target.tagName !== 'A') { map.removeChild(popup); currentPopup = null; }
          });
          setTimeout(() => { map.isPopupActionInProgress = false; }, 100);
      });
      return ymapMarker;
    };

    function createStackedPopup(features, coordinates) {
        let currentIndex = 0;

        const popupContainer = document.createElement('div');
        popupContainer.style.position = 'relative';
        const contentWrapper = document.createElement('div');
        contentWrapper.className = 'stacked-popup-content';
        const navWrapper = document.createElement('div');

        // ИЗМЕНЕНИЕ: делаем фон белым и добавляем разделитель
        navWrapper.style.cssText = `
            display: flex; justify-content: space-between; align-items: center;
            background: #ffffff; padding: 8px 10px;
            border-top: 1px solid #eee;
            border-radius: 0 0 8px 8px;
        `;
        
        const prevButton = document.createElement('button');
        prevButton.innerText = '← Назад';
        prevButton.className = 'stacked-popup-btn';
        const counter = document.createElement('span');
        counter.style.cssText = `font-size: 12px; color: #212529; font-weight: 500;`; // Более темный текст
        const nextButton = document.createElement('button');
        nextButton.innerText = 'Вперед →';
        nextButton.className = 'stacked-popup-btn';

        navWrapper.appendChild(prevButton);
        navWrapper.appendChild(counter);
        navWrapper.appendChild(nextButton);
        
        function updateContent() {
            contentWrapper.innerHTML = createPopupHTML(features[currentIndex]);
            const innerDiv = contentWrapper.firstElementChild; 
            if(innerDiv) {
                innerDiv.style.borderRadius = '8px 8px 0 0';
                innerDiv.style.borderBottom = 'none';
                innerDiv.style.boxShadow = '0 2px 10px rgba(0,0,0,0.2), 0 0 0 1px rgba(0,0,0,0.1)';
            }
            counter.innerText = `${currentIndex + 1} из ${features.length}`;
            prevButton.disabled = currentIndex === 0;
            nextButton.disabled = currentIndex === features.length - 1;
        }

        prevButton.addEventListener('click', e => { e.stopPropagation(); if (currentIndex > 0) { currentIndex--; updateContent(); } });
        nextButton.addEventListener('click', e => { e.stopPropagation(); if (currentIndex < features.length - 1) { currentIndex++; updateContent(); } });
        
        popupContainer.appendChild(contentWrapper);
        popupContainer.appendChild(navWrapper);
        updateContent();
        popupContainer.style.transform = 'translate(-50%, -100%) translateY(-20px)';
        
        return new YMapMarker({ coordinates, draggable: false }, popupContainer);
    }
    
    const cluster = (coordinates, features) => {
        const uniqueColors = new Set( features.map(feature => getExecutorColor(feature.properties.deal.executors)) );
        let clusterColor = uniqueColors.size === 1 ? uniqueColors.values().next().value : NEUTRAL_CLUSTER_COLOR;
        const circle = document.createElement('div');
        circle.classList.add('cluster-circle');
        circle.style.color = clusterColor; 
        circle.innerHTML = `<div class="cluster-circle-content"><span class="cluster-circle-text">${features.length}</span></div>`;
        return new YMapMarker( { coordinates, onClick: () => {
                const firstCoord = features[0].geometry.coordinates;
                const allSameCoords = features.every( f => f.geometry.coordinates[0] === firstCoord[0] && f.geometry.coordinates[1] === firstCoord[1] );
                if (allSameCoords && features.length > 1) {
                    map.isPopupActionInProgress = true;
                    if (currentPopup) { map.removeChild(currentPopup); }
                    const stackedPopup = createStackedPopup(features, coordinates);
                    map.addChild(stackedPopup);
                    currentPopup = stackedPopup;
                    setTimeout(() => { map.isPopupActionInProgress = false; }, 100);
                } else {
                    if (currentPopup) { map.removeChild(currentPopup); currentPopup = null; }
                    const clusterBounds = getBounds(features.map(f => f.geometry.coordinates));
                    map.update({ location: { bounds: clusterBounds, duration: 500, easing: 'ease-in-out' }});
                }
            } }, circle );
    };

    const clusterer = new YMapClusterer({ method: clusterByGrid({ gridSize: 64 }), features: points, marker, cluster });
    map.addChild(clusterer);
    const legendElement = document.createElement('div');
    legendElement.innerHTML = createLegend();
    mapContainer.appendChild(legendElement.firstElementChild);

  } catch (error) {
    console.error('Ошибка при инициализации карты:', error);
  }
}

// Вспомогательные функции (без изменений)
function getBounds(coordinates) {
  let minLat = Infinity, minLng = Infinity;
  let maxLat = -Infinity, maxLng = -Infinity;
  for (const coords of coordinates) {
    const lng = coords[0];
    const lat = coords[1];
    if (lat < minLat) minLat = lat;
    if (lat > maxLat) maxLat = lat;
    if (lng < minLng) minLng = lng;
    if (lng > maxLng) maxLng = lng;
  }
  const lonPadding = (maxLng - minLng) * 0.1 || 0.01;
  const latPadding = (maxLat - minLat) * 0.1 || 0.01;
  return [ [minLng - lonPadding, minLat - latPadding], [maxLng + lonPadding, maxLat + latPadding] ];
}
function calculateBounds(coords) {
  if (coords.length === 0) return { minLon: 37.6, maxLon: 37.7, minLat: 55.7, maxLat: 55.8 }
  const [[minLon, minLat], [maxLon, maxLat]] = getBounds(coords);
  return { minLon, minLat, maxLon, maxLat };
}
function calculateCenter(bounds) { return [(bounds.minLon + bounds.maxLon) / 2, (bounds.minLat + bounds.maxLat) / 2] }
function calculateZoom(bounds) {
  const lonDiff = bounds.maxLon - bounds.minLon;
  const latDiff = bounds.maxLat - bounds.minLat;
  const maxDiff = Math.max(lonDiff, latDiff);
  if (maxDiff > 5) return 5; if (maxDiff > 2) return 7; if (maxDiff > 1) return 8;
  if (maxDiff > 0.5) return 9; if (maxDiff > 0.2) return 10; if (maxDiff > 0.1) return 11;
  if (maxDiff > 0.05) return 12; if (maxDiff > 0.02) return 13; if (maxDiff > 0.01) return 14;
  if (maxDiff > 0.005) return 15; return 16;
}

// Хуки жизненного цикла
onMounted(() => { initMap(); });
onUnmounted(() => { if (mapInstance.value) { mapInstance.value.destroy(); } });
</script>

<style>
/* Глобальные стили для кластеров и попапов */
.cluster-circle {
  position: absolute;
  width: 40px;
  height: 40px;
  color: #eb5547;
  border-radius: 50%;
  background-color: rgba(255, 255, 255, 0.7);
  box-shadow: 2px 2px 5px rgba(0, 0, 0, 0.2);
  transform: translate(-50%, -50%);
  cursor: pointer;
  transition: transform 0.2s ease;
}
.cluster-circle:hover {
  transform: translate(-50%, -50%) scale(1.1);
}
.cluster-circle-content {
  position: absolute;
  top: 50%;
  left: 50%;
  display: flex;
  justify-content: center;
  align-items: center;
  width: 90%;
  height: 90%;
  border-radius: 50%;
  background-color: currentColor;
  transform: translate3d(-50%, -50%, 0);
}
.cluster-circle-text {
  font-size: 16px;
  font-weight: 500;
  line-height: 20px;
  color: #fff;
}

/* ИЗМЕНЕНИЕ: более контрастные стили для кнопок пагинации */
.stacked-popup-btn {
    background-color: #ffffff;
    border: 1px solid #ccc;
    border-radius: 4px;
    padding: 5px 10px;
    cursor: pointer;
    font-size: 12px;
    color: #333;
    font-weight: 500;
    transition: background-color 0.2s;
}
.stacked-popup-btn:disabled {
    background-color: #f8f8f8;
    color: #aaa;
    cursor: not-allowed;
    border-color: #eee;
}
.stacked-popup-btn:hover:not(:disabled) {
    background-color: #f0f0f0;
    border-color: #adadad;
}
</style>

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
  
  .map-container > div[style*="bottom: 20px"] {
    bottom: 10px !important;
    right: 10px !important;
    max-width: 200px !important;
    font-size: 11px !important;
  }
}
</style>