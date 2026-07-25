import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig(({ command }) => ({
  base: command === "build" ? process.env.VITE_BASE_PATH || "/" : "/",
  plugins: [vue()],
  server: {
    host: "127.0.0.1",
    port: 3810,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:3811",
        changeOrigin: true,
      },
      "/health": {
        target: "http://127.0.0.1:3811",
        changeOrigin: true,
      },
      "/ws": {
        target: "ws://127.0.0.1:3811",
        ws: true,
      },
    },
  },
}));
