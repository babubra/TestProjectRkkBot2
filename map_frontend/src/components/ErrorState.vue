<template>
  <div class="error-container">
    <h2 class="error-title">Упс! Что-то пошло не так</h2>
    <p class="error-message">{{ errorMessage }}</p>
  </div>
</template>

<script setup>
import { computed } from 'vue'

// Принимаем проп с ошибкой
const props = defineProps({
  error: {
    type: [Error, Object],
    required: true
  }
})

// Вычисляемое свойство для получения текста ошибки
const errorMessage = computed(() => {
  if (props.error instanceof Error) {
    return props.error.message
  }
  return props.error.message || 'Произошла неизвестная ошибка'
})
</script>