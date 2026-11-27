// The Matchups section (#37): championship cards, newest first, each linking to its Season.
// Expected values come from the invented fixture (contract/examples/matchups.json).
import fs from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";

const EXAMPLES = path.resolve(import.meta.dirname, "../../contract/examples");
const SHOTS = path.resolve(import.meta.dirname, "../test-results/screenshots");
const { championships } = JSON.parse(fs.readFileSync(path.join(EXAMPLES, "matchups.json"), "utf-8"));
const pts = (n: number) => n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

test("the Matchups nav link opens the section", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("navigation").getByRole("link", { name: "Matchups" }).click();
  await expect(page).toHaveURL(/\/matchups\/$/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Matchups");
  await expect(page.getByText("Coming soon", { exact: true })).toHaveCount(0);
});

test("every championship has a card, newest first, with both sides and the margin", async ({ page }) => {
  await page.goto("/matchups/");
  const cards = page.getByTestId("championship");
  await expect(cards).toHaveCount(championships.length);
  for (const [i, c] of championships.entries()) {
    const card = cards.nth(i);
    await expect(card).toHaveAttribute("data-year", String(c.year));
    await expect(card.getByRole("link", { name: c.champion.owner.name })).toHaveAttribute("href", `/owners/${c.champion.owner.slug}/`);
    await expect(card.getByRole("link", { name: c.runnerUp.owner.name })).toHaveAttribute("href", `/owners/${c.runnerUp.owner.slug}/`);
    await expect(card).toContainText(`${c.champion.teamName} · seed ${c.champion.seed}`);
    await expect(card).toContainText(pts(c.champion.score));
    await expect(card).toContainText(pts(c.runnerUp.score));
    await expect(card).toContainText(`Won by ${pts(c.margin)}`);
    await expect(card).toContainText(c.weeks.length > 1 ? `Weeks ${c.weeks[0]}–${c.weeks[1]}` : `Week ${c.weeks[0]}`);
  }
});

test("a card's year opens that Season's page", async ({ page }) => {
  await page.goto("/matchups/");
  const year = championships[championships.length - 1].year;
  await page.getByTestId("championship").last().getByRole("link", { name: String(year), exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/seasons/${year}/$`));
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(`${year} Season`);
});

test("the Matchups page fits the screen", async ({ page }, info) => {
  await page.goto("/matchups/");
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow, "page is wider than the viewport").toBeLessThanOrEqual(0);
  await page.screenshot({ path: path.join(SHOTS, info.project.name, "matchups-championships.png"), fullPage: true });
});

// --- Leaderboards (#38) ---

const { leaderboards } = JSON.parse(fs.readFileSync(path.join(EXAMPLES, "matchups.json"), "utf-8"));
const BOARDS = [
  { tab: "Blowouts", id: "blowouts", key: "blowouts", kind: "game" },
  { tab: "Closest games", id: "closest", key: "closestGames", kind: "game" },
  { tab: "Highest scores", id: "highest", key: "highestScores", kind: "score" },
  { tab: "Lowest scores", id: "lowest", key: "lowestScores", kind: "score" },
  { tab: "Playoff upsets", id: "upsets", key: "playoffUpsets", kind: "upset" },
] as const;

for (const b of BOARDS) {
  test(`${b.tab}: the tab lists the example rows in order with a format badge`, async ({ page }) => {
    await page.goto("/matchups/");
    const section = page.getByTestId("leaderboards");
    await section.getByRole("tab", { name: b.tab }).click();
    const rows = section.getByTestId(`board-${b.id}`).getByTestId("leaderboard-row");
    const expected = leaderboards[b.key];
    await expect(rows).toHaveCount(expected.length);
    for (const [i, r] of expected.entries()) {
      const row = rows.nth(i);
      await expect(row).toContainText(String(r.year));
      await expect(row.getByTestId("format-badge")).toHaveText(r.scoringFormat);
      if (b.kind === "score") {
        await expect(row).toContainText(pts(r.team.score));
        await expect(row.getByRole("link", { name: r.team.owner.name, exact: true })).toBeVisible();
      } else {
        await expect(row).toContainText(`${pts(r.winner.score)}–${pts(r.loser.score)}`);
        await expect(row).toContainText(b.kind === "upset" ? String(r.seedGap) : pts(r.margin));
        await expect(row.getByRole("link", { name: r.winner.owner.name, exact: true })).toBeVisible();
      }
    }
  });
}

test("leaderboard tables fit the page and scroll inside their own box", async ({ page }, info) => {
  await page.goto("/matchups/#highest");
  await expect(page.getByTestId("board-highest")).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow, "page is wider than the viewport").toBeLessThanOrEqual(0);
  await page.screenshot({ path: path.join(SHOTS, info.project.name, "matchups-leaderboards.png"), fullPage: true });
});
