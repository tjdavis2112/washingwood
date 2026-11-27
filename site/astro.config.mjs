// Static Astro build (ADR-0006): every page is rendered at build time from site-data JSON.
import react from "@astrojs/react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "astro/config";
import { fileURLToPath } from "node:url";

// Absolute path, so the build works from any working directory
const SCHEMA_PATH = fileURLToPath(new URL("../contract/site-data.schema.json", import.meta.url));

export default defineConfig({
  output: "static",
  trailingSlash: "ignore",
  integrations: [react()],
  vite: { plugins: [tailwindcss()], define: { __SITE_DATA_SCHEMA__: JSON.stringify(SCHEMA_PATH) } },
});
