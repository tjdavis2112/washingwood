import path from "node:path";
import { expect, test } from "@playwright/test";
import { ALL_PAGES } from "./pages";

const SHOTS = path.resolve(import.meta.dirname, "../test-results/screenshots");

for (const url of [...ALL_PAGES, "/no-such-page/"]) {
  test(`layout of ${url}`, async ({ page, baseURL }, info) => {
    const offsite: string[] = [];
    page.on("request", (req) => {
      if (!req.url().startsWith(baseURL!) && !req.url().startsWith("data:")) offsite.push(req.url());
    });

    await page.goto(url, { waitUntil: "networkidle" });

    // No sideways page scroll: wide content must scroll inside its own container
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow, "page is wider than the viewport").toBeLessThanOrEqual(0);

    // Static site: nothing is fetched from third parties at runtime
    expect(offsite).toEqual([]);

    // No team logos anywhere
    await expect(page.locator('img[src*="logo" i], img[alt*="logo" i], img[src*="espncdn" i]')).toHaveCount(0);

    // Saved for human review (gitignored): test-results/screenshots/<phone|desktop>/<page>.png
    const name = url === "/" ? "home" : url.replace(/^\/|\/$/g, "").replace(/\//g, "-");
    await page.screenshot({ path: path.join(SHOTS, info.project.name, `${name}.png`), fullPage: true });
  });
}
