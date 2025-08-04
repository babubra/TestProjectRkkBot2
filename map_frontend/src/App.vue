<template>
  <div id="app">
    <!-- Состояние загрузки -->
    <LoadingState v-if="isLoading" />
    
    <!-- Состояние ошибки -->
    <ErrorState v-else-if="error" :error="error" />
    
    <!-- Карта -->
    <MapView v-else-if="dealsData.length > 0" :deals="dealsData" />
    
    <!-- Нет данных -->
    <ErrorState v-else :error="{ message: 'Нет данных для отображения' }" />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import MapView from './components/MapView.vue'
import LoadingState from './components/LoadingState.vue'
import ErrorState from './components/ErrorState.vue'
import { fetchMapData } from './services/api.js'

// Реактивные переменные для хранения состояния
const isLoading = ref(true)
const error = ref(null)
const dealsData = ref([])

// Функция для получения токена из URL
const getTokenFromUrl = () => {
  const urlParams = new URLSearchParams(window.location.search)
  return urlParams.get('token')
}

// При монтировании компонента загружаем данные
onMounted(async () => {
  try {
    const token = getTokenFromUrl()
    
    if (!token) {
      throw new Error('Токен не найден в URL. Проверьте правильность ссылки.')
    }
    
    console.log('Загрузка данных для токена:', token)
    
    // Запрашиваем данные с бэкенда
    const data = await fetchMapData(token)
    dealsData.value = data
    
    console.log('Получены данные:', data)
  } catch (err) {
    console.error('Ошибка загрузки данных:', err)
    error.value = err
  } finally {
    isLoading.value = false
  }
})
</script>