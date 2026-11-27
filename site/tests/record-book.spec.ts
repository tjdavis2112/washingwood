// The Record Book (#50): Last place history and tally. Expected values come from the invented
// fixture (contract/examples/record-book.json).
import fs from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";

const EXAMPLES = path.resolve(import.meta.dirname, "../../contract/examples");
const SHOTS = path.resolve(import.meta.dirname, "../test-results/screenshots");
const { lastPlace } = JSON.parse(fs.readFileSync(path.join(EXAMPLES, "record-book.json"), "utf-8"));
const pts = (n: number) => n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const rec = (r: { wins: number; losses: number; ties: number }) => (r.ties ? `${r.wins}-${r.losses}-${r.ties}` : `${r.wins}-${r.losses}`);

test("the Record Book nav link opens the section, with the rule-change note", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("navigation").getByRole("link", { name: "Record Book" }).click();
  await expect(page).toHaveURL(/\/record-book\/$/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Record Book");
  await expect(page.getByText("Coming soon", { exact: true })).toHaveCount(0);
  await expect(page.getByTestId("rule-change-note")).toContainText("2020");
  await expect(page.getByTestId("rule-change-note")).toContainText("second FLEX");
  for (const name of ["Week", "Season", "All-time", "Streaks", "Last place"]) {
    await expect(page.getByRole("tab", { name, exact: true })).toBeVisible();
  }
});

test("#last-place opens the tab with every Season's Last place, newest first", async ({ page }) => {
  await page.goto("/record-book/#last-place");
  const tab = page.getByRole("tab", { name: "Last place" });
  await expect(tab).toHaveAttribute("aria-selected", "true");
  // On a phone the tab strip scrolls; the linked tab is scrolled fully into view
  const box = (await tab.boundingBox())!;
  expect(box.x + box.width).toBeLessThanOrEqual(page.viewportSize()!.width);
  const rows = page.getByTestId("last-place-row");
  await expect(rows).toHaveCount(lastPlace.seasons.length);
  for (const [i, r] of lastPlace.seasons.entries()) {
    const row = rows.nth(i);
    await expect(row).toHaveAttribute("data-year", String(r.year));
    await expect(row.getByRole("link", { name: String(r.year), exact: true })).toHaveAttribute("href", `/seasons/${r.year}/`);
    await expect(row.getByRole("link", { name: r.owner.name })).toHaveAttribute("href", `/owners/${r.owner.slug}/`);
    await expect(row).toContainText(r.teamName);
    await expect(row).toContainText(rec(r.record));
    await expect(row).toContainText(pts(r.pointsFor));
    await expect(row.getByTestId("format-badge")).toHaveText(r.scoringFormat);
  }
  const tally = page.getByTestId("tally-row");
  await expect(tally).toHaveCount(lastPlace.tally.length);
  for (const [i, t] of lastPlace.tally.entries()) {
    await expect(tally.nth(i).getByRole("link", { name: t.owner.name })).toBeVisible();
    await expect(tally.nth(i)).toContainText(t.years.join(", "));
    await expect(tally.nth(i)).toContainText(String(t.count));
  }
});

test("the Punishment link opens that Season's popup", async ({ page }) => {
  const r = lastPlace.seasons[0];
  await page.goto("/record-book/#last-place");
  await page.getByTestId("last-place-row").first().getByTestId("punishment-link").click();
  await expect(page).toHaveURL(new RegExp(`/seasons/${r.year}/#punishment-${r.year}$`));
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText(`${r.year} · ${r.owner.name}`);
});

test("the tally sits beside the table on desktop and below it on a phone", async ({ page }, info) => {
  await page.goto("/record-book/#last-place");
  const table = await page.getByRole("table", { name: "Last place by Season" }).boundingBox();
  const tally = await page.getByTestId("last-place-tally").boundingBox();
  if (info.project.name === "desktop") expect(tally!.x).toBeGreaterThan(table!.x + table!.width - 1);
  else expect(tally!.y).toBeGreaterThanOrEqual(table!.y + table!.height);
});

test("the Record Book fits the screen", async ({ page }, info) => {
  await page.goto("/record-book/#last-place");
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow, "page is wider than the viewport").toBeLessThanOrEqual(0);
  await page.screenshot({ path: path.join(SHOTS, info.project.name, "record-book-last-place.png"), fullPage: true });
});
