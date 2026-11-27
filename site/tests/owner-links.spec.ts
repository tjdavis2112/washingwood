// Owner names link to their Owner page everywhere they appear (#17). Section ids come from the
// components; names and slugs from the invented fixture documents.
import { expect, type Page, test } from "@playwright/test";

const PLACES: { page: string; section: string; label: string }[] = [
  { page: "/", section: "#shelf-heading", label: "Home trophy shelf" },
  { page: "/", section: "#champion-heading", label: "Home Champion banner" },
  { page: "/seasons/2020/", section: "#podium-heading", label: "Podium" },
  { page: "/seasons/2020/", section: "#last-place-heading", label: "Last place" },
  { page: "/seasons/2020/", section: "#standings-heading", label: "Final standings" },
  { page: "/seasons/2020/", section: "#bracket-heading", label: "Playoff bracket" },
  { page: "/seasons/2020/", section: "#weekly-heading", label: "Weekly results" },
];

const ownerLinks = (page: Page, headingId: string) =>
  page.locator(`section:has(> ${headingId}), section:has(${headingId})`).first().locator("a[data-owner-link]");

for (const place of PLACES) {
  test(`${place.label}: every Owner name links to its Owner page`, async ({ page }) => {
    await page.goto(place.page);
    const links = ownerLinks(page, place.section);
    const count = await links.count();
    expect(count, "Owner links in this section").toBeGreaterThan(0);

    // Every link points at /owners/<slug>/
    const hrefs = await links.evaluateAll((els) => els.map((a) => a.getAttribute("href")));
    for (const href of hrefs) expect(href).toMatch(/^\/owners\/[a-z0-9]+(-[a-z0-9]+)*\/$/);

    // A sample link opens a real Owner page for that name
    const sample = links.first();
    const name = (await sample.textContent())!.trim();
    await sample.click();
    await expect(page).toHaveURL(/\/owners\/[a-z0-9-]+\/$/);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(name);
  });
}

test("Owner links show a visible focus outline from the keyboard", async ({ page }) => {
  await page.goto("/seasons/2020/");
  const link = ownerLinks(page, "#podium-heading").first();
  await link.focus();
  await expect(link).toBeFocused();
  const outline = await link.evaluate((el) => getComputedStyle(el).outlineStyle);
  expect(outline).not.toBe("none");
});
