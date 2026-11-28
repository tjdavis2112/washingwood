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

  // The full list, by Season (the Fleeced cards repeat 5 of these at the top)
  const cards = page.getByTestId("trade-season").getByTestId("trade-card");
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
  await expect(page.getByTestId("trade-season").locator('[data-testid="trade-side"][data-outcome="won"].border-brand')).toHaveCount(
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

// --- Fleeced and leaderboards (#66) ---

const { tradeRecords, activity } = JSON.parse(fs.readFileSync(path.join(EXAMPLES, "transactions.json"), "utf-8"));
type FTrade = { year: number; week: number; margin: number; fleeced: boolean; sides: { owner: { name: string } }[] };
const fleeced = (trades as FTrade[]).filter((t) => t.fleeced).sort((a, b) => b.margin - a.margin || a.year - b.year || a.week - b.week);
const GOLD = "rgb(212, 175, 55)";
const signed = (n: number) => (n > 0 ? `+${pts(n)}` : n < 0 ? `−${pts(-n)}` : pts(0));

test("the page runs Fleeced, Best pickups, Trade record, Most active, then every trade", async ({ page }) => {
  await page.goto("/transactions/");
  const order = await page.locator("[data-section]").evaluateAll((els) => els.map((e) => e.getAttribute("data-section")));
  expect(order).toEqual(["fleeced", "best-pickups", "trade-records", "most-active", "trades"]);
});

test("the 5 Fleeced cards lead, largest Margin first, with the label and a gold border", async ({ page }, info) => {
  await page.goto("/transactions/");
  const cards = page.getByTestId("fleeced").getByTestId("trade-card");
  await expect(cards).toHaveCount(fleeced.length);
  expect(fleeced.length).toBe(5);
  for (const [i, t] of fleeced.entries()) {
    const card = cards.nth(i);
    await expect(card).toHaveAttribute("data-year", String(t.year));
    await expect(card.getByTestId("trade-result")).toContainText(`won by ${pts(t.margin)}`);
    await expect(card.getByTestId("fleeced-label")).toHaveText("Fleeced");
    expect(await card.evaluate((el) => getComputedStyle(el).borderTopColor)).toBe(GOLD);
  }
  // Every Fleeced trade is also marked in the full list; no other card is
  await expect(page.getByTestId("trade-season").getByTestId("fleeced-label")).toHaveCount(fleeced.length);
  await page.getByTestId("fleeced").screenshot({ path: path.join(SHOTS, `fleeced-${info.project.name}.png`) });
});

test("the shine plays on hover on desktop only, and never under reduced motion", async ({ page }, info) => {
  // The config runs every test with reduced motion; allow motion here to see the shine
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.goto("/transactions/");
  const card = page.getByTestId("fleeced").getByTestId("trade-card").first();
  const shine = card.getByTestId("fleeced-shine");
  await card.hover();
  const animation = () => shine.evaluate((el) => getComputedStyle(el).animationName);
  const display = () => shine.evaluate((el) => getComputedStyle(el).display);
  if (info.project.name === "phone") {
    expect(await display()).toBe("none");
  } else {
    expect(await animation()).toBe("fleeced-shine");
  }
  await page.emulateMedia({ reducedMotion: "reduce" });
  await card.hover();
  expect(await display()).toBe("none");
});

test("Fleeced trades are marked on their Season tab too", async ({ page }) => {
  const years = [...new Set(fleeced.map((t) => t.year))];
  for (const y of years) {
    await page.goto(`/seasons/${y}/#transactions`);
    await expect(page.getByRole("tabpanel", { name: "Transactions" }).getByTestId("fleeced-label")).toHaveCount(
      fleeced.filter((t) => t.year === y).length,
    );
  }
});

test("Trade record and Most active list every Owner's numbers and fit the page", async ({ page }, info) => {
  await page.goto("/transactions/");
  const rec = page.getByTestId("trade-record-row");
  await expect(rec).toHaveCount(tradeRecords.length);
  for (const [i, r] of tradeRecords.entries()) {
    await expect(rec.nth(i).getByRole("link", { name: r.owner.name })).toHaveAttribute("href", `/owners/${r.owner.slug}/`);
    await expect(rec.nth(i)).toContainText(`${r.won}-${r.lost}-${r.tied}`);
    await expect(rec.nth(i)).toContainText(signed(r.netPoints));
  }
  const act = page.getByTestId("activity-row");
  await expect(act).toHaveCount(activity.length);
  for (const [i, a] of activity.entries()) {
    await expect(act.nth(i).getByRole("link", { name: a.owner.name })).toBeVisible();
    await expect(act.nth(i).getByTestId("activity-trades")).toHaveText(String(a.trades));
    await expect(act.nth(i).getByTestId("activity-pickups")).toHaveText(String(a.pickups));
  }
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow, "page is wider than the viewport").toBeLessThanOrEqual(0);
  await page.getByTestId("trade-records").screenshot({ path: path.join(SHOTS, `trade-records-${info.project.name}.png`) });
  await page.getByTestId("most-active").screenshot({ path: path.join(SHOTS, `most-active-${info.project.name}.png`) });
});
