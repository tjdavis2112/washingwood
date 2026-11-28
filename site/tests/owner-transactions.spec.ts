// The Owner page's Transactions tab (#65): the Owner's trade record and net points, their trades as cards
// (newest first) and their top 5 Pickups. Expected values come from contract/examples/transactions.json.
import fs from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";

const EXAMPLES = path.resolve(import.meta.dirname, "../../contract/examples");
const SHOTS = path.resolve(import.meta.dirname, "../test-results/screenshots");
const doc = JSON.parse(fs.readFileSync(path.join(EXAMPLES, "transactions.json"), "utf-8"));
const pts = (n: number) => n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const signed = (n: number) => (n > 0 ? `+${pts(n)}` : n < 0 ? `−${pts(-n)}` : pts(0));
type Trade = { year: number; week: number; sides: { owner: { slug: string; name: string } }[] };

// Quinn Harrow has a trade and a Pickup; Wren Solano (a former Owner) has a Pickup and no trades
for (const slug of ["quinn-harrow", "wren-solano"]) {
  const trades = (doc.trades as Trade[]).filter((t) => t.sides.some((s) => s.owner.slug === slug));
  const record = doc.tradeRecords.find((r: { owner: { slug: string } }) => r.owner.slug === slug);
  const pickups = doc.ownerPickups.find((e: { owner: { slug: string } }) => e.owner.slug === slug).pickups;

  test(`${slug}: #transactions opens the tab with the trade record, trades and best Pickups`, async ({ page }, info) => {
    await page.goto(`/owners/${slug}/#transactions`);
    await expect(page.getByRole("tab", { name: "Transactions" })).toHaveAttribute("aria-selected", "true");
    const panel = page.getByRole("tabpanel", { name: "Transactions" });
    await expect(panel).toBeVisible();
    await expect(panel).not.toContainText("Coming soon");

    if (record) {
      const summary = panel.getByTestId("trade-record");
      await expect(summary.getByTestId("trade-record-wlt")).toHaveText(`${record.won}-${record.lost}-${record.tied}`);
      await expect(summary.getByTestId("trade-record-net")).toHaveText(signed(record.netPoints));
      await expect(panel.getByTestId("no-trades")).toHaveCount(0);
    } else {
      await expect(panel.getByTestId("trade-record")).toHaveCount(0);
      await expect(panel.getByTestId("no-trades")).toHaveText("No trades yet.");
    }

    const cards = panel.getByTestId("trade-card");
    await expect(cards).toHaveCount(trades.length);
    for (const [i, t] of trades.entries()) {
      await expect(cards.nth(i)).toHaveAttribute("data-year", String(t.year));
      await expect(cards.nth(i)).toHaveAttribute("data-week", String(t.week));
    }

    const rows = panel.getByTestId("pickup-row");
    await expect(rows).toHaveCount(pickups.length);
    for (const [i, p] of pickups.entries()) {
      await expect(rows.nth(i)).toContainText(p.name);
      await expect(rows.nth(i).getByRole("link", { name: String(p.year), exact: true })).toHaveAttribute("href", `/seasons/${p.year}/`);
      await expect(rows.nth(i)).toContainText(pts(p.points));
    }

    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow, "page is wider than the viewport").toBeLessThanOrEqual(0);
    await page.screenshot({ path: path.join(SHOTS, `owner-${slug}-transactions-${info.project.name}.png`), fullPage: true });
  });
}
