// Home: the trophy shelf (#6). Expected values come from the invented fixture document
// (contract/examples/trophy-shelf.json) the site is built from.
import fs from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";

const SHELF = JSON.parse(
  fs.readFileSync(path.resolve(import.meta.dirname, "../../contract/examples/trophy-shelf.json"), "utf-8"),
).owners as {
  owner: { name: string };
  currentTeamName: string;
  titles: number[];
  runnerUps: number[];
  firstSeason: number;
  lastSeason: number;
  isFormer: boolean;
}[];
const years = (first: number, last: number) => (first === last ? String(first) : `${first}–${last}`);

test("Home shows every Owner on the trophy shelf, ordered by titles then runner-ups", async ({ page }) => {
  await page.goto("/");
  const shelf = page.getByRole("region", { name: "Trophy shelf" });
  const plaques = shelf.getByRole("listitem").filter({ has: page.getByRole("heading") });
  await expect(plaques.getByRole("heading")).toHaveText(SHELF.map((e) => e.owner.name));

  for (const [i, e] of SHELF.entries()) {
    const plaque = plaques.nth(i);
    await expect(plaque).toContainText(e.currentTeamName);
    const titles = plaque.getByRole("list", { name: "Titles" }).getByRole("listitem");
    await expect(titles).toHaveText(e.titles.map(String));
    const runnerUps = plaque.getByRole("list", { name: "Runner-up finishes" }).getByRole("listitem");
    await expect(runnerUps).toHaveText(e.runnerUps.map(String));
    if (e.isFormer) {
      await expect(plaque).toContainText("Former");
      await expect(plaque).toContainText(years(e.firstSeason, e.lastSeason));
    } else {
      await expect(plaque).not.toContainText("Former");
    }
  }
});

test("the trophy shelf fits the screen", async ({ page }, info) => {
  await page.goto("/");
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
  const shots = path.resolve(import.meta.dirname, "../test-results/screenshots", info.project.name);
  await page
    .getByRole("region", { name: "Trophy shelf" })
    .screenshot({ path: path.join(shots, "trophy-shelf.png"), style: "header { position: static !important; }" });
});
