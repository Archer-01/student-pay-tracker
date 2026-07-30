import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In production the API is served same-origin (FastAPI serves the built SPA), so the app calls `/api/v1`
// relatively (see src/api/client.ts) — no CORS. In dev, proxy `/api` and `/health` to the backend on :8000
// so the same relative code works without CORS or an absolute URL.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/health": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
});
