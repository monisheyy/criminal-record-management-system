import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // The API only accepts requests from http://localhost:5173 (CORS_ORIGINS), so
  // fail loudly if the port is busy instead of silently moving to 5174, where
  // every request would be rejected as "Cannot reach the server".
  server: { host: 'localhost', port: 5173, strictPort: true },
})
