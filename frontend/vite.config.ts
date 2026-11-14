/// <reference types="vitest/config" />
import { readFileSync } from "node:fs";
import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";

/**
 * Emits `sw.js` (from sw/service-worker.js) into a production build, with this build's id and
 * the files the installed app needs to open offline. The id changes on every build, so a deploy
 * always ships a new worker, which replaces the old build's files: the installed app can't stay
 * on an old version. Not used in `vite dev`, where a worker would only get in the way.
 */
function serviceWorker(): Plugin {
  // Files from public/ the app shows; everything Vite builds is added from the bundle.
  const publicFiles = [
    "/",
    "/favicon.svg",
    "/site.webmanifest",
    "/apple-touch-icon.png",
    "/icon-192.png",
    "/icon-512.png",
    "/icon-maskable-512.png",
  ];
  return {
    name: "ardoise-service-worker",
    apply: "build",
    generateBundle(_options, bundle) {
      const built = Object.keys(bundle)
        .filter((file) => file !== "index.html" && !file.endsWith(".map"))
        .map((file) => `/${file}`);
      const source = readFileSync(new URL("./sw/service-worker.js", import.meta.url), "utf8")
        .replace('"__ARDOISE_BUILD_ID__"', JSON.stringify(Date.now().toString(36)))
        .replace("/*__ARDOISE_PRECACHE__*/ []", JSON.stringify([...publicFiles, ...built]));
      this.emitFile({ type: "asset", fileName: "sw.js", source });
    },
  };
}

// In production the API is served same-origin (FastAPI serves the built SPA), so the app calls `/api/v1`
// relatively (see src/api/client.ts) — no CORS. In dev, proxy `/api` and `/health` to the backend on :8000
// so the same relative code works without CORS or an absolute URL.
export default defineConfig({
  plugins: [react(), serviceWorker()],
  server: {
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/health": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    // Tests import { describe, it, expect } explicitly rather than relying on globals, so the
    // tsconfig needs no extra `types` entry and an unimported helper is a type error.
    globals: false,
    css: false,
  },
});
