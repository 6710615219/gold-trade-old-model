import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // Send all /api requests to FastAPI
      '/api': 'http://127.0.0.1:8000',
      // Send Huasengheng requests through a proxy to avoid CORS
      '/hsh-api': {
        target: 'https://apicheckpricev3.huasengheng.com',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/hsh-api/, '')
      }
    }
  }
})