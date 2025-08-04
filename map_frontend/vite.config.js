import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      // Проксирование запросов к API для избежания CORS проблем в разработке
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      }
    }
  }
})