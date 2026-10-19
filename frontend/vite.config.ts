/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  // GitHub Pages serves the site from /Rebuildr/, not the domain root.
  // Set GITHUB_PAGES=1 in the deploy workflow; local dev/build stays at "/".
  base: process.env.GITHUB_PAGES ? "/Rebuildr/" : "/",
  plugins: [react()],
  server: { port: 5173 },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    env: { VITE_SUPABASE_URL: "http://localhost:54321", VITE_SUPABASE_ANON_KEY: "test-anon-key" },
  },
});
