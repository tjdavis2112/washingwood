// The Draft section (#27): every Season's first round, newest first, each linking to its board.
// Expected values come from the invented fixture (contract/examples/draft.json).
import fs from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";

const EXAMPLES = path.resolve(import.meta.dirname, "../../contract/examples");
const SHOTS = path.resolve(import.meta.dirname, "../test-results/screenshots");
type Pick = {
  overall: number;
  owner: { slug: string; name: string };
  teamName: string;
  player: { name: string; position: string; nflTeam: string | null } | null;
};
const history = JSON.parse(fs.readFileSync(path.join(EXAMPLES, "draft.json"), "utf-8")).seasons as {
  year: number;
  teamCount: number;
  type: string;
  firstRound: Pick[];
}[];

test("the Draft nav link opens the first-round history", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("navigation").getByRole("link", { name: "Draft" }).click();
  await expect(page).toHaveURL(/\/draft\/$/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Draft");
  await expect(page.getByText("Coming soon", { exact: true })).toHaveCount(0);
});

test("every Season's first round is listed newest first with Player and Owner", async ({ page }, info) => {
  await page.goto("/draft/");
  const isPhone = info.project.name === "phone";
  const seasons = page.getByTestId(isPhone ? "first-round-season" : "first-round-row");
  await expect(seasons).toHaveCount(history.length);
  for (const [i, s] of history.entries()) {
    const row = seasons.nth(i);
    await expect(row).toHaveAttribute("data-year", String(s.year));
    const picks = row.getByTestId(isPhone ? "first-round-row-item" : "first-round-cell");
    await expect(picks).toHaveCount(s.teamCount);
    for (const [j, p] of s.firstRound.entries()) {
      await expect(picks.nth(j)).toContainText(p.player ? p.player.name : "Not recorded");
      if (p.player) await expect(picks.nth(j)).toContainText(p.player.position);
      await expect(picks.nth(j).getByRole("link", { name: p.owner.name })).toHaveAttribute(
        "href",
        `/owners/${p.owner.slug}/`,
      );
    }
  }
});

test("a Season opens its full draft board", async ({ page }) => {
  await page.goto("/draft/");
  const year = history[history.length - 1].year;
  await page.getByRole("link", { name: String(year), exact: true }).filter({ visible: true }).click();
  await expect(page).toHaveURL(new RegExp(`/seasons/${year}/#draft$`));
  await expect(page.getByRole("tabpanel", { name: "Draft" })).toBeVisible();
});

test("the first-round history fits the page", async ({ page }, info) => {
  await page.goto("/draft/");
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow, "page is wider than the viewport").toBeLessThanOrEqual(0);
  await page.screenshot({ path: path.join(SHOTS, info.project.name, "draft-first-rounds.png"), fullPage: true });
});
