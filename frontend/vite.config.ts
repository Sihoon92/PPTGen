import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: true, // bind 0.0.0.0 so a tunnel (ngrok) can reach the dev server
    port: 5173,
    allowedHosts: [".ngrok-free.app"], // allow ngrok's tunnel Host header (Vite 5 blocks unknown hosts)
    proxy: { "/api": "http://localhost:8000" },
  },
});
