// Transactions (#62): every trade as a card, grouped by Season, newest first. Expected values come from
// the invented fixture (contract/examples/transactions.json).
import fs from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";

const EXAMPLES = path.resolve(import.meta.dirname, "../../contract/examples");
const SHOTS = path.resolve(import.meta.dirname, "../test-results/screenshots");
const { trades, pickups } = JSON.parse(fs.readFileSync(path.join(EXAMPLES, "transactions.json"), "utf-8"));
const pts = (n: number) => n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

test("the Transactions nav link opens the section", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("navigation").getByRole("link", { name: "Transactions" }).click();
  await expect(page).toHaveURL(/\/transactions\/$/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Transactions");
  await expect(page.getByText("Coming soon", { exact: true })).toHaveCount(0);
});

test("every trade is a card, grouped by Season newest first, with both sides and the result", async ({ page }, info) => {
  await page.goto("/transactions/");
  const years = [...new Set(trades.map((t: { year: number }) => t.year))];
  const groups = page.getByTestId("trade-season");
  await expect(groups).toHaveCount(years.length);
  for (const [i, y] of years.entries()) {
    await expect(groups.nth(i)).toHaveAttribute("data-year", String(y));
    await expect(groups.nth(i).getByRole("heading", { level: 3 }).getByRole("link")).toHaveAttribute("href", `/seasons/${y}/`);
  }

  const cards = page.getByTestId("trade-card");
  await expect(cards).toHaveCount(trades.length);
  for (const [i, t] of trades.entries()) {
    const card = cards.nth(i);
    await expect(card).toHaveAttribute("data-year", String(t.year));
    await expect(card).toContainText(`Week ${t.week}`);
    const result = card.getByTestId("trade-result");
    if (t.sides[0].outcome === "tied") await expect(result).toHaveText("Tied");
    else await expect(result).toHaveText(`${t.sides[0].owner.name} won by ${pts(t.margin)}`);

    const sides = card.getByTestId("trade-side");
    await expect(sides).toHaveCount(2);
    for (const [j, s] of t.sides.entries()) {
      const side = sides.nth(j);
      await expect(side).toHaveAttribute("data-outcome", s.outcome);
      await expect(side.getByRole("link", { name: s.owner.name })).toHaveAttribute("href", `/owners/${s.owner.slug}/`);
      await expect(side).toContainText(s.teamName);
      await expect(side.getByTestId("side-total")).toHaveText(pts(s.total));
      const players = side.getByTestId("traded-player");
      await expect(players).toHaveCount(s.players.length);
      for (const [k, p] of s.players.entries()) {
        await expect(players.nth(k)).toContainText(p.name);
        await expect(players.nth(k)).toContainText(p.position);
        if (p.nflTeam) await expect(players.nth(k)).toContainText(p.nflTeam);
        await expect(players.nth(k)).toContainText(pts(p.points));
        await expect(players.nth(k)).toContainText(`${p.weeksStarted} start`);
      }
    }
  }
  // Only the winning side is highlighted
  await expect(page.locator('[data-testid="trade-side"][data-outcome="won"].border-brand')).toHaveCount(
    trades.filter((t: { sides: { outcome: string }[] }) => t.sides[0].outcome === "won").length,
  );
  await page.screenshot({ path: path.join(SHOTS, `transactions-${info.project.name}.png`), fullPage: true });
});

test("every link on the Transactions page resolves", async ({ page }) => {
  await page.goto("/transactions/");
  const hrefs = await page.locator("main a[href^='/']").evaluateAll((as) => [...new Set(as.map((a) => a.getAttribute("href")!))]);
  expect(hrefs.length).toBeGreaterThan(0);
  for (const href of hrefs) {
    const res = await page.request.get(href);
    expect(res.status(), href).toBe(200);
  }
});

test("Best pickups lists the top 10 with Owner, Season, Week, points and a Format badge", async ({ page }, info) => {
  await page.goto("/transactions/");
  const board = page.getByTestId("best-pickups");
  await expect(board.getByRole("heading", { level: 2 })).toHaveText("Best pickups");
  await expect(board).toContainText("formats differ");
  const rows = board.getByTestId("pickup-row");
  await expect(rows).toHaveCount(pickups.length);
  for (const [i, p] of pickups.entries()) {
    const row = rows.nth(i);
    await expect(row.getByRole("link", { name: String(p.year), exact: true })).toHaveAttribute("href", `/seasons/${p.year}/`);
    await expect(row).toContainText(`Week ${p.week}`);
    await expect(row).toContainText(p.name);
    await expect(row).toContainText(p.position);
    await expect(row.getByTestId("pickup-via")).toHaveText(p.via === "waiver" ? "via waivers" : "free agent");
    await expect(row.getByRole("link", { name: p.owner.name })).toHaveAttribute("href", `/owners/${p.owner.slug}/`);
    await expect(row).toContainText(p.teamName);
    await expect(row).toContainText(pts(p.points));
    await expect(row).toContainText(`${p.weeksStarted} start`);
    await expect(row.getByTestId("format-badge")).toHaveText(p.scoringFormat);
  }
  // The table scrolls inside its own box; the page never scrolls sideways
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow, "page is wider than the viewport").toBeLessThanOrEqual(0);
  await board.screenshot({ path: path.join(SHOTS, `best-pickups-${info.project.name}.png`) });
});
