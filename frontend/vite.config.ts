import { fileURLToPath, URL } from "node:url";
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

const repoRoot = fileURLToPath(new URL("../..", import.meta.url));

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, repoRoot, "");
  const smallModel = env.VITE_SMALL_MODEL || env.SMALL_MODEL || "";
  const largeModel = env.VITE_LARGE_MODEL || env.LARGE_MODEL || "";

  return {
    envDir: repoRoot,
    define: {
      "import.meta.env.VITE_SMALL_MODEL": JSON.stringify(smallModel),
      "import.meta.env.VITE_LARGE_MODEL": JSON.stringify(largeModel),
    },
    plugins: [react(), tailwindcss()],
    server: {
      host: "0.0.0.0",
      proxy: {
        "/api": {
          target: "http://localhost:2024",
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, ""),
          ws: true,
        },
      },
    },
  };
});
