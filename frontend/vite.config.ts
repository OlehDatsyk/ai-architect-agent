import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { loadEnv } from "vite";
import { defineConfig } from "vitest/config";

// The repository root holds the single .env file shared with the backend.
const ENV_DIR = "..";

export default defineConfig(({ mode }) => {
  // Empty prefix loads every variable, but only inside this Node-side config.
  // Nothing here is exposed to the browser bundle (only VITE_* would be).
  const env = loadEnv(mode, ENV_DIR, "");
  const backendUrl = env.BACKEND_URL || "http://127.0.0.1:8000";

  return {
    envDir: ENV_DIR,
    plugins: [react(), tailwindcss()],
    server: {
      port: 5173,
      proxy: { "/api": { target: backendUrl, changeOrigin: true } },
    },
    preview: {
      port: 4173,
      proxy: { "/api": { target: backendUrl, changeOrigin: true } },
    },
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: ["./src/test/setup.ts"],
      css: false,
    },
  };
});
