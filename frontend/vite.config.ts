import { defineConfig, loadEnv } from "vite";
import vue from "@vitejs/plugin-vue";

// 生产挂在 /apps/orderflow/。Caddy 用 handle_path 剥前缀回源时，
// 后端看到的是 / 与 /assets；但浏览器仍从 /apps/orderflow/ 加载，
// 因此构建产物必须带完整 public base。
// 注意：Git Bash 会改写以 / 开头的环境变量路径，禁止用 VITE_BASE_PATH=/xxx。
export default defineConfig(({ command, mode }) => {
  const target = loadEnv(mode, ".", "").VITE_API_TARGET || "http://127.0.0.1:3811";
  const wsTarget = target.replace(/^http/, "ws");
  const productionBase = loadEnv(mode, ".", "").VITE_BASE_PATH || "/apps/orderflow/";
  return {
    base: command === "build" ? productionBase : "/",
    plugins: [vue()],
    server: {
      host: "127.0.0.1",
      port: 3810,
      proxy: {
        "/api": { target, changeOrigin: true },
        "/health": { target, changeOrigin: true },
        "/ws": { target: wsTarget, ws: true },
      },
    },
  };
});
