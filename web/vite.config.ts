import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// The FastAPI backend (ui/server.py) serves /api; in development Vite proxies to it.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { port: 5174, proxy: { "/api": { target: "http://127.0.0.1:8780", changeOrigin: true } } },
});
