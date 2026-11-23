import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In dev (npm run dev on :5173), /api calls are forwarded to the API container.
// In production, FastAPI serves the built files and the API from one URL, so no proxy is needed.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { "/api": "http://localhost:8000" },
  },
});
