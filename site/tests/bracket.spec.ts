// Season page: the playoff bracket (#9). Expected values come from the invented fixture
// documents the site is built from.
import fs from "node:fs";
import path from "node:path";
import { expect, type Locator, test } from "@playwright/test";

const EXAMPLES = path.resolve(import.meta.dirname, "../../contract/examples");
const seasonDoc = (year: number) =>
  JSON.parse(fs.readFileSync(path.join(EXAMPLES, "seasons", `${year}.json`), "utf-8"));
const points = (n: number) => n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const weeksNote = (w: number[]) => (w.length > 1 ? `Weeks ${w[0]}–${w[w.length - 1]}` : `Week ${w[0]}`);

type Side = { seed: number; owner: { name: string }; score: number | null };
type Matchup = { home: Side; away: Side | null; winner: "home" | "away" | null; isBye: boolean };

async function expectMatchup(game: Locator, m: Matchup) {
  const home = game.getByTestId("bracket-side").filter({ hasText: m.home.owner.name });
  await expect(home).toContainText(String(m.home.seed));
  if (m.isBye) {
    await expect(game).toContainText("Bye");
    return;
  }
  const away = game.getByTestId("bracket-side").filter({ hasText: m.away!.owner.name });
  await expect(home).toContainText(points(m.home.score!));
  await expect(away).toContainText(String(m.away!.seed));
  await expect(away).toContainText(points(m.away!.score!));
  const [winner, loser] = m.winner === "home" ? [home, away] : [away, home];
  await expect(winner).toContainText("Winner");
  await expect(loser).not.toContainText("Winner");
}

for (const year of [2018, 2020]) {
  const { bracket } = seasonDoc(year);

  test(`${year}: the bracket shows every round in order with seeds, Owners, scores and winners`, async ({ page }, info) => {
    await page.goto(`/seasons/${year}/`);
    const region = page.getByRole("region", { name: "Playoff bracket" });
    await expect(region.getByRole("heading", { level: 3 })).toHaveText([
      ...bracket.rounds.map((r: { name: string }) => r.name),
      "Third-place game",
    ]);

    for (const round of bracket.rounds) {
      const section = region.getByRole("group", { name: round.name });
      await expect(section).toContainText(weeksNote(round.weeks));
      const matchups = section.getByRole("listitem");
      await expect(matchups).toHaveCount(round.matchups.length);
      for (const [i, m] of round.matchups.entries()) await expectMatchup(matchups.nth(i), m);
    }

    const third = region.getByRole("group", { name: "Third-place game" });
    await expectMatchup(third.getByRole("listitem"), bracket.thirdPlaceGame.matchup);

    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
    const shots = path.resolve(import.meta.dirname, "../test-results/screenshots", info.project.name);
    // The sticky header would otherwise be painted across a tall element capture
    await region.screenshot({ path: path.join(shots, `bracket-${year}.png`), style: "header { position: static !important; }" });
  });
}

test("the 12-team bracket shows first-round byes", async ({ page }) => {
  await page.goto("/seasons/2020/");
  const firstRound = page.getByRole("region", { name: "Playoff bracket" }).getByRole("group").first();
  await expect(firstRound.getByRole("listitem").filter({ hasText: "Bye" })).toHaveCount(2);
});

test("a two-week round says which Weeks it spans", async ({ page }) => {
  await page.goto("/seasons/2018/");
  const region = page.getByRole("region", { name: "Playoff bracket" });
  await expect(region.getByRole("group", { name: "Semifinals" })).toContainText("Weeks 14–15");
  await expect(region.getByRole("group", { name: "Championship" })).toContainText("Weeks 16–17");
});
