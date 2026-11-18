import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwind from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwind()],
  build: { rollupOptions: { output: { manualChunks(id) {
    if (id.includes('/node_modules/recharts/') || id.includes('/node_modules/d3-')) return 'charts'
  } } } },
  server: { proxy: { '/api': process.env.VITE_API_TARGET || 'http://127.0.0.1:8000' } },
})
