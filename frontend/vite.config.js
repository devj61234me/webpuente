import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development, /api calls are forwarded to the Django server, so no CORS setup is needed locally.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": { target: process.env.VITE_DEV_API_TARGET || "http://127.0.0.1:8000", changeOrigin: true } },
  },
  test: { environment: "jsdom", globals: true, setupFiles: ["./src/test/setup.js"] },
});
