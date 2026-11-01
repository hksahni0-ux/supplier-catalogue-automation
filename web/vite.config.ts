import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// In development the page runs on :5173 and calls the Python API on :8000.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://127.0.0.1:8000", "/auth": "http://127.0.0.1:8000" } },
  test: { environment: "jsdom", globals: true, setupFiles: ["./src/setupTests.ts"] },
});
