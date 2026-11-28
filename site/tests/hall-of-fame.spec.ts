// Hall of Fame (#73): Inductee cards grouped by Season, newest first. Expected values come from the invented
// fixture (contract/examples/hall-of-fame.json).
import fs from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";

const EXAMPLES = path.resolve(import.meta.dirname, "../../contract/examples");
const SHOTS = path.resolve(import.meta.dirname, "../test-results/screenshots");
const { inductees } = JSON.parse(fs.readFileSync(path.join(EXAMPLES, "hall-of-fame.json"), "utf-8"));
const pts = (n: number) => n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

test("the Hall of Fame nav link opens the section, which explains how Players get in", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("navigation").getByRole("link", { name: "Hall of Fame" }).click();
  await expect(page).toHaveURL(/\/hall-of-fame\/$/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Hall of Fame");
  await expect(page.getByText("Coming soon", { exact: true })).toHaveCount(0);
  await expect(page.getByTestId("induction-note")).toContainText("fixed bar");
  await expect(page.getByTestId("induction-note")).toContainText("Points above replacement");
});

test("every Inductee is a gold card, grouped by Season newest first", async ({ page }, info) => {
  await page.goto("/hall-of-fame/");
  const years = [...new Set(inductees.map((i: { year: number }) => i.year))];
  expect(years).toEqual([...years].sort((a, b) => Number(b) - Number(a)));
  const groups = page.getByTestId("inductee-season");
  await expect(groups).toHaveCount(years.length);
  for (const [n, y] of years.entries()) {
    await expect(groups.nth(n)).toHaveAttribute("data-year", String(y));
    await expect(groups.nth(n).getByRole("heading", { level: 2 }).getByRole("link")).toHaveAttribute("href", `/seasons/${y}/`);
  }

  const cards = page.getByTestId("inductee-card");
  await expect(cards).toHaveCount(inductees.length);
  for (const [n, i] of inductees.entries()) {
    const card = cards.nth(n);
    await expect(card).toHaveAttribute("data-year", String(i.year));
    await expect(card.getByRole("link", { name: String(i.year), exact: true })).toHaveAttribute("href", `/seasons/${i.year}/`);
    await expect(card.getByTestId("format-badge")).toHaveText(i.scoringFormat);
    await expect(card.getByTestId("inductee-name")).toHaveText(i.name);
    await expect(card.getByTestId("inductee-position")).toHaveText(i.nflTeam ? `${i.position} · ${i.nflTeam}` : i.position);
    await expect(card.getByRole("link", { name: i.owner.name })).toHaveAttribute("href", `/owners/${i.owner.slug}/`);
    await expect(card).toContainText(i.teamName);
    const lanes = card.getByTestId("inductee-lane");
    await expect(lanes).toHaveCount(i.lanes.length);
    for (const [k, lane] of i.lanes.entries()) {
      await expect(lanes.nth(k)).toHaveAttribute("data-lane", lane.lane);
      await expect(lanes.nth(k)).toContainText("Dominant");
      await expect(lanes.nth(k).getByTestId("lane-value")).toHaveText(`+${pts(lane.value)}`);
    }
    await expect(card.getByTestId("inductee-points")).toHaveText(pts(i.points));
    await expect(card.getByTestId("inductee-finish")).toHaveText(`${i.position}${i.positionalFinish}`);
    // Plain gold border, no effects yet (#77)
    const border = await card.evaluate((el) => getComputedStyle(el).borderTopColor);
    expect(border).toBe("rgb(212, 175, 55)");
  }

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow, "page is wider than the viewport").toBeLessThanOrEqual(0);
  await page.screenshot({ path: path.join(SHOTS, `hall-of-fame-${info.project.name}.png`), fullPage: true });
});

test("every link on the Hall of Fame page resolves", async ({ page }) => {
  await page.goto("/hall-of-fame/");
  const hrefs = await page.locator("main a[href^='/']").evaluateAll((as) => [...new Set(as.map((a) => a.getAttribute("href")!))]);
  expect(hrefs.length).toBeGreaterThan(0);
  for (const href of hrefs) {
    const res = await page.request.get(href);
    expect(res.status(), href).toBe(200);
  }
});
