/// <reference types="vitest/config" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Fail loudly if 5173 is taken instead of quietly moving to another port,
    // which leaves an old server answering on the URL you have open
    port: 5173,
    strictPort: true,
    // Same-origin /api in dev, like nginx does in Docker
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
  },
});
