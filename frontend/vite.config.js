import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: 'dist',
  },
  server: {
    port: 3000,
    open: true,
    // Dev mode: forwards API calls to backend (no CORS issues)
    proxy: {
      '/translate':           'http://localhost:8000',
      '/session':             'http://localhost:8000',
      '/sessions':            'http://localhost:8000',
      '/health':              'http://localhost:8000',
      '/memory':              'http://localhost:8000',
      '/supported-languages': 'http://localhost:8000',
    }
  }
})