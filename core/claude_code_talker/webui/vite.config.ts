import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:17832",
      "/m": "http://localhost:17832",
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
