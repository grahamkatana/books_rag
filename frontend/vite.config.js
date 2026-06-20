import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      // Lets the frontend call relative "/api/..." paths in dev without
      // hitting CORS at all, even though the Flask side already allows
      // it via flask-cors. Point this at wherever your API actually runs.
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
