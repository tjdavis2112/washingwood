// Seam 2: build the site from fixture site-data, serve it the way Cloudflare Pages does
// (wrangler pages dev, with the passphrase middleware), and drive it at phone and desktop widths.
import path from "node:path";
import { defineConfig } from "@playwright/test";
import { AUTH_STATE, PASSPHRASE, PORT, SESSION_KEY } from "./tests/gate-config";

const phone = { browserName: "chromium" as const, viewport: { width: 375, height: 812 }, isMobile: true, hasTouch: true };
const desktop = { browserName: "chromium" as const, viewport: { width: 1280, height: 800 } };

export default defineConfig({
  testDir: "tests",
  outputDir: "test-results/artifacts",
  fullyParallel: true,
  reporter: [["list"]],
  // Reduced motion: screenshots show settled pages, not a page transition caught mid-fade
  use: { baseURL: `http://127.0.0.1:${PORT}`, contextOptions: { reducedMotion: "reduce" } },
  projects: [
    // Signs in once through the real landing form; the other projects reuse its cookie
    { name: "auth", testMatch: /auth\.setup\.ts/ },
    { name: "phone", use: { ...phone, storageState: AUTH_STATE }, dependencies: ["auth"] },
    { name: "desktop", use: { ...desktop, storageState: AUTH_STATE }, dependencies: ["auth"] },
  ],
  webServer: {
    command: `npx astro build && npx wrangler pages dev dist --ip 127.0.0.1 --port ${PORT} --binding "SITE_PASSPHRASE=${PASSPHRASE}" --binding "SESSION_KEY=${SESSION_KEY}"`,
    url: `http://127.0.0.1:${PORT}/robots.txt`,
    reuseExistingServer: false,
    timeout: 180_000,
    env: {
      // Invented fixture data from the site-data contract (ADR-0007)
      SITE_DATA_DIR: path.resolve(import.meta.dirname, "../contract/examples"),
      WRANGLER_SEND_METRICS: "false",
    },
  },
});
