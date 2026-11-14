import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import "./index.css";
import "./i18n";
import App from "./App.tsx";
import { ThemeProvider } from "./lib/theme.tsx";
import { AuthProvider } from "./lib/auth.tsx";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <ThemeProvider>
        <AuthProvider>
          <App />
        </AuthProvider>
      </ThemeProvider>
    </BrowserRouter>
  </StrictMode>,
);

// Offline support (sw/service-worker.js, built into dist/sw.js). Production only: in `vite dev` a
// worker would serve stale files over the live ones, and tests run without one.
if (import.meta.env.PROD && "serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {
      // Offline support is a bonus; the app works the same without it.
    });
  });
}
