// The Season page's Transactions tab (#64): that Season's trades as cards, newest Week first, then its top
// 10 Pickups. Expected values come from the invented fixture (contract/examples/transactions.json).
import fs from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";

const EXAMPLES = path.resolve(import.meta.dirname, "../../contract/examples");
const SHOTS = path.resolve(import.meta.dirname, "../test-results/screenshots");
const doc = JSON.parse(fs.readFileSync(path.join(EXAMPLES, "transactions.json"), "utf-8"));
const pts = (n: number) => n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
type Trade = { year: number; week: number; sides: { owner: { name: string } }[] };

for (const { year, pickups } of doc.seasonPickups as { year: number; pickups: Record<string, any>[] }[]) {
  const trades = (doc.trades as Trade[]).filter((t) => t.year === year);

  test(`${year}: #transactions opens the tab with the Season's trades, then its best Pickups`, async ({ page }, info) => {
    await page.goto(`/seasons/${year}/#transactions`);
    await expect(page.getByRole("tab", { name: "Transactions" })).toHaveAttribute("aria-selected", "true");
    const panel = page.getByRole("tabpanel", { name: "Transactions" });
    await expect(panel).toBeVisible();
    await expect(panel).not.toContainText("Coming soon");

    const cards = panel.getByTestId("trade-card");
    await expect(cards).toHaveCount(trades.length);
    for (const [i, t] of trades.entries()) {
      await expect(cards.nth(i)).toHaveAttribute("data-week", String(t.week));
      for (const side of t.sides) await expect(cards.nth(i).getByTestId("trade-side").getByRole("link", { name: side.owner.name })).toBeVisible();
    }
    const weeks = trades.map((t) => t.week);
    expect(weeks).toEqual([...weeks].sort((a, b) => b - a));
    if (trades.length === 0) await expect(panel.getByTestId("no-trades")).toHaveText(`No trades in ${year}.`);
    else await expect(panel.getByTestId("no-trades")).toHaveCount(0);

    const rows = panel.getByTestId("pickup-row");
    await expect(rows).toHaveCount(pickups.length);
    for (const [i, p] of pickups.entries()) {
      await expect(rows.nth(i)).toContainText(`Week ${p.week}`);
      await expect(rows.nth(i)).toContainText(p.name);
      await expect(rows.nth(i).getByRole("link", { name: p.owner.name })).toHaveAttribute("href", `/owners/${p.owner.slug}/`);
      await expect(rows.nth(i)).toContainText(pts(p.points));
    }

    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow, "page is wider than the viewport").toBeLessThanOrEqual(0);
    await page.screenshot({ path: path.join(SHOTS, `season-${year}-transactions-${info.project.name}.png`), fullPage: true });
  });
}

test("the example has a Season with no trades, so the empty line is covered", () => {
  const withTrades = new Set((doc.trades as Trade[]).map((t) => t.year));
  expect(doc.seasonPickups.some((s: { year: number }) => !withTrades.has(s.year))).toBe(true);
});
