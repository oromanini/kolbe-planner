import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  // VITE_ is the canonical prefix. REACT_APP_ stays exposed so deploys that
  // still pass REACT_APP_BACKEND_URL keep working without changes.
  envPrefix: ["VITE_", "REACT_APP_"],
  server: {
    host: true,
    port: 3000,
  },
  preview: {
    host: true,
    port: 3000,
  },
  build: {
    outDir: "dist",
    sourcemap: false,
  },
});
