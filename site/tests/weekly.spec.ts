// Season page: weekly results (#10). Expected values come from the invented fixture documents
// the site is built from (2018 has a tie; 2020 has byes).
import fs from "node:fs";
import path from "node:path";
import { expect, type Locator, test } from "@playwright/test";

const EXAMPLES = path.resolve(import.meta.dirname, "../../contract/examples");
const seasonDoc = (year: number) =>
  JSON.parse(fs.readFileSync(path.join(EXAMPLES, "seasons", `${year}.json`), "utf-8"));
const points = (n: number) => n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const weeksLabel = (w: number[]) => (w.length > 1 ? `Weeks ${w[0]}–${w[w.length - 1]}` : `Week ${w[0]}`);

type Side = { owner: { name: string }; score: number | null };
type Matchup = { home: Side; away: Side | null; winner: "home" | "away" | null; isTie: boolean; isBye: boolean };

async function expectMatchup(item: Locator, m: Matchup) {
  const home = item.getByTestId("weekly-side").filter({ hasText: m.home.owner.name });
  if (m.isBye) {
    await expect(item).toContainText("Bye");
    await expect(item.getByTestId("weekly-side")).toHaveCount(1);
    return;
  }
  const away = item.getByTestId("weekly-side").filter({ hasText: m.away!.owner.name });
  await expect(home).toContainText(points(m.home.score!));
  await expect(away).toContainText(points(m.away!.score!));
  if (m.isTie) {
    await expect(item).toContainText("Tie");
    await expect(item).not.toContainText("Winner");
    return;
  }
  const [winner, loser] = m.winner === "home" ? [home, away] : [away, home];
  await expect(winner).toContainText("Winner");
  await expect(loser).not.toContainText("Winner");
}

for (const year of [2018, 2020]) {
  const { weeklyResults } = seasonDoc(year);

  test(`${year}: weekly results show every Matchup period with every Matchup`, async ({ page }) => {
    await page.goto(`/seasons/${year}/`);
    const region = page.getByRole("region", { name: "Weekly results" });
    await expect(region.getByRole("heading", { level: 3 })).toHaveText(
      weeklyResults.map((p: { weeks: number[] }) => weeksLabel(p.weeks)),
    );
    for (const period of weeklyResults) {
      const items = region.getByRole("group", { name: weeksLabel(period.weeks), exact: true }).getByRole("listitem");
      await expect(items).toHaveCount(period.matchups.length);
      for (const [i, m] of period.matchups.entries()) await expectMatchup(items.nth(i), m);
    }
  });
}

test("ties and byes are labelled", async ({ page }) => {
  await page.goto("/seasons/2018/");
  const region = page.getByRole("region", { name: "Weekly results" });
  await expect(region.getByRole("listitem").filter({ hasText: "Tie" })).toHaveCount(1);

  await page.goto("/seasons/2020/");
  const byes = page.getByRole("region", { name: "Weekly results" }).getByRole("listitem").filter({ hasText: "Bye" });
  await expect(byes).toHaveCount(2);
});

test("the weekly grid scrolls inside its own box on phones and uses the full width on desktop", async ({ page }, info) => {
  await page.goto("/seasons/2020/");
  const grid = page.getByTestId("weekly-grid");
  const [scrollW, clientW] = await grid.evaluate((el) => [el.scrollWidth, el.clientWidth]);
  const pageOverflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(pageOverflow).toBeLessThanOrEqual(0);

  const region = page.getByRole("region", { name: "Weekly results" });
  const [w1, w2] = [await region.getByRole("group").nth(0).boundingBox(), await region.getByRole("group").nth(1).boundingBox()];
  if (info.project.name === "phone") {
    expect(scrollW).toBeGreaterThan(clientW); // sideways scroll inside the grid
    expect(w2!.x).toBeGreaterThan(w1!.x); // Weeks run left to right
  } else {
    expect(scrollW).toBeLessThanOrEqual(clientW); // no sideways scroll: Weeks wrap
    expect(w2!.y).toBeCloseTo(w1!.y, 0); // several Weeks per row
    const gridBox = (await grid.boundingBox())!;
    expect(gridBox.width).toBeGreaterThan(page.viewportSize()!.width * 0.8);
  }

  const shots = path.resolve(import.meta.dirname, "../test-results/screenshots", info.project.name);
  await region.screenshot({
    path: path.join(shots, "weekly-2020.png"),
    style: "header { position: static !important; }",
  });
});
