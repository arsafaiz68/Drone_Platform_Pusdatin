import { resolve } from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Drone Video Platform — satu frontend multi-halaman:
//   /             menu utama (pilih modul)
//   /downloader/  Drone Video Downloader (React + TypeScript + Tailwind)
//   /trimmer/     Drone Video Trimmer   (React)
//   /compiler/    Drone Video Compiler  (React, editor multi-track bertema gelap)
// Setiap halaman memuat CSS-nya sendiri sehingga tampilan kedua modul tidak saling bertabrakan.
const BACKEND = process.env.VITE_BACKEND_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: "localhost",
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": { target: BACKEND, changeOrigin: true, ws: true },
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    rollupOptions: {
      input: {
        main: resolve(__dirname, "index.html"),
        downloader: resolve(__dirname, "downloader/index.html"),
        trimmer: resolve(__dirname, "trimmer/index.html"),
        compiler: resolve(__dirname, "compiler/index.html"),
      },
    },
  },
});
