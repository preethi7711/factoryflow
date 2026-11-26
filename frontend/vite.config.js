import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { VitePWA } from "vite-plugin-pwa";

// In dev (npm run dev on :5173), /api calls are forwarded to the API container.
// In production, FastAPI serves the built files and the API from one URL, so no proxy is needed.
//
// PWA shell (P11): vite-plugin-pwa generates a service worker that precaches the built static
// assets (JS/CSS/fonts/SVGs), so the salesman can reopen the app on a train and keep queueing
// orders in localStorage. API responses are NOT cached (they're the live ledger and a stale copy
// would be worse than an honest offline banner); the salesman's existing online/offline UX tells
// them when the server is out of reach. `registerType: autoUpdate` ships new app versions on the
// next reload without a prompt — the Render auto-deploys are small and frequent.
export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["logo.svg", "maskable-icon.svg"],
      manifest: {
        name: "FactoryFlow",
        short_name: "FactoryFlow",
        description: "Order-to-audit for a small snack factory.",
        theme_color: "#E8A317",
        background_color: "#FFFDF8",
        display: "standalone",
        start_url: "/",
        scope: "/",
        icons: [
          { src: "/logo.svg", sizes: "any", type: "image/svg+xml" },
          {
            src: "/maskable-icon.svg",
            sizes: "any",
            type: "image/svg+xml",
            purpose: "maskable",
          },
        ],
      },
      workbox: {
        // Precache the built shell so the app opens offline.
        globPatterns: ["**/*.{js,css,html,svg,woff,woff2,ico,png}"],
        // /api is the live ledger: never cache it, never return a stale response.
        navigateFallbackDenylist: [/^\/api/],
        // index.html is the SPA shell; serve it for client-side routes offline.
        navigateFallback: "index.html",
      },
      devOptions: {
        // Keep the service worker off in dev: it would race with Vite's HMR, and the app's offline
        // behaviour is better verified against the real production build.
        enabled: false,
      },
    }),
  ],
  server: {
    proxy: { "/api": "http://localhost:8000" },
  },
});
