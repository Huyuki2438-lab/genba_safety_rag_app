import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

const backendTarget = process.env.VITE_BACKEND_ORIGIN ?? "http://127.0.0.1:8000";

export default defineConfig({
  build: { outDir: "frontend_build", emptyOutDir: true },
  plugins: [react(), tailwindcss()],
  server: {
    watch: {
      ignored: [
        "**/history/**",
        "**/data/**",
        "**/tmp/**",
        "**/.step5-2-test/**",
        "**/.venv/**",
        "**/build/**",
        "**/dist/**",
        "**/frontend_build/**",
        "**/release/**",
        "**/pw-browsers/**",
        "**/reference_pdfs/**",
        "**/static/**",
        "**/*.tsbuildinfo"
      ]
    },
    proxy: {
      "/history": { target: backendTarget, changeOrigin: true },
      "/reports": { target: backendTarget, changeOrigin: true },
      "/api": {
        target: backendTarget,
        changeOrigin: false
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
