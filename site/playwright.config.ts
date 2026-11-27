// Seam 2: build the site from fixture site-data, serve it the way Cloudflare Pages does
// (wrangler pages dev), and drive it at phone and desktop widths.
import path from "node:path";
import { defineConfig } from "@playwright/test";

const PORT = 8788;

export default defineConfig({
  testDir: "tests",
  outputDir: "test-results/artifacts",
  fullyParallel: true,
  reporter: [["list"]],
  use: { baseURL: `http://127.0.0.1:${PORT}` },
  projects: [
    { name: "phone", use: { browserName: "chromium", viewport: { width: 375, height: 812 }, isMobile: true, hasTouch: true } },
    { name: "desktop", use: { browserName: "chromium", viewport: { width: 1280, height: 800 } } },
  ],
  webServer: {
    command: `npx astro build && npx wrangler pages dev dist --ip 127.0.0.1 --port ${PORT}`,
    url: `http://127.0.0.1:${PORT}`,
    reuseExistingServer: false,
    timeout: 180_000,
    env: {
      // Invented fixture data from the site-data contract (ADR-0007)
      SITE_DATA_DIR: path.resolve(import.meta.dirname, "../contract/examples"),
      WRANGLER_SEND_METRICS: "false",
    },
  },
});
