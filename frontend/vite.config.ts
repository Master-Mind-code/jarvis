import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig(({ command }) => ({
  // En prod (build), tout est servi sous /voice/ par FastAPI → préfixe les paths.
  // En dev (npm run dev), reste à la racine pour que le dev server marche sur :5173/.
  base: command === "build" ? "/voice/" : "/",
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  server: {
    port: 5173,
    // En dev : proxy les WebSocket et /api vers le serveur FastAPI sur 8765
    proxy: {
      "/ws": { target: "ws://localhost:8765", ws: true, changeOrigin: true },
      "/api": { target: "http://localhost:8765", changeOrigin: true },
      "/assets": { target: "http://localhost:8765", changeOrigin: true },
      "/status": { target: "http://localhost:8765", changeOrigin: true },
      "/devices": { target: "http://localhost:8765", changeOrigin: true },
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    sourcemap: false,
    target: "es2020",
  },
}));
