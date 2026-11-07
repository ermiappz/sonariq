import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@design": fileURLToPath(new URL("../design", import.meta.url)) } },
  server: {
    port: 5173,
    fs: { allow: [".."] },
    proxy: { "/api": { target: process.env.SQ_API ?? "http://127.0.0.1:8765", rewrite: (p) => p.replace(/^\/api/, "") } },
  },
});
