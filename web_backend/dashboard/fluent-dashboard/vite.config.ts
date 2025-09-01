import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const TAILSCALE_IP = "100.75.198.6";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,        // listen on 0.0.0.0
    port: 5173,
    strictPort: true,
    cors: true,
    hmr: {
      host: TAILSCALE_IP, // where the browser should connect for HMR
      port: 5173,
      protocol: "ws",
    },
  },
});