import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

const backendTarget = process.env.VITE_BACKEND_ORIGIN ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    watch: {
      ignored: [
        "**/history/**",
        "**/data/**",
        "**/reference_pdfs/**",
        "**/static/**",
        "**/*.tsbuildinfo"
      ]
    },
    proxy: {
      "/api": {
        target: backendTarget,
        changeOrigin: true
      },
      "/analyze": {
        target: backendTarget,
        changeOrigin: true
      },
      "/pdf": {
        target: backendTarget,
        changeOrigin: true
      }
    }
  }
});
